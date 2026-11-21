import json
from decimal import Decimal

from data_engineering.generate import challenge, export, generate
from data_engineering.schema import FEEDS


def test_generator_is_deterministic_and_preserves_relationships(tmp_path):
    data = generate("tiny", 42)
    assert data == generate("tiny", 42)
    assert data != generate("tiny", 48)
    assert 800 <= sum(map(len, data.values())) <= 1400
    for name, rows in data.items():
        feed = FEEDS[name]
        assert len({row[feed.key] for row in rows}) == len(rows)
        for foreign_key, parent in feed.references:
            keys = {row[FEEDS[parent].key] for row in data[parent]}
            assert all(row[foreign_key] in keys for row in rows)
    for row in data["order_items"]:
        expected = Decimal(row["unit_price"]) * row["quantity"] - Decimal(row["discount"]) + Decimal(row["tax"])
        assert expected == Decimal(row["line_total"])
    export(data, tmp_path)
    export(data, tmp_path, file_format="csv")
    assert json.loads((tmp_path / "orders/batch-00000.json").read_text()) == data["orders"]
    assert (tmp_path / "orders/batch-00000.csv").exists()


def test_challenge_is_separate_and_labeled():
    data = generate("tiny")
    modified, labels = challenge(data)
    assert len(labels) == 9
    assert modified["customers"][0]["city"] is None
    assert data["customers"][0]["city"] is not None
    assert len(modified["customers"]) == len(data["customers"]) + 1
