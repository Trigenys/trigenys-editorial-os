from __future__ import annotations

from urllib.parse import quote, urlparse

import asgi
from js import Request as JSRequest
from workers import Response, WorkerEntrypoint

from editorial_os_api.config import Settings
from editorial_os_api.main import create_app


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


def _settings_for_env(env: object) -> Settings:
    payload_token = _text(getattr(env, "EDITORIAL_OS_PAYLOAD_API_TOKEN", None))
    return Settings(
        environment="staging",
        deployment_label="cloudflare-worker",
        database_url=_hyperdrive_database_url(getattr(env, "HYPERDRIVE")),
        database_echo=False,
        langfuse_enabled=False,
        posthog_enabled=False,
        payload_enabled=bool(payload_token),
        payload_base_url=(
            _text(getattr(env, "EDITORIAL_OS_PAYLOAD_BASE_URL", None))
            or "https://insight.trigenys.com"
        ),
        payload_api_token=payload_token,
        payload_collection=(
            _text(getattr(env, "EDITORIAL_OS_PAYLOAD_COLLECTION", None)) or "posts"
        ),
        payload_auth_mode=(
            _text(getattr(env, "EDITORIAL_OS_PAYLOAD_AUTH_MODE", None)) or "bearer"
        ),
        payload_auth_collection=(
            _text(getattr(env, "EDITORIAL_OS_PAYLOAD_AUTH_COLLECTION", None)) or "users"
        ),
        postiz_enabled=False,
        n8n_enabled=False,
        remotion_enabled=False,
        operator_api_token=_text(
            getattr(env, "EDITORIAL_OS_OPERATOR_TOKEN", None)
        ),
    )


class Default(WorkerEntrypoint):
    """Cloudflare transport adapter around the canonical FastAPI application."""

    async def fetch(self, request):
        # All Worker routes except the explicitly public health probes are
        # protected by Cloudflare Access at the edge. Authenticated operator
        # requests carry the Cloudflare-signed assertion; the legacy FastAPI
        # bearer token is injected *only in the Worker*, never sent to a browser.
        path = urlparse(str(request.url)).path
        if path.startswith("/api/operator/"):
            assertion = _text(request.headers.get("Cf-Access-Jwt-Assertion"))
            if assertion is None:
                return Response.json(
                    {"detail": "Cloudflare Access authentication is required."},
                    status=401,
                )
            operator_token = _text(getattr(self.env, "EDITORIAL_OS_OPERATOR_TOKEN", None))
            if operator_token is None:
                return Response.json(
                    {"detail": "Operator authentication is not configured."},
                    status=503,
                )
            # A JS Request constructor takes the original Request and an
            # optional RequestInit *object*, not Python keyword arguments.
            # Cloning first gives us writable headers without mutating the
            # incoming request or exposing the server credential to the client.
            request = JSRequest.new(request)
            request.headers.set("Authorization", f"Bearer {operator_token}")

        application = getattr(self, "_editorial_os_app", None)
        if application is None:
            application = create_app(_settings_for_env(self.env))
            self._editorial_os_app = application

        return await asgi.fetch(application, request, self.env)
