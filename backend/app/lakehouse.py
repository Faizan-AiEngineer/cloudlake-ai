import re
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import select

from backend.app.database import Manifest, Run, published_run
from data_engineering.gold import MODELS
from data_engineering.schema import FEEDS, SCHEMA_VERSION


def inspect_parquet(paths, limit):
    rows = []
    schema = None
    total = size = 0
    for path in paths:
        if not path.is_file():
            continue
        file = pq.ParquetFile(path)
        schema = file.schema_arrow
        total += file.metadata.num_rows
        size += path.stat().st_size
        remaining = limit - len(rows)
        if remaining > 0:
            batch = next(file.iter_batches(batch_size=remaining), None)
            if batch is not None:
                rows.extend(batch.to_pylist())
    return {
        "rows": rows, "total": total, "bytes": size,
        "fields": [{"name": field.name, "type": str(field.type)} for field in schema] if schema is not None else [],
    }


def snapshot(db) -> Path | None:
    with db.transaction() as session:
        run_id = published_run(session)
    return db.settings.home / "snapshots" / run_id if run_id else None


def source_inventory(db):
    output = []
    with db.transaction() as session:
        for name, feed in FEEDS.items():
            batches = session.scalars(
                select(Manifest).where(Manifest.dataset == name).order_by(Manifest.source_file),
            ).all()
            files = [{"file": batch.source_file, "rows": batch.rows, "watermark": batch.watermark,
                      "run": batch.run_id, "ingested_at": session.get(Run, batch.run_id).started_at}
                     for batch in batches]
            output.append({
                "dataset": name, "type": "Exchange-rate feed" if name == "rates" else "Synthetic commerce",
                "rows": sum(item["rows"] for item in files), "schema_version": SCHEMA_VERSION,
                "updated_at": max((item["ingested_at"] for item in files), default=None),
                "event_watermark": max((item["watermark"] for item in files if item["watermark"]), default=None),
                "schema": feed.fields, "files": files,
            })
    return output


def partitions(db, dataset):
    with db.transaction() as session:
        batches = session.scalars(select(Manifest).where(Manifest.dataset == dataset)).all()
    return [db.settings.home / batch.key for batch in batches]


def lineage(is_published):
    nodes = []
    edges = []

    def add_node(zone, name):
        identifier = f"{zone}:{name}"
        nodes.append({"id": identifier, "zone": zone, "name": name})
        return identifier

    def link(start, end):
        edges.append({"source": start, "target": end, "origin": "declared"})

    for name in FEEDS:
        link(add_node("source", name), f"bronze:{name}")
        link(add_node("bronze", name), f"silver:{name}")
        add_node("silver", name)
    for table in MODELS:
        add_node("gold", table)
        for feed in FEEDS:
            if re.search(rf"\b(?:FROM|JOIN)\s+{feed}\b", MODELS[table], re.IGNORECASE):
                link(f"silver:{feed}", f"gold:{table}")
        for parent in MODELS:
            if parent != table and re.search(
                rf"\b(?:FROM|JOIN)\s+{parent}\b", MODELS[table], re.IGNORECASE,
            ):
                link(f"gold:{parent}", f"gold:{table}")
    add_node("dashboard", "business_analytics")
    link("gold:fact_sales", "dashboard:business_analytics")
    return {"nodes": nodes, "edges": edges, "has_publication": is_published}
