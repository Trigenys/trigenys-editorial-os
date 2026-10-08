from __future__ import annotations

from urllib.parse import quote

import asgi
from workers import WorkerEntrypoint

from editorial_os_api.config import Settings
from editorial_os_api.main import create_app
from editorial_os_api.persistence.session import configure_session_factory


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    return raw or None


def _bool(value: object | None, *, default: bool = False) -> bool:
    raw = _text(value)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _hyperdrive_database_url(binding: object) -> str:
    user = quote(str(getattr(binding, "user")), safe="")
    password = quote(str(getattr(binding, "password")), safe="")
    host = str(getattr(binding, "host"))
    port = int(getattr(binding, "port"))
    database = quote(str(getattr(binding, "database")), safe="")
    return f"postgresql+pg8000://{user}:{password}@{host}:{port}/{database}"


class Default(WorkerEntrypoint):
    """Cloudflare transport adapter around the canonical FastAPI application."""

    async def fetch(self, request):
        application = getattr(self, "_editorial_os_app", None)
        if application is None:
            settings = Settings(
                environment="staging",
                deployment_label="cloudflare-worker",
                database_url=_hyperdrive_database_url(self.env.HYPERDRIVE),
                database_echo=False,
                langfuse_enabled=False,
                posthog_enabled=False,
                payload_enabled=_bool(
                    getattr(self.env, "EDITORIAL_OS_PAYLOAD_ENABLED", None)
                ),
                payload_base_url=_text(
                    getattr(self.env, "EDITORIAL_OS_PAYLOAD_BASE_URL", None)
                ),
                payload_api_token=_text(
                    getattr(self.env, "EDITORIAL_OS_PAYLOAD_API_TOKEN", None)
                ),
                payload_collection=(
                    _text(getattr(self.env, "EDITORIAL_OS_PAYLOAD_COLLECTION", None))
                    or "posts"
                ),
                payload_auth_mode=(
                    _text(getattr(self.env, "EDITORIAL_OS_PAYLOAD_AUTH_MODE", None))
                    or "bearer"
                ),
                payload_auth_collection=(
                    _text(
                        getattr(
                            self.env,
                            "EDITORIAL_OS_PAYLOAD_AUTH_COLLECTION",
                            None,
                        )
                    )
                    or "users"
                ),
                postiz_enabled=False,
                n8n_enabled=False,
                remotion_enabled=False,
            )
            configure_session_factory(settings)
            application = create_app(settings)
            self._editorial_os_app = application

        return await asgi.fetch(application, request, self.env)
