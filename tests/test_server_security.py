"""Tests P0-2 — Autenticación obligatoria en LAN/HUD + rate limiting.

Cubre:
  1. Sin bypass de loopback: localhost sin credencial -> 401 (HTTP y WS).
  2. El HUD (/) y /admin exigen autenticación; /static también.
  3. Los tokens en query strings ya no autentican (ni HTTP ni WS).
  4. /pair y /healthz siguen públicos (puerta de emparejamiento y monitoreo).
  5. /api/pair/claim: rate limiting contra fuerza bruta (429 tras N fallos).
  6. claim válido (pair y setup) -> 303 con cookies de larga duración.
"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from fastapi.testclient import TestClient

import core.security as security
import server.web_server as web_server
from core.device_registry import DeviceRegistry
from core.pairing import PairingManager
from core.rate_limit import RateLimiter
from core.security import authorize_http


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeHTTPRequest:
    def __init__(self, host="127.0.0.1", headers=None):
        self.client = FakeClient(host)
        self.headers = headers or {}


class FakeWS:
    def __init__(self, host="127.0.0.1", headers=None, query_params=None):
        self.client = FakeClient(host)
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.closed = []

    async def close(self, code=1000, reason=""):
        self.closed.append((code, reason))


class ServerAuthTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._old_sec_reg = security.registry
        self._old_ws_reg = web_server.registry
        self._old_pm = web_server.pairing_manager
        self._old_limiter = web_server._pair_limiter
        tmp_reg = DeviceRegistry(path=Path(self._tmp.name) / "authorized_devices.json")
        security.registry = tmp_reg
        web_server.registry = tmp_reg
        web_server.pairing_manager = PairingManager()
        web_server._pair_limiter = RateLimiter(max_attempts=3, window_seconds=600, lockout_seconds=600)
        self.registry = tmp_reg
        self.client = TestClient(web_server.app, follow_redirects=False)

    def tearDown(self):
        security.registry = self._old_sec_reg
        web_server.registry = self._old_ws_reg
        web_server.pairing_manager = self._old_pm
        web_server._pair_limiter = self._old_limiter
        self._tmp.cleanup()

    def _enroll(self, device_id="pc-exequiel", roles=("api",)):
        token, _device = self.registry.enroll(device_id, list(roles))
        return device_id, token

    def _auth_headers(self, device_id, token):
        return {"x-titan-token": token, "x-titan-device-id": device_id}


class TestLoopbackBypassRemoved(ServerAuthTestBase):
    def test_localhost_http_without_credential_is_401(self):
        req = FakeHTTPRequest(host="127.0.0.1", headers={})
        with self.assertRaises(HTTPException) as ctx:
            authorize_http(req)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_lan_http_without_credential_is_401(self):
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 401)

    def test_enrolled_device_gets_200(self):
        device_id, token = self._enroll()
        resp = self.client.get("/api/status", headers=self._auth_headers(device_id, token))
        self.assertEqual(resp.status_code, 200)

    def test_wrong_token_is_401(self):
        device_id, _token = self._enroll()
        resp = self.client.get("/api/status", headers=self._auth_headers(device_id, "wrong"))
        self.assertEqual(resp.status_code, 401)

    def test_cookie_auth_works(self):
        device_id, token = self._enroll()
        resp = self.client.get(
            "/api/status",
            headers={"cookie": f"titan_token={token}; titan_device_id={device_id}"},
        )
        self.assertEqual(resp.status_code, 200)


class TestWebsocketBypassRemoved(unittest.IsolatedAsyncioTestCase):
    async def test_localhost_ws_without_credential_is_rejected(self):
        from fastapi import WebSocketException
        ws = FakeWS(host="127.0.0.1", headers={})
        # P0-2 (fix doble close): authorize_websocket ya no cierra el socket
        # ella misma; lanza WebSocketException y Starlette hace el cierre.
        with self.assertRaises(WebSocketException) as ctx:
            await security.authorize_websocket(ws, role="ws")
        self.assertEqual(ctx.exception.code, 1008)
        self.assertEqual(ws.closed, [])

    async def test_query_string_token_no_longer_authenticates(self):
        from fastapi import WebSocketException
        # Aunque el token sea válido, en query string se ignora.
        ws = FakeWS(host="192.168.100.10", headers={},
                    query_params={"token": "api-secret", "device_id": "x"})
        with self.assertRaises(WebSocketException) as ctx:
            await security.authorize_websocket(ws, role="api")
        self.assertEqual(ctx.exception.code, 1008)
        self.assertEqual(ws.closed, [])


class TestHudAndAdminProtected(ServerAuthTestBase):
    def test_index_requires_auth(self):
        self.assertEqual(self.client.get("/").status_code, 401)

    def test_index_served_with_valid_device(self):
        device_id, token = self._enroll()
        resp = self.client.get("/", headers=self._auth_headers(device_id, token))
        # 200 si existe index.html, 404 JSON si no; nunca 401
        self.assertIn(resp.status_code, (200, 404))

    def test_admin_requires_auth(self):
        self.assertEqual(self.client.get("/admin").status_code, 401)

    def test_query_string_token_does_not_authenticate_index(self):
        device_id, token = self._enroll()
        resp = self.client.get(f"/?token={token}&device_id={device_id}")
        self.assertEqual(resp.status_code, 401)

    def test_static_requires_auth(self):
        resp = self.client.get("/static/app.js")
        self.assertIn(resp.status_code, (401, 404))

    def test_pair_page_is_public(self):
        resp = self.client.get("/pair")
        self.assertIn(resp.status_code, (200, 404))

    def test_healthz_is_public(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)


class TestPairClaimRateLimit(ServerAuthTestBase):
    def test_brute_force_gets_429(self):
        for _ in range(3):
            resp = self.client.post("/api/pair/claim", json={"code": "000000"})
            self.assertEqual(resp.status_code, 401)
        resp = self.client.post("/api/pair/claim", json={"code": "000000"})
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp.headers)

    def test_valid_pair_claim_sets_long_lived_cookies(self):
        device_id, token = self._enroll()
        code = web_server.pairing_manager.create(device_id, token)
        resp = self.client.post("/api/pair/claim", json={"code": code})
        self.assertEqual(resp.status_code, 303)
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("titan_token", set_cookie)
        self.assertIn(f"max-age={web_server.DEVICE_COOKIE_MAX_AGE}", set_cookie.lower())

    def test_setup_claim_enrolls_new_device(self):
        code = web_server.pairing_manager.create_setup(["api"])
        resp = self.client.post("/api/pair/claim", json={"code": code})
        self.assertEqual(resp.status_code, 303)
        devices = self.registry.list_devices()
        self.assertTrue(any("api" in d.get("roles", []) for d in devices.values()))
        # El código es de un solo uso
        resp2 = self.client.post("/api/pair/claim", json={"code": code})
        self.assertEqual(resp2.status_code, 401)


class TestRateLimiter(unittest.TestCase):
    def test_blocks_after_max_attempts(self):
        rl = RateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=60)
        self.assertFalse(rl.is_blocked("k"))
        rl.register_failure("k")
        self.assertFalse(rl.is_blocked("k"))
        rl.register_failure("k")
        self.assertTrue(rl.is_blocked("k"))
        self.assertGreater(rl.retry_after("k"), 0)

    def test_success_resets(self):
        rl = RateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=60)
        rl.register_failure("k")
        rl.register_success("k")
        rl.register_failure("k")
        self.assertFalse(rl.is_blocked("k"))


if __name__ == "__main__":
    unittest.main()
