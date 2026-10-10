"""Cloudflare Access request bridge: reproduce the actual workers-runtime-sdk boundary.

The runtime passes a Python `workers.Request` wrapper, NOT a native
JavaScript Request. Only `request.js_object` may be passed to js.Request.new().
This test suite models that distinction so a regression fails without deploying.
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
        matching = [name for name in self if name.lower() == key.lower()]
        for name in matching:
            del self[name]
        self[key] = value


class NativeJSRequest:
    """Models a real JavaScript Request object (not a Python Request)."""

    def __init__(self, path, headers=None, *, method="GET", body=None):
        self.url = "https://example.workers.dev" + path
        self.headers = Headers(headers or {})
        self.method = method
        self.body = body


class PythonSDKRequest:
    """Matches workers.Request: .js_object is the native JS Request."""

    def __init__(self, path, headers=None, *, method="GET", body=None):
        self.js_object = NativeJSRequest(
            path, headers, method=method, body=body
        )

    @property
    def url(self):
        return self.js_object.url

    @property
    def headers(self):
        return self.js_object.headers

    @property
    def method(self):
        return self.js_object.method

    def __repr__(self):
        return f"Request(method={self.method!r}, url={self.url!r})"


class JSRequest:
    @staticmethod
    def new(original):
        if not isinstance(original, NativeJSRequest):
            # This was the actual production 500 from Cloudflare's logs.
            raise TypeError(f"Invalid URL: {original!r}")
        clone = NativeJSRequest(
            "/",
            original.headers,
            method=original.method,
            body=original.body,
        )
        clone.url = original.url
        return clone


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

    def test_python_sdk_request_is_not_native_js_request(self):
        wrapped = PythonSDKRequest("/api/operator/runs")
        with self.assertRaisesRegex(TypeError, "Invalid URL"):
            JSRequest.new(wrapped)

    def test_authenticated_requests_get_server_only_authorization(self):
        incoming = PythonSDKRequest(
            "/api/operator/runs?limit=50",
            {
                "Cf-Access-Jwt-Assertion": "verified-by-access-edge",
                "Cf-Access-Authenticated-User-Email": "editor@trigenys.com",
                "X-Editorial-Verified-Actor": "client-fraud",
                "Authorization": "Bearer client-untrusted",
            },
        )
        forwarded = asyncio.run(self.entrypoint.fetch(incoming))
        self.assertIsInstance(forwarded, NativeJSRequest)
        self.assertIsNot(forwarded, incoming.js_object)
        self.assertEqual(
            forwarded.headers.get("Authorization"), "Bearer private-worker-token"
        )
        self.assertEqual(
            incoming.headers.get("Authorization"), "Bearer client-untrusted"
        )
        self.assertEqual(
            forwarded.headers.get("Cf-Access-Jwt-Assertion"), "verified-by-access-edge"
        )
        self.assertEqual(forwarded.url, incoming.url)
        self.assertEqual(
            forwarded.headers.get("X-Editorial-Verified-Actor"), "editor@trigenys.com"
        )
        self.assertEqual(incoming.headers.get("X-Editorial-Verified-Actor"), "client-fraud")

    def test_post_body_and_method_survive_native_clone(self):
        incoming = PythonSDKRequest(
            "/api/operator/runs/123/gate",
            {
                "Cf-Access-Jwt-Assertion": "verified-by-access-edge",
                "Cf-Access-Authenticated-User-Email": "editor@trigenys.com",
            },
            method="POST",
            body='{"outcome":"APPROVED"}',
        )
        forwarded = asyncio.run(self.entrypoint.fetch(incoming))
        self.assertEqual(forwarded.method, "POST")
        self.assertEqual(forwarded.body, incoming.js_object.body)
        self.assertEqual(forwarded.headers.get("Authorization"), "Bearer private-worker-token")

    def test_missing_access_assertion_fails_closed(self):
        result = asyncio.run(self.entrypoint.fetch(PythonSDKRequest("/api/operator/runs")))
        self.assertEqual(result["status"], 401)

    def test_no_verified_email_fails_closed(self):
        result = asyncio.run(
            self.entrypoint.fetch(
                PythonSDKRequest(
                    "/api/operator/runs", {"Cf-Access-Jwt-Assertion": "token"}
                )
            )
        )
        self.assertEqual(result["status"], 401)

    def test_missing_server_secret_fails_closed(self):
        self.entrypoint.env.EDITORIAL_OS_OPERATOR_TOKEN = None
        result = asyncio.run(
            self.entrypoint.fetch(
                PythonSDKRequest(
                    "/api/operator/runs",
                    {
                        "Cf-Access-Jwt-Assertion": "token",
                        "Cf-Access-Authenticated-User-Email": "editor@trigenys.com",
                    },
                )
            )
        )
        self.assertEqual(result["status"], 503)

    def test_health_checks_do_not_require_a_session(self):
        incoming = PythonSDKRequest("/health/ready")
        forwarded = asyncio.run(self.entrypoint.fetch(incoming))
        self.assertIs(forwarded, incoming)


if __name__ == "__main__":
    unittest.main()
