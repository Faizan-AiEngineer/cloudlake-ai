import argparse
from pathlib import Path

from data_engineering.generate import PROFILES, export, generate
from data_engineering.gold import sales_summary
from data_engineering.pipeline import run_pipeline
from evaluation.scripts.benchmark import independent_revenue, measurement, save_csv, workspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, default="standard")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    location = args.work.resolve()
    if (location / "metadata.db").exists() or args.output.exists():
        parser.error("Use new run and output paths")
    sample = generate(args.profile, 42)
    db = workspace(location)
    export(sample, location / "landing")
    outcome = run_pipeline(db, location / "landing")
    record = measurement(db, outcome["run_id"])
    if outcome["status"] == "successful":
        gold = location / "snapshots" / outcome["run_id"] / "gold"
        revenue = sales_summary(gold, {})["kpis"]["revenue_usd"]
        record["reconciled"] = revenue == independent_revenue([sample])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_csv(args.output.parent, args.output.name, [dict(profile=args.profile, **record)])
    print(record)
    return 0 if record.get("reconciled") else 1


if __name__ == "__main__":
    raise SystemExit(main())
