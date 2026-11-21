from pathlib import Path

import pytest


def test_airflow_imports_all_dags():
    pytest.importorskip("airflow")
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert bag.import_errors == {}
    assert {dag_id.removeprefix("cloudlake_") for dag_id in bag.dags} == {
        "batch", "incremental", "quality", "maintenance", "backfill",
    }
