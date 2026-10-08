from fastapi.testclient import TestClient

import editorial_os_api.main as main_module
from editorial_os_api.config import Settings
from editorial_os_api.main import app, create_app

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


def test_readiness_uses_injected_app_database_settings(monkeypatch) -> None:
    settings = Settings(
        environment="staging",
        deployment_label="cloudflare-worker",
        database_url="postgresql+psycopg://staging:staging@hyperdrive.local:5432/editorial_os",
        langfuse_enabled=False,
        posthog_enabled=False,
        payload_enabled=False,
        postiz_enabled=False,
        n8n_enabled=False,
        remotion_enabled=False,
    )
    seen: list[Settings | None] = []

    def fake_check_database(candidate: Settings | None = None) -> None:
        seen.append(candidate)

    monkeypatch.setattr(main_module, "check_database", fake_check_database)
    response = TestClient(create_app(settings)).get("/health/ready")

    assert response.status_code == 200
    assert seen == [settings]


def test_session_factory_can_be_bound_to_injected_runtime_settings(monkeypatch) -> None:
    import editorial_os_api.persistence.session as session_module

    settings = Settings(
        environment="staging",
        deployment_label="cloudflare-worker",
        database_url="postgresql+psycopg://runtime:runtime@runtime-db:5432/editorial_os",
        langfuse_enabled=False,
        posthog_enabled=False,
        payload_enabled=False,
        postiz_enabled=False,
        n8n_enabled=False,
        remotion_enabled=False,
    )
    captured: list[Settings | None] = []

    class DummyEngine:
        pass

    def fake_get_engine(candidate: Settings | None = None):
        captured.append(candidate)
        return DummyEngine()

    monkeypatch.setattr(session_module, "get_engine", fake_get_engine)
    session_module.configure_session_factory(settings)
    session_module.get_session_factory()

    assert captured == [settings]
