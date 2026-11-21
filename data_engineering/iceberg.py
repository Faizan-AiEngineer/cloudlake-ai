import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def iceberg_catalog(home: Path):
    from pyiceberg.catalog import load_catalog

    root = home / "iceberg"
    root.mkdir(parents=True, exist_ok=True)
    return load_catalog(
        "local", type="sql", uri="sqlite:///" + (root / "catalog.db").as_posix(),
        warehouse=(root / "warehouse").resolve().as_uri(),
        **{"py-io-impl": "data_engineering.iceberg_io.LocalFileIO"},
    )


def register_snapshot(home, run_id):
    if not re.fullmatch("[0-9a-f]{32}", run_id):
        raise ValueError("Expected a published run identifier")
    catalog = iceberg_catalog(home)
    catalog.create_namespace_if_not_exists("commerce")
    sample = pq.read_table(home / "snapshots" / run_id / "gold" / "daily_sales.parquet")
    table_name = "commerce.daily_sales"
    table = catalog.create_table_if_not_exists(table_name, schema=sample.schema, properties={"format-version": "2"})
    if any(snapshot.summary.additional_properties.get("cloudlake_run") == run_id for snapshot in table.snapshots()):
        return table
    # Replacing the logical table retains its earlier snapshots for time travel.
    sample = sample.cast(pa.schema([pa.field(field.name, field.type, nullable=True) for field in sample.schema]))
    table.overwrite(sample, snapshot_properties={"cloudlake_run": run_id})
    return table
