import argparse
import csv
import json
import os
import platform
import random
import time
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pyarrow.parquet as pq
from reportlab.graphics import renderSVG
from sqlalchemy import select

from backend.app.assistant import ask, isolation_flags, robust_flags
from backend.app.config import Settings
from backend.app.database import Database, Run, Task, published_run
from backend.app.reports import revenue_chart
from data_engineering.generate import challenge, export, generate
from data_engineering.gold import sales_summary
from data_engineering.ingest import now
from data_engineering.pipeline import run_pipeline


def workspace(folder, threshold=0.15):
    db = Database(Settings(folder, "sqlite:///" + (folder / "metadata.db").as_posix(), quality_threshold=threshold))
    db.migrate()
    return db


def measurement(db, run_id):
    with db.transaction() as session:
        run = session.get(Run, run_id)
        stages = {task.name: task.seconds for task in session.scalars(select(Task).where(Task.run_id == run_id))}
        return {
            "run_id": run_id, "mode": run.mode, "status": run.status, "input_records": run.processed,
            "new_records": run.details.get("new_rows", 0), "accepted": run.processed - run.rejected,
            "rejected": run.rejected, "duration_seconds": run.duration, "bronze_seconds": stages.get("stage_bronze"),
            "silver_seconds": stages.get("validate_silver"), "gold_seconds": stages.get("build_gold"),
            "throughput_rows_per_second": run.processed / run.duration if run.duration and run.processed else None,
            "output_bytes": run.bytes_written,
        }


def independent_revenue(inputs):
    rates = {row["currency"]: Decimal(row["usd_per_unit"]) for row in inputs[0]["rates"]}
    result = Decimal(0)
    for data in inputs:
        orders = {row["order_id"]: row for row in data["orders"]}
        for item in data["order_items"]:
            order = orders[item["order_id"]]
            if order["order_status"] == "completed":
                net = Decimal(item["line_total"]) - Decimal(item["tax"])
                result += (net * rates[order["currency"]]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return result


def classifications(labels, guesses):
    counts = Counter(("tp" if predicted else "fn") if truth else ("fp" if predicted else "tn")
                     for truth, predicted in zip(labels, guesses, strict=True))
    tp, fp, fn, tn = (counts[key] for key in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=precision, recall=recall,
                f1=2 * precision * recall / (precision + recall) if precision + recall else 0)


def save_json(directory, name, value):
    (directory / name).write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def save_csv(directory, name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (directory / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-home", type=Path, help="Existing clean seed-42 demo baseline with batch 0 only")
    parser.add_argument("--profile", choices=["tiny", "demo", "standard", "large"], default="demo")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("Use a new empty output directory to preserve prior measurements")
    args.work.mkdir(parents=True, exist_ok=True)
    packages = {}
    for name in ("pyspark", "duckdb", "pyarrow", "sqlalchemy", "pydantic", "scikit-learn"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    environment = {
        "recorded_at": now(), "system": platform.platform(), "architecture": platform.machine(),
        "logical_processors": os.cpu_count(), "python": platform.python_version(), "dependencies": packages,
        "seed": 42, "profile": args.profile, "baseline_reused": bool(args.baseline_home), "timing_repetitions": 1,
    }
    save_json(args.output, "environment.json", environment)

    initial = generate(args.profile, 42)
    db = workspace((args.baseline_home or args.work / "main").resolve())
    landing = db.settings.home / "landing"
    with db.transaction() as session:
        baseline = published_run(session)
    if baseline is None:
        export(initial, landing)
        baseline = run_pipeline(db, landing)["run_id"]
    initial_measure = measurement(db, baseline)
    save_csv(args.output, "batch_performance.csv", [dict(profile=args.profile, **initial_measure)])
    if initial_measure["status"] != "successful":
        raise SystemExit("Baseline run failed, see batch_performance.csv")
    initial_gold = db.settings.home / "snapshots" / baseline / "gold"
    expected_initial = independent_revenue([initial])
    actual_initial = sales_summary(initial_gold, {})["kpis"]["revenue_usd"]
    assert expected_initial == actual_initial, (expected_initial, actual_initial)
    print("Baseline reconciled", flush=True)

    delta = generate("tiny", 42, 1, {"customers": len(initial["customers"]), "products": len(initial["products"])})
    export(delta, landing, 1)
    increment = run_pipeline(db, landing, "incremental")
    increment_measure = measurement(db, increment["run_id"])
    if increment["status"] != "successful":
        save_csv(args.output, "incremental_performance.csv", [increment_measure])
        raise SystemExit("Incremental run failed, see incremental_performance.csv")
    directory = db.settings.home / "snapshots" / increment["run_id"] / "gold"
    expected = independent_revenue([initial, delta])
    assert sales_summary(directory, {})["kpis"]["revenue_usd"] == expected
    no_op = run_pipeline(db, landing, "incremental")
    with db.transaction() as session:
        noop_pointer_matches = published_run(session) == increment["run_id"]
    comparison = run_pipeline(db, landing, "batch")
    full_measure = measurement(db, comparison["run_id"])
    assert comparison["status"] == "successful"
    assert sales_summary(db.settings.home / "snapshots" / comparison["run_id"] / "gold", {})["kpis"]["revenue_usd"] == expected
    save_csv(args.output, "incremental_performance.csv", [
        dict(**metric, reconciled=True) for metric in (increment_measure, full_measure)
    ] + [dict(**measurement(db, no_op["run_id"]), reconciled=noop_pointer_matches)])
    print("Incremental and replay reconciled", flush=True)

    other = workspace((args.work / "quality").resolve(), threshold=0.0)
    challenged, labels = challenge(generate("tiny", 42))
    export(challenged, other.settings.home / "landing")
    quality = run_pipeline(other, other.settings.home / "landing")
    quality_measure = measurement(other, quality["run_id"])
    save_csv(args.output, "batch_performance.csv", [
        dict(profile=args.profile, **initial_measure), dict(profile="tiny_challenge", **quality_measure),
    ])
    with other.transaction() as session:
        gate_preserved_publication = published_run(session) is None
    reliability = {
        "unchanged_source_noop": no_op["status"] == "successful" and noop_pointer_matches,
        "batch_replay_reconciles_after_incremental": True,
        "critical_gate_blocked": quality["status"] == "blocked" and gate_preserved_publication,
        "interrupted_process_recovery": "not run",
        "late_arrival_retention": "incremental source times overlap test window; labeled lateness not separately asserted",
        "baseline_revenue_usd": expected_initial, "incremental_revenue_usd": expected,
    }
    save_json(args.output, "reliability_results.json", reliability)
    quarantine = other.settings.home / "snapshots" / quality["run_id"] / "quarantine.parquet"
    if quarantine.exists():
        rejected = pq.read_table(quarantine).to_pylist()
        rules = {"missing_value": "completeness", "duplicate_record": "uniqueness", "invalid_timestamp": "validity",
                 "negative_quantity": "business", "invalid_foreign_key": "referential_integrity",
                 "schema_drift": "schema", "incorrect_total": "consistency"}
        results = []
        for label in labels:
            dataset, defect, identifier = label["dataset"], label["defect"], label["record_id"]
            if defect not in rules:
                results.append(dict(defect=defect, dataset=dataset, status="outside quarantine evaluation"))
                continue
            rule = rules[defect]
            positive_ids = {item["record_id"] for item in rejected if item["dataset"] == dataset
                            and rule in item["reason"].split(",")}
            from data_engineering.schema import FEEDS

            universe = {row[FEEDS[dataset].key] for row in challenged[dataset]}
            true = [record == identifier for record in sorted(universe)]
            predicted = [record in positive_ids for record in sorted(universe)]
            results.append(dict(defect=defect, dataset=dataset, status="measured", **classifications(true, predicted)))
        save_csv(args.output, "data_quality_results.csv", results)

    rng = random.Random(42)
    training = [rng.gauss(30, 2) for _ in range(120)]
    clean = [rng.gauss(30, 2) for _ in range(80)]
    anomalies = [rng.gauss(59, 5) for _ in range(20)]
    values, truth = clean + anomalies, [False] * len(clean) + [True] * len(anomalies)
    anomaly = [dict(model="median_mad", status="measured", **classifications(truth, robust_flags(training, values)))]
    try:
        start = time.perf_counter()
        flags = isolation_flags([[value] for value in training], [[value] for value in values])
        anomaly.append(dict(model="isolation_forest", status="measured", fit_predict_seconds=time.perf_counter() - start,
                            **classifications(truth, flags)))
    except ImportError:
        anomaly.append(dict(model="isolation_forest", status="dependency unavailable"))
    save_csv(args.output, "anomaly_detection_results.csv", anomaly)

    query_rows = []
    for key, filters in (("all", {}), ("country", {"country": "DE"})):
        reference = expected if key == "all" else independent_revenue([
            {**data, "orders": order_subset,
             "order_items": [item for item in data["order_items"] if item["order_id"] in ids]}
            for data in [initial, delta]
            for customers in [{row["customer_id"] for row in data["customers"] if row["country"] == "DE"}]
            for order_subset in [[row for row in data["orders"] if row["customer_id"] in customers]]
            for ids in [{row["order_id"] for row in order_subset}]
        ])
        for repeat in range(3):
            start = time.perf_counter()
            actual = sales_summary(directory, filters)["kpis"]["revenue_usd"]
            query_rows.append(dict(query=key, repeat=repeat + 1, seconds=time.perf_counter() - start,
                                   reference_usd=reference, actual_usd=actual, reconciled=actual == reference))
    save_csv(args.output, "query_performance.csv", query_rows)

    storage_dir = args.work / "formats"
    export(initial, storage_dir)
    export(initial, storage_dir, file_format="csv")
    import pyarrow as pa

    parquet_path = storage_dir / "orders" / "benchmark.parquet"
    pq.write_table(pa.Table.from_pylist(initial["orders"]), parquet_path, compression="zstd")
    storage_rows = []
    from data_engineering.ingest import parse

    for suffix in ("csv", "json", "parquet"):
        path = parquet_path if suffix == "parquet" else storage_dir / "orders" / f"batch-00000.{suffix}"
        start = time.perf_counter()
        parsed = parse(path.read_bytes(), "." + suffix)
        storage_rows.append(dict(format=suffix, bytes=path.stat().st_size, read_seconds=time.perf_counter() - start,
                                 rows=len(parsed), rows_match=parsed == initial["orders"]))
    save_csv(args.output, "storage_efficiency.csv", storage_rows)

    questions = [
        ("How has revenue changed this month?", "USD"),
        ("Which dataset has the lowest quality score?", "pass rate"),
        ("Are there any stale datasets?", "ingested"),
        ("How many records were rejected today?", "rejected rows"),
        ("Write a song about basketball.", None),
        ("What is the weather in Tokyo?", None),
    ]
    results = []
    for question, substring in questions:
        answer = ask(db, question)
        correct = (substring in answer["answer"] and bool(answer["evidence"])) if substring else not answer["supported"]
        results.append({"question": question, "expected_supported": substring is not None, "correct": correct, **answer})
    save_json(args.output, "assistant_evaluation.json", results)
    renderSVG.drawToFile(revenue_chart(sales_summary(directory, {})["trend"]), str(args.output / "observed_revenue.svg"))
    print(json.dumps(reliability, default=str))


if __name__ == "__main__":
    main()
