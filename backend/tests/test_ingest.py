import json

import pyarrow.parquet as pq
import pytest

from data_engineering.ingest import Source, exchange_rates, parse, stage


def test_ingest_writes_metadata_and_skips_seen_content(tmp_path):
    content = json.dumps([{"order_id": "order", "order_timestamp": "2024-01-02T02:00:00+02:00"}]).encode()
    source = Source("orders", "order.json", content)
    staged = stage([source, source], tmp_path, "a", [])
    assert len(staged) == 1
    batch = staged[0]
    assert batch.watermark == "2024-01-02T00:00:00+00:00"
    row = pq.read_table(tmp_path / batch.key).to_pylist()[0]
    assert row["ingestion_run_id"] == "a"
    assert len(row["record_hash"]) == 64
    assert stage([source], tmp_path, "b", staged) == []


def test_csv_schema_and_exchange_rate_fixture():
    assert parse(b"currency,usd_per_unit\nUSD,1\n", ".csv") == [{"currency": "USD", "usd_per_unit": "1"}]
    with pytest.raises(ValueError):
        parse(b"duplicate,duplicate\nx,y\n", ".csv")
    assert len(parse(exchange_rates().content, ".json")) == 3
