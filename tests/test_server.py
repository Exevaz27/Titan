import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.security as security
import server.web_server as web_server
from core.device_registry import DeviceRegistry


class TestServer(unittest.TestCase):
    def setUp(self):
        # P0-2: la API exige autenticación; los tests enrolan un dispositivo
        # en un registry temporal.
        self._tmp = TemporaryDirectory()
        self._old_sec_reg = security.registry
        self._old_ws_reg = web_server.registry
        tmp_reg = DeviceRegistry(path=Path(self._tmp.name) / "authorized_devices.json")
        security.registry = tmp_reg
        web_server.registry = tmp_reg
        device_id, token = "test-pc", tmp_reg.enroll("test-pc", ["api"])[0]
        self.headers = {"x-titan-token": token, "x-titan-device-id": device_id}
        self.client = TestClient(web_server.app)

    def tearDown(self):
        security.registry = self._old_sec_reg
        web_server.registry = self._old_ws_reg
        self._tmp.cleanup()

    def test_status_endpoint(self):
        response = self.client.get("/api/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("metrics", data)

    def test_metrics_endpoint(self):
        response = self.client.get("/api/metrics", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cpu_percent", data)

    def test_apps_endpoint(self):
        response = self.client.get("/api/apps", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("catalog", data)

    def test_status_endpoint_without_auth_is_401(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
