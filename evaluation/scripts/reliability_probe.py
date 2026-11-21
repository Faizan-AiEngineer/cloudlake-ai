import argparse
import json
from pathlib import Path

from sqlalchemy import select

from backend.app.database import Quality, Run, published_run
from data_engineering.generate import challenge, export, generate
from data_engineering.pipeline import run_pipeline
from evaluation.scripts.benchmark import workspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True, help="Existing demo benchmark workspace with a publication")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output filename to preserve prior results")
    db = workspace(args.home.resolve(), threshold=0)
    with db.transaction() as session:
        previous = published_run(session)
        incremental = session.scalar(select(Run).where(
            Run.mode == "incremental", Run.status == "successful", Run.processed > 0,
        ).order_by(Run.started_at.desc()).limit(1))
        if not previous or not incremental:
            parser.error("A demo baseline and a changed incremental publication are required")
        late = sum(session.scalars(select(Quality.failed).where(
            Quality.run_id == incremental.id, Quality.rule_id == "freshness",
        )))
    landing = db.settings.home / "challenge"
    payload, _ = challenge(generate("tiny", 42, 2, {"customers": 1000, "products": 250}))
    export(payload, landing, 2)
    outcome = run_pipeline(db, landing, "incremental")
    with db.transaction() as session:
        current = published_run(session)
        failed = session.get(Run, outcome["run_id"])
        report = {
            "blocked_run": failed.id, "blocked": failed.status == "blocked", "rejected_rows": failed.rejected,
            "publication_preserved": current == previous, "published_run": current,
            "late_records_flagged_in_successful_incremental_run": late,
        }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(report)
    return 0 if report["blocked"] and report["publication_preserved"] and late else 1


if __name__ == "__main__":
    raise SystemExit(main())
