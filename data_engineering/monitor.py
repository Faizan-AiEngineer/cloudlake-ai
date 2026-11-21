from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.database import Run
from data_engineering.ingest import get_history
from data_engineering.pipeline import exclusive, open_alert
from data_engineering.schema import FEEDS


def monitor(db, stale_hours=36):
    with exclusive(db.settings.home), db.transaction() as session:
        history = get_history(session)
        runs = session.scalars(select(Run).where(Run.status == "successful").order_by(
            Run.started_at.desc(), Run.id.desc(),
        ).limit(20)).all()
        current = datetime.now(UTC)
        threshold = current - timedelta(hours=stale_hours)
        timestamps = {}
        for batch in history:
            run = session.get(Run, batch.run_id)
            timestamps[batch.dataset] = max(run.started_at, timestamps.get(batch.dataset, ""))
        stale = [name for name in FEEDS if name not in timestamps or datetime.fromisoformat(timestamps[name]) < threshold]
        run_id = runs[0].id if runs else None
        if stale:
            open_alert(session, run_id, "stale_datasets", "WARNING", "Stale or missing: " + ", ".join(stale))
        meaningful = [run for run in runs if run.processed]
        if len(meaningful) > 2:
            latest, *older = meaningful
            baseline_rows = sum(run.processed for run in older) / len(older)
            baseline_seconds = sum(run.duration or 0 for run in older) / len(older)
            if latest.processed > 1.75 * baseline_rows:
                open_alert(session, latest.id, "volume_change", "WARNING", "Latest processed volume exceeded baseline.")
            if (latest.duration or 0) > max(15, 2 * baseline_seconds):
                open_alert(session, latest.id, "slow_run", "WARNING", "Latest duration exceeded baseline.")
            if latest.rejected / latest.processed > db.settings.quality_threshold:
                open_alert(session, latest.id, "high_error_rate", "CRITICAL", "Rejected record fraction exceeded threshold.")
        return {"stale": stale, "datasets": len(timestamps), "runs_examined": len(runs)}
