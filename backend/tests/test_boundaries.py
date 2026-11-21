import csv
import io
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.app.config import Settings
from backend.app.database import Alert, Database, Quality, Run, State, published_run
from backend.app.main import create_app
from data_engineering.ingest import now
from data_engineering.pipeline import exclusive, recover_interrupted


def app_client(tmp_path):
    return TestClient(create_app(Settings(tmp_path, "sqlite:///" + (tmp_path / "metadata.db").as_posix())))


def test_upload_and_query_boundaries(tmp_path):
    with app_client(tmp_path) as client:
        assert client.get("/api/v1/lakehouse/gold/unknown").status_code == 404
        assert client.get("/api/v1/lakehouse/quarantine/rejected_records?run_id=..").status_code in (404, 422)
        assert client.get("/api/v1/runs?limit=101").status_code == 422
        assert client.get("/api/v1/analytics?start=2025-02-02&end=2025-01-01").status_code == 422
        assert client.post("/api/v1/sources/orders/upload", params={"filename": "../orders.json"},
                           content=b"[]").status_code == 422
        assert client.post("/api/v1/sources/orders/upload", params={"filename": "orders.json"},
                           content=b"x" * (10 * 1024 * 1024 + 1)).status_code == 413
        payload = json.dumps([{"order_id": "seeded"}]).encode()
        response = client.post("/api/v1/sources/orders/upload", params={"filename": "orders.json"}, content=payload)
        assert response.status_code == 201
        assert (tmp_path / "landing" / "orders" / response.json()["file"]).read_bytes() == payload
        assert client.post("/api/v1/runs", json={"mode": "unrestricted"}).status_code == 422
        assert client.post("/api/v1/runs", json={}, headers={"origin": "https://outside.invalid"}).status_code == 403
        assert client.post("/api/v1/assistant/ask", content=b"a" * 8193).status_code == 413
        assert client.get("/health", headers={"host": "outside.invalid"}).status_code == 400


def test_workspace_lease_rejects_concurrent_run(tmp_path):
    with exclusive(tmp_path), pytest.raises(RuntimeError, match="lease"):
        with exclusive(tmp_path):
            pytest.fail("Concurrent processing unexpectedly acquired the workspace lease")
    with exclusive(tmp_path):
        assert (tmp_path / "pipeline.lock").exists()


def test_recovery_keeps_last_published_pointer(tmp_path):
    db = Database(Settings(tmp_path, "sqlite:///" + (tmp_path / "metadata.db").as_posix()))
    db.migrate()
    with db.transaction() as session:
        session.add(Run(id="interrupted", status="running", mode="batch", started_at=now()))
        session.add(State(key="published_run", value="previous"))
    assert recover_interrupted(db) == 1
    assert recover_interrupted(db) == 0
    with db.transaction() as session:
        assert published_run(session) == "previous"
        assert session.get(Run, "interrupted").status == "failed"


def test_offline_assistant_rejects_unsupported_and_handles_empty_state(tmp_path):
    with app_client(tmp_path) as client:
        route = "/api/v1/assistant/ask"
        unsupported = client.post(route, json={"question": "Write a song about basketball"}).json()
        assert unsupported["supported"] is False
        assert unsupported["evidence"] == []
        supported = client.post(route, json={"question": "Which dataset has the lowest quality score?"}).json()
        assert supported["supported"] is True
        assert supported["confidence"] == "insufficient data"
        assert client.get("/api/v1/reports/business/pdf").status_code == 409
        assert client.get("/api/v1/reports/infrastructure/pdf").content.startswith(b"%PDF")


def test_reports_distinguish_published_quality_from_linked_blocked_run(tmp_path, monkeypatch):
    published_id = "a" * 32
    blocked_id = "b" * 32
    monkeypatch.setattr("backend.app.reports.sales_summary", lambda *_: {
        "kpis": {"revenue_usd": Decimal("25.30"), "orders": 2}, "trend": [],
    })
    with app_client(tmp_path) as client:
        with client.app.state.database.transaction() as session:
            session.add(Run(id=blocked_id, mode="incremental", status="blocked", started_at=now(),
                            processed=12, rejected=2))
            session.flush()
            session.add(Alert(run_id=blocked_id, kind="quality_gate", status="open", severity="CRITICAL",
                              message="Quality gate blocked publication", created_at=now()))
        assert client.get("/api/v1/reports/executive/csv").status_code == 409
        pipeline = client.get("/api/v1/reports/pipeline/csv")
        assert pipeline.status_code == 200
        assert f"Pipeline runs,1,run_id,{blocked_id}" in pipeline.text
        assert "Pipeline runs,1,status,blocked" in pipeline.text
        with client.app.state.database.transaction() as session:
            session.add(Run(id=published_id, mode="batch", status="successful", started_at=now()))
            session.flush()
            session.add(State(key="published_run", value=published_id))
            for run_id, failed, status in ((published_id, 0, "pass"), (blocked_id, 2, "blocked")):
                session.add(Quality(run_id=run_id, dataset="orders", rule_id="schema", rule_name="Schema",
                                    evaluated=12, failed=failed, pass_rate=1 - failed / 12,
                                    severity="CRITICAL", status=status, evaluated_at=now()))

        result = client.get("/api/v1/reports/executive/csv")
        assert result.status_code == 200
        fields = {(r["section"], r["row"], r["field"]): r["value"]
                  for r in csv.DictReader(io.StringIO(result.text))}
        assert fields["Quality totals by run", "1", "scope"] == "Published snapshot"
        assert fields["Quality totals by run", "1", "run_id"] == published_id
        assert fields["Quality totals by run", "1", "failed_rule_evaluations"] == "0"
        assert fields["Quality totals by run", "2", "run_id"] == blocked_id
        assert fields["Quality totals by run", "2", "blocked_rules"] == "1"
        assert fields["Operational alerts", "1", "run_id"] == blocked_id
        assert fields["Operational alerts", "1", "run_status"] == "blocked"
        xlsx = client.get("/api/v1/reports/executive/xlsx")
        assert xlsx.status_code == 200
        with io.BytesIO(xlsx.content) as file:
            workbook = load_workbook(file, read_only=True, data_only=True)
            assert list(workbook["Quality totals by run"].values)[2][:2] == ("Blocked candidate", blocked_id)
            assert workbook["Sales metrics"]["B2"].value == 25.30
            workbook.close()
