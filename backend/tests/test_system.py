from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_readiness_migration_and_public_configuration(tmp_path):
    settings = Settings(tmp_path, "sqlite:///" + (tmp_path / "metadata.db").as_posix())
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json() == {"status": "up"}
        readiness = client.get("/ready")
        assert readiness.json() == {"ready": True}
        assert len(readiness.headers["x-correlation-id"]) == 32
        assert client.get("/api/v1/system/status").json()["metadata"] == {
            "engine": "sqlite", "available": True,
        }
        configuration = client.get("/api/v1/system/configuration").json()
        assert set(configuration) == {"mode", "quality_threshold", "spark_master", "assistant_provider"}
