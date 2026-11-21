from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import SparkSession

from data_engineering.ingest import BRONZE_SCHEMA, now
from data_engineering.rules import RULES, validate_records
from data_engineering.schema import FEEDS, PROCESSING_ORDER

QUARANTINE = pa.schema([
    ("dataset", pa.string()), ("run_id", pa.string()), ("record_id", pa.string()),
    ("reason", pa.string()), ("payload", pa.string()), ("source_file", pa.string()),
    ("record_hash", pa.string()), ("detected_at", pa.string()),
])


def arrow_type(kind):
    if kind.startswith("decimal"):
        precision, scale = map(int, kind.removeprefix("decimal(").removesuffix(")").split(","))
        return pa.decimal128(precision, scale)
    return {"string": pa.string(), "int": pa.int32(), "timestamp": pa.timestamp("us"), "date": pa.date32()}[kind]


def write_chunk(writer, rows, schema):
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        rows.clear()


def spark_path(path):
    normalized = path.resolve().as_posix()
    return "file://" + (normalized if normalized.startswith("/") else "/" + normalized)


@dataclass
class SilverResult:
    quality: list[dict]
    datasets: dict[str, dict]
    rejected: int
    blocked: bool


def transform(spark: SparkSession, batches, home, output, run_id, previous_watermarks, threshold):
    output.mkdir(parents=True, exist_ok=True)
    grouped = {name: [home / batch.key for batch in batches if batch.dataset == name] for name in FEEDS}
    parents, quality, datasets = {}, [], {}
    rejected = 0
    stamp = now()
    blocked = False
    with pq.ParquetWriter(output.parent / "quarantine.parquet", QUARANTINE, compression="zstd") as quarantined:
        for dataset in PROCESSING_ORDER:
            feed = FEEDS[dataset]
            files = grouped[dataset]
            if files:
                raw = spark.read.parquet(*[spark_path(path) for path in files])
            else:
                empty_path = output / f"_empty_{dataset}.parquet"
                pq.write_table(pa.Table.from_pylist([], schema=BRONZE_SCHEMA), empty_path)
                raw = spark.read.parquet(spark_path(empty_path))
            frame = validate_records(dataset, raw, parents, previous_watermarks.get(dataset), run_id)
            path = output / f"{dataset}.parquet"
            schema = pa.schema([(field, arrow_type(kind)) for field, kind in feed.fields.items()])
            good, bad = [], []
            counts = dict.fromkeys(RULES, 0)
            total = accepted = 0
            with pq.ParquetWriter(path, schema, compression="zstd") as writer:
                for row in frame.toLocalIterator():
                    total += 1
                    violations = row["_violations"]
                    for rule in violations:
                        counts[rule] += 1
                    hard = [rule for rule in violations if RULES[rule][1] != "INFO"]
                    if hard:
                        rejected += 1
                        bad.append({
                            "dataset": dataset, "run_id": run_id, "record_id": row[feed.key],
                            "reason": ",".join(hard), "payload": row["payload"], "source_file": row["source_file"],
                            "record_hash": row["record_hash"], "detected_at": stamp,
                        })
                    else:
                        accepted += 1
                        good.append({field: row[field] for field in feed.fields})
                    if len(good) >= 8192:
                        write_chunk(writer, good, schema)
                    if len(bad) >= 8192:
                        write_chunk(quarantined, bad, QUARANTINE)
                write_chunk(writer, good, schema)
                write_chunk(quarantined, bad, QUARANTINE)
            if not files:
                empty_path.unlink()
            parents[dataset] = spark.read.parquet(spark_path(path))
            datasets[dataset] = {"input": total, "accepted": accepted, "bytes": path.stat().st_size}
            for rule, (name, severity) in RULES.items():
                failure = counts[rule] / total if total else 0
                critical = severity == "CRITICAL" and failure > threshold
                blocked |= critical
                quality.append(dict(
                    run_id=run_id, dataset=dataset, rule_id=rule, rule_name=name, evaluated=total,
                    failed=counts[rule], pass_rate=1 - failure, severity=severity, evaluated_at=stamp,
                    status="blocked" if critical else "warning" if counts[rule] else "passed",
                ))
    return SilverResult(quality, datasets, rejected, blocked)
