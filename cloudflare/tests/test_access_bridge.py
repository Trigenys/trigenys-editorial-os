"""Contract tests for the Cloudflare Access / Python Worker request bridge.

No Cloudflare credentials, database or network connection are required.
The JS Request constructor mock accepts exactly the one positional argument
used in production; passing an unsupported Python keyword breaks this test.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_PATH = Path(__file__).resolve().parents[2] / "cloudflare/src/worker.py"


class Headers(dict):
    def get(self, key, default=None):
        return next(
            (value for name, value in self.items() if name.lower() == key.lower()),
            default,
        )

    def set(self, key, value):
        self[key] = value


class Request:
    def __init__(self, path, headers=None):
        self.url = "https://example.workers.dev" + path
        self.headers = Headers(headers or {})


class JSRequest:
    @staticmethod
    def new(original):
        cloned = Request("/")
        cloned.url = original.url
        cloned.headers = Headers(original.headers)
        return cloned


class Response:
    @staticmethod
    def json(payload, status=200):
        return {"status": status, "payload": payload}


def load_worker():
    workers = types.ModuleType("workers")
    workers.Response = Response
    workers.WorkerEntrypoint = object
    js = types.ModuleType("js")
    js.Request = JSRequest
    asgi = types.ModuleType("asgi")

    async def asgi_fetch(application, request, env):
        return request

    asgi.fetch = asgi_fetch
    package = types.ModuleType("editorial_os_api")
    package.__path__ = []
    config = types.ModuleType("editorial_os_api.config")
    config.Settings = object
    main = types.ModuleType("editorial_os_api.main")
    main.create_app = lambda settings: object()
    stubs = {
        "workers": workers,
        "js": js,
        "asgi": asgi,
        "editorial_os_api": package,
        "editorial_os_api.config": config,
        "editorial_os_api.main": main,
    }
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("editorial_worker_test", WORKER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module._settings_for_env = lambda env: object()
    return module


class OperatorAccessBridgeTests(unittest.TestCase):
    def setUp(self):
        self.worker = load_worker()
        self.entrypoint = self.worker.Default()
        self.entrypoint.env = types.SimpleNamespace(
            EDITORIAL_OS_OPERATOR_TOKEN="private-worker-token"
        )

    def test_authenticated_requests_get_server_only_authorization(self):
        incoming = Request(
            "/api/operator/runs?limit=50",
            {"Cf-Access-Jwt-Assertion": "verified-by-access-edge"},
        )
        forwarded = asyncio.run(self.entrypoint.fetch(incoming))
        self.assertIsNot(forwarded, incoming)
        self.assertEqual(
            forwarded.headers.get("Authorization"),
            "Bearer private-worker-token",
        )
        self.assertIsNone(incoming.headers.get("Authorization"))
        self.assertEqual(
            forwarded.headers.get("Cf-Access-Jwt-Assertion"),
            "verified-by-access-edge",
        )

    def test_missing_access_assertion_fails_closed(self):
        result = asyncio.run(self.entrypoint.fetch(Request("/api/operator/runs")))
        self.assertEqual(result["status"], 401)

    def test_missing_server_secret_fails_closed(self):
        self.entrypoint.env.EDITORIAL_OS_OPERATOR_TOKEN = None
        result = asyncio.run(
            self.entrypoint.fetch(
                Request("/api/operator/runs", {"Cf-Access-Jwt-Assertion": "token"})
            )
        )
        self.assertEqual(result["status"], 503)

    def test_health_checks_do_not_require_a_session(self):
        incoming = Request("/health/ready")
        forwarded = asyncio.run(self.entrypoint.fetch(incoming))
        self.assertIs(forwarded, incoming)


if __name__ == "__main__":
    unittest.main()
