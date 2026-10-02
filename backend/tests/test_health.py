from fastapi.testclient import TestClient

from editorial_os_api.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Trigenys Editorial OS API"
    assert payload["environment"] == "test"
    assert payload["deployment"] == "local"


def test_readiness_endpoint_with_postgres() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
