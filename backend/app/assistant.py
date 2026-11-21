import re
from datetime import UTC, datetime
from statistics import median

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.database import Quality, Run, Task
from backend.app.lakehouse import snapshot, source_inventory
from data_engineering.gold import analytical_connection, records, sales_summary

router = APIRouter(prefix="/api/v1")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=400)


def robust_flags(train, values, cutoff=4):
    if len(train) < 5:
        return [False] * len(values)
    center = median(train)
    deviation = median(abs(value - center) for value in train)
    tolerance = max(abs(center) * 0.15, 1e-9)
    return [abs(value - center) > max(tolerance, cutoff * deviation / 0.67449) for value in values]


def isolation_flags(train, values):
    from sklearn.ensemble import IsolationForest

    if len(train) < 25:
        return [False] * len(values)
    model = IsolationForest(random_state=42, contamination=0.05, n_estimators=80)
    return [value == -1 for value in model.fit(train).predict(values)]


def response(answer, evidence=(), actions=(), supported=True, confidence="observed"):
    return {
        "answer": answer, "evidence": list(evidence), "actions": list(actions),
        "supported": supported, "confidence": confidence, "provider": "offline",
    }


def ask(db, question):
    words = re.sub(r"[^a-z0-9 ]", "", question.lower())
    if any(term in words for term in ("quality gate", "pipeline fail", "latest failure", "jobs fail")):
        with db.transaction() as session:
            query = select(Run).where(Run.status.in_(["blocked", "failed"]))
            if "quality gate" in words:
                query = query.where(Run.status == "blocked")
            failed = session.scalar(query.order_by(Run.started_at.desc()).limit(1))
            if not failed:
                return response("There is no recorded failure for that request.")
            task = session.scalar(select(Task).where(
                Task.run_id == failed.id, Task.status.in_(["failed", "blocked"]),
            ).order_by(Task.id.desc()).limit(1))
            rules = session.scalars(select(Quality).where(
                Quality.run_id == failed.id, Quality.status == "blocked",
            ).order_by(Quality.failed.desc()).limit(3)).all()
            detail = "; ".join(f"{rule.dataset} / {rule.rule_name} ({rule.failed}/{rule.evaluated})" for rule in rules)
            explain = f" The leading blocking rules were {detail}." if detail else ""
            return response(
                f"Run {failed.id[:8]} was {failed.status} at {task.name if task else 'worker startup'}.{explain}",
                [{"label": "Pipeline run", "path": f"/pipelines?run={failed.id}"}],
                ["Inspect the task and quarantine records, correct the affected source, and retry."],
            )
    if any(term in words for term in ("quality", "declining dataset")):
        directory = snapshot(db)
        if directory is None:
            return response("No published dataset quality measurements are available.", confidence="insufficient data")
        with db.transaction() as session:
            row = session.execute(select(Quality.dataset, func.sum(Quality.failed), func.sum(Quality.evaluated))
                .where(Quality.run_id == directory.name, Quality.severity != "INFO")
                .group_by(Quality.dataset).order_by(
                    (func.sum(Quality.failed) * 1.0 / func.nullif(func.sum(Quality.evaluated), 0)).desc(),
                    Quality.dataset,
                ).limit(1)).first()
            if row is None or not row[2]:
                return response("The publication has no scored rule checks.", confidence="insufficient data")
            return response(f"{row[0]} has the lowest rule-check pass rate at {1 - row[1] / row[2]:.2%}.",
                            [{"label": "Quality results", "path": "/quality"}])
    if "stale" in words or "freshness" in words:
        feeds = source_inventory(db)
        current = datetime.now(UTC)
        stale = [feed["dataset"] for feed in feeds if not feed["updated_at"] or
                 (current - datetime.fromisoformat(feed["updated_at"])).total_seconds() > 36 * 3600]
        message = "Missing or stale feeds: " + ", ".join(stale) + "." if stale else "All feeds were ingested within 36 hours."
        return response(message, [{"label": "Source inventory", "path": "/sources"}])
    if "reject" in words:
        today = datetime.now(UTC).date().isoformat()
        with db.transaction() as session:
            count = session.scalar(select(func.coalesce(func.sum(Run.rejected), 0)).where(Run.started_at >= today))
        return response(f"Pipeline runs started today (UTC) recorded {count:,} rejected rows.",
                        [{"label": "Run history", "path": "/pipelines"}])
    if any(term in words for term in ("slow", "performance", "pipeline anomaly", "pipeline duration")):
        with db.transaction() as session:
            latest = list(session.scalars(
                select(Run).where(Run.processed > 0, Run.duration.is_not(None), Run.status == "successful")
                .order_by(Run.started_at.desc()).limit(31),
            ))
        if len(latest) < 6:
            return response("At least six successful processing runs are needed for a duration baseline.",
                            [{"label": "Run history", "path": "/pipelines"}], confidence="insufficient data")
        current, *prior = latest
        flags = []
        metrics = {
            "duration": lambda run: run.duration, "processed rows": lambda run: run.processed,
            "error rate": lambda run: run.rejected / run.processed, "output bytes": lambda run: run.bytes_written,
        }
        for label, value in metrics.items():
            if robust_flags([value(run) for run in prior], [value(current)])[0]:
                flags.append(label)
        found = ", ".join(flags) if flags else "no unusual metrics"
        return response(f"The latest run took {current.duration:.1f} seconds. Its rolling baseline flagged {found}.",
                        [{"label": "Run history", "path": f"/pipelines?run={current.id}"}], confidence="statistical")
    if any(word in words for word in ("revenue", "unusual sales", "product demand", "inventory risk", "conversion")):
        directory = snapshot(db)
        if directory is None:
            return response("Business analytics require a successful publication.", confidence="insufficient data")
        if "conversion" in words or "inventory risk" in words or "unusual sales" in words or "product demand" in words:
            with analytical_connection(directory / "gold") as connection:
                if "conversion" in words:
                    rows = records(connection.read_parquet(str(directory / "gold/conversion_funnel.parquet")).execute())
                    by_kind = {row["event_type"]: row["sessions"] for row in rows}
                    answer = (f"Purchase events occurred in {by_kind.get('purchase', 0):,} of "
                              f"{by_kind.get('view', 0):,} viewed sessions.")
                elif "inventory risk" in words:
                    connection.read_parquet(str(directory / "gold/dim_product.parquet")).create_view("p")
                    count = connection.execute("SELECT count(*) FROM p WHERE current_stock = 0").fetchone()[0]
                    answer = f"{count:,} products have zero stock in the latest product snapshot."
                else:
                    connection.read_parquet(str(directory / "gold/fact_sales.parquet")).create_view("sales")
                    rows = records(connection.execute("""
                        WITH daily AS (SELECT product_id, sale_date, SUM(revenue_usd) revenue
                                      FROM sales WHERE order_status='completed' GROUP BY 1,2),
                        ranked AS (SELECT *, row_number() OVER(PARTITION BY product_id ORDER BY sale_date DESC) n
                                   FROM daily),
                        baseline AS (SELECT product_id, avg(revenue) average, count(*) observations
                                     FROM ranked WHERE n BETWEEN 2 AND 31 GROUP BY 1)
                        SELECT r.product_id, round(r.revenue / b.average, 2) AS ratio
                        FROM ranked r JOIN baseline b USING(product_id)
                        WHERE r.n = 1 AND b.observations >= 5 AND b.average > 0 AND r.revenue > 3 * b.average
                        ORDER BY ratio DESC LIMIT 5
                    """))
                    answer = ("Latest selling-day revenue exceeded three times preceding selling-day average for " +
                              ", ".join(f"{row['product_id']} ({row['ratio']}×)" for row in rows) + "."
                              if rows else "No product exceeded the configured selling-day revenue threshold.")
            return response(answer, [{"label": "Published Gold data", "path": "/lakehouse"}])
        trend = sales_summary(directory / "gold", {})["trend"]
        if len(trend) < 2:
            return response("Two observed sales months are needed for a revenue comparison.", confidence="insufficient data")
        previous, current = trend[-2:]
        return response(
            f"Revenue was USD {current['revenue_usd']:,.2f} in {current['month']:%B %Y} and "
            f"USD {previous['revenue_usd']:,.2f} in {previous['month']:%B %Y}, the two latest observed months.",
            [{"label": "Sales analytics", "path": "/analytics"}],
        )
    return response("This question is outside the offline assistant's supported pipeline and analytics topics.",
                    supported=False, confidence="unsupported")


@router.get("/assistant/status")
def provider_status():
    return {"provider": "offline", "available": True, "external_provider_enabled": False}


@router.post("/assistant/ask")
def answer(request: Request, question: Question):
    return ask(request.app.state.database, question.question)
