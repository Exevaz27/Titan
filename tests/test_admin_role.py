"""S-4: rol admin separado para gestionar dispositivos."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import server.web_server as web_server
from core import security
from core.device_registry import DeviceRegistry


def _headers(device_id, token):
    return {"x-titan-token": token, "x-titan-device-id": device_id}


class TestAdminRole(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reg = DeviceRegistry(path=Path(self.temp_dir.name) / "authorized_devices.json")
        self.patcher1 = patch.object(security, "registry", self.reg)
        self.patcher2 = patch.object(web_server, "registry", self.reg)
        self.patcher1.start()
        self.patcher2.start()
        self.client = TestClient(web_server.app, raise_server_exceptions=False)

    def tearDown(self):
        self.patcher2.stop()
        self.patcher1.stop()
        self.temp_dir.cleanup()

    def test_api_no_puede_ver_panel_ni_lista(self):
        token = self.reg.enroll("hud-j2", ["api"])[0]
        did = "hud-j2"
        self.assertEqual(self.client.get("/api/admin/devices", headers=_headers(did, token)).status_code, 401)
        self.assertEqual(self.client.get("/admin", headers=_headers(did, token)).status_code, 401)

    def test_admin_si_puede(self):
        token = self.reg.enroll("celu", ["api", "admin"])[0]
        did = "celu"
        r = self.client.get("/api/admin/devices", headers=_headers(did, token))
        self.assertEqual(r.status_code, 200)
        self.assertIn("celu", r.json()["registered"])
        self.assertEqual(self.client.get("/admin", headers=_headers(did, token)).status_code, 200)

    def test_admin_implica_api_en_transporte(self):
        token = self.reg.enroll("adm", ["admin"])[0]
        did = "adm"
        self.assertEqual(self.client.get("/api/status", headers=_headers(did, token)).status_code, 200)

    def test_enroll_acepta_rol_admin(self):
        token = self.reg.enroll("adm", ["admin"])[0]
        did = "adm"
        r = self.client.post(
            "/api/admin/devices/enroll",
            headers=_headers(did, token),
            json={"device_id": "hud-nuevo", "roles": ["api"], "base_url": "http://192.168.100.5:8000"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.reg.list_devices()["hud-nuevo"]["roles"], ["api"])

    def test_enroll_rechaza_rol_invalido(self):
        token = self.reg.enroll("adm", ["admin"])[0]
        did = "adm"
        r = self.client.post(
            "/api/admin/devices/enroll",
            headers=_headers(did, token),
            json={"device_id": "x", "roles": ["root"], "base_url": "http://192.168.100.5:8000"},
        )
        self.assertEqual(r.status_code, 400)

    def test_enroll_solo_admin(self):
        token = self.reg.enroll("hud", ["api"])[0]
        did = "hud"
        r = self.client.post(
            "/api/admin/devices/enroll",
            headers=_headers(did, token),
            json={"device_id": "x", "roles": ["api"], "base_url": "http://192.168.100.5:8000"},
        )
        self.assertEqual(r.status_code, 401)

    def test_revoke_solo_admin(self):
        api_token = self.reg.enroll("hud", ["api"])[0]
        api_id = "hud"
        adm_token = self.reg.enroll("adm", ["admin"])[0]
        adm_id = "adm"
        self.reg.enroll("victima", ["api"])
        r = self.client.post("/api/admin/devices/victima/revoke", headers=_headers(api_id, api_token))
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/admin/devices/victima/revoke", headers=_headers(adm_id, adm_token))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.reg.list_devices()["victima"]["enabled"])

    def test_migracion_promueve_api(self):
        self.reg.enroll("celu", ["api"])
        self.reg.enroll("j2", ["api"])
        self.assertEqual(security.ensure_admin_role(), 2)
        self.assertTrue(security.admin_devices_exist())
        self.assertIn("admin", self.reg.list_devices()["celu"]["roles"])
        self.assertEqual(security.ensure_admin_role(), 0)

    def test_migracion_no_toca_si_hay_admin(self):
        self.reg.enroll("adm", ["api", "admin"])
        self.reg.enroll("j2", ["api"])
        self.assertEqual(security.ensure_admin_role(), 0)
        self.assertNotIn("admin", self.reg.list_devices()["j2"]["roles"])

    def test_migracion_no_promueve_satellite(self):
        self.reg.enroll("pc-win", ["satellite"])
        self.assertEqual(security.ensure_admin_role(), 0)
        self.assertNotIn("admin", self.reg.list_devices()["pc-win"]["roles"])

    def test_migracion_registry_vacio(self):
        self.assertEqual(security.ensure_admin_role(), 0)
        self.assertFalse(security.admin_devices_exist())


if __name__ == "__main__":
    unittest.main()
