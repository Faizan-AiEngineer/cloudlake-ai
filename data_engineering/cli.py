import argparse
import json
import logging
import time
from pathlib import Path

from backend.app.config import Settings
from backend.app.database import Database
from data_engineering.generate import PROFILES, challenge, export, generate
from data_engineering.pipeline import recover_interrupted, run_pipeline


def main():
    parser = argparse.ArgumentParser(prog="cloudlake")
    commands = parser.add_subparsers(dest="command", required=True)
    generator = commands.add_parser("generate")
    generator.add_argument("--profile", choices=PROFILES, default="demo")
    generator.add_argument("--seed", type=int, default=42)
    generator.add_argument("--batch", type=int, default=0)
    generator.add_argument("--count", action="append", default=[], metavar="DATASET=COUNT")
    generator.add_argument("--format", choices=["csv", "json"], default="json")
    generator.add_argument("--output", type=Path)
    generator.add_argument("--challenge", action="store_true")
    runner = commands.add_parser("run")
    runner.add_argument("--landing", type=Path)
    runner.add_argument("--object-bucket", help="Read feed files from an explicitly configured S3-compatible bucket")
    runner.add_argument("--object-prefix", default="landing")
    runner.add_argument("--object-endpoint", help="Optional endpoint URL for local MinIO")
    runner.add_argument("--mode", choices=["batch", "incremental", "backfill"], default="batch")
    runner.add_argument("--run-id")
    runner.add_argument("--trigger", choices=["cli", "api", "airflow"], default="cli")
    runner.add_argument("--online-rates", action="store_true")
    stream = commands.add_parser("stream")
    stream.add_argument("--batches", type=int, default=3, choices=range(1, 101), metavar="1..100")
    stream.add_argument("--interval", type=float, default=5)
    migrate = commands.add_parser("migrate")
    migrate.set_defaults(command="migrate")
    commands.add_parser("monitor")
    commands.add_parser("iceberg")
    commands.add_parser("recover")
    args = parser.parse_args()
    settings = Settings.load()
    landing = settings.home / "landing"
    logging.basicConfig(level=logging.INFO)

    if args.command == "generate":
        try:
            counts = {name: int(count) for name, count in (item.split("=", 1) for item in args.count)}
            data = generate(args.profile, args.seed, args.batch, counts)
        except ValueError as error:
            parser.error(str(error))
        output = args.output or (settings.home / "challenge" if args.challenge else landing)
        if args.challenge:
            data, labels = challenge(data)
            output.mkdir(parents=True, exist_ok=True)
            (output / "defects.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
        export(data, output, args.batch, args.format)
        print(json.dumps({name: len(rows) for name, rows in data.items()}))
        return 0

    db = Database(settings)
    db.migrate()
    if args.command == "migrate":
        return 0
    if args.command == "recover":
        print(json.dumps({"recovered_runs": recover_interrupted(db)}))
        return 0
    if args.command == "monitor":
        from data_engineering.monitor import monitor

        print(json.dumps(monitor(db)))
        return 0
    if args.command == "iceberg":
        from backend.app.database import published_run
        from data_engineering.iceberg import register_snapshot

        with db.transaction() as session:
            current = published_run(session)
        if current is None:
            parser.error("Publish the pipeline before registering an Iceberg snapshot")
        table = register_snapshot(settings.home, current)
        print(json.dumps([{"id": item.snapshot_id, "committed_ms": item.timestamp_ms} for item in table.snapshots()]))
        return 0
    if args.command == "stream":
        first = max([int(path.stem.split("-")[-1]) for path in (landing / "clickstream").glob("batch-*.json")
                     if path.stem.split("-")[-1].isdigit()], default=0) + 1
        for number in range(first, first + args.batches):
            export(generate("tiny", 42, number), landing, number)
            result = run_pipeline(db, landing, "incremental")
            print(json.dumps(result))
            if result["status"] != "successful":
                return 1
            if number + 1 < first + args.batches:
                time.sleep(max(0, args.interval))
        return 0
    source = args.landing or landing
    if args.object_bucket:
        if args.landing:
            parser.error("Choose one source location")
        import boto3

        from data_engineering.ingest import S3Source

        source = S3Source(boto3.client("s3", endpoint_url=args.object_endpoint), args.object_bucket, args.object_prefix)
    result = run_pipeline(db, source, args.mode, args.trigger, args.run_id, args.online_rates)
    print(json.dumps(result))
    return 0 if result["status"] == "successful" else 1


if __name__ == "__main__":
    raise SystemExit(main())
