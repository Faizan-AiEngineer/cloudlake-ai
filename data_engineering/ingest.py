import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import Manifest
from data_engineering.generate import FIXTURE
from data_engineering.schema import FEEDS, SCHEMA_VERSION

MAX_SOURCE_BYTES = 512 * 1024 * 1024
FORMATS = {".csv", ".json", ".parquet"}
BRONZE_SCHEMA = pa.schema([
    ("payload", pa.string()), ("ingestion_timestamp", pa.string()), ("source_name", pa.string()),
    ("source_file", pa.string()), ("ingestion_run_id", pa.string()), ("schema_version", pa.string()),
    ("record_hash", pa.string()), ("record_number", pa.int64()),
])


def now():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def fingerprint(content):
    return hashlib.sha256(content).hexdigest()


def canonical(row):
    return json.dumps(
        {key: None if val is None or val == "" else str(val) for key, val in row.items()},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def parse(data, suffix):
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds ingestion size limit")
    if suffix == ".json":
        records = json.loads(data)
    elif suffix == ".csv":
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        if not reader.fieldnames or "" in reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requires named and unique headers")
        records = list(reader)
    elif suffix == ".parquet":
        records = pq.ParquetFile(pa.BufferReader(data)).read().to_pylist()
    else:
        raise ValueError("Unsupported source format")
    if not isinstance(records, list) or any(
        not isinstance(row, dict) or any(not isinstance(key, str) for key in row)
        or any(isinstance(value, (list, dict, bytes)) for value in row.values())
        for row in records
    ):
        raise ValueError("Expected an array of flat source records")
    return records


@dataclass(frozen=True)
class Source:
    dataset: str
    name: str
    content: bytes


class Filesystem:
    def __init__(self, root: Path):
        self.root = root

    def sources(self):
        for dataset in FEEDS:
            folder = self.root / dataset
            if not folder.is_dir() or folder.is_symlink():
                continue
            for file in sorted(folder.iterdir()):
                if file.suffix.lower() not in FORMATS or file.is_symlink() or not file.is_file():
                    continue
                if file.stat().st_size > MAX_SOURCE_BYTES or len(file.name) > 200:
                    raise ValueError(f"Source size or filename limit exceeded in {dataset}")
                yield Source(dataset, file.name, file.read_bytes())


class S3Source:
    """Read-only S3 or MinIO adapter. The caller supplies the configured boto3 client."""

    def __init__(self, client, bucket, prefix="landing"):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")

    def sources(self):
        page = self.client.get_paginator("list_objects_v2")
        for batch in page.paginate(Bucket=self.bucket, Prefix=self.prefix + "/"):
            for entry in batch.get("Contents", ()):
                key = entry["Key"]
                parts = key.removeprefix(self.prefix + "/").split("/")
                if len(parts) != 2 or parts[0] not in FEEDS or Path(parts[1]).suffix.lower() not in FORMATS:
                    continue
                if entry["Size"] > MAX_SOURCE_BYTES or len(parts[1]) > 200:
                    raise ValueError(f"Source size or filename limit exceeded in {parts[0]}")
                body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
                try:
                    content = body.read(MAX_SOURCE_BYTES + 1)
                finally:
                    body.close()
                yield Source(parts[0], parts[1], content)


def exchange_rates(online=False) -> Source:
    if online:
        try:
            response = httpx.get(
                "https://api.frankfurter.dev/v1/latest",
                params={"base": "USD", "symbols": "EUR,GBP"}, timeout=5,
            )
            payload = response.raise_for_status().json()
            currencies = {"USD": 1, **payload["rates"]}
            records = [
                {"currency": currency, "usd_per_unit": f"{1 / currencies[currency]:.6f}",
                 "provenance": f"Frankfurter {payload['date']}"}
                for currency in ("USD", "EUR", "GBP")
            ]
            return Source("rates", "http-rates.json", json.dumps(records).encode())
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    return Source("rates", "offline-rates.json", FIXTURE.read_bytes())


@dataclass(frozen=True)
class BronzeBatch:
    dataset: str
    digest: str
    run_id: str
    key: str
    source_file: str
    rows: int
    watermark: str | None

    def manifest(self):
        return Manifest(**asdict(self))


def get_history(session: Session):
    return [BronzeBatch(**{key: getattr(row, key) for key in BronzeBatch.__annotations__})
            for row in session.scalars(select(Manifest)).all()]


def bronze(source, home: Path, run_id, digest):
    feed = FEEDS[source.dataset]
    rows = parse(source.content, Path(source.name).suffix.lower())
    key = f"bronze/{source.dataset}/{digest}.parquet"
    destination = home / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    recorded = now()
    output, events = [], []
    for number, row in enumerate(rows, start=1):
        payload = canonical(row)
        output.append({
            "payload": payload, "ingestion_timestamp": recorded, "source_name": source.dataset,
            "source_file": source.name, "ingestion_run_id": run_id, "schema_version": SCHEMA_VERSION,
            "record_hash": fingerprint(payload.encode()), "record_number": number,
        })
        if feed.timestamp and row.get(feed.timestamp):
            try:
                stamp = datetime.fromisoformat(str(row[feed.timestamp]))
                stamp = stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)
                events.append(stamp.isoformat(timespec="seconds"))
            except ValueError:
                pass
    temporary = destination.with_suffix(f".{uuid4().hex}.tmp")
    try:
        pq.write_table(pa.Table.from_pylist(output, schema=BRONZE_SCHEMA), temporary, compression="zstd")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return BronzeBatch(source.dataset, digest, run_id, key, source.name, len(rows), max(events, default=None))


def stage(sources, home: Path, run_id, history):
    existing = {(batch.dataset, batch.digest) for batch in history}
    staged = []
    for source in sources:
        digest = fingerprint(source.content)
        key = source.dataset, digest
        if key not in existing:
            staged.append(bronze(source, home, run_id, digest))
            existing.add(key)
    return staged
