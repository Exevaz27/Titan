import os
import unittest
from pathlib import Path

from core.path_security import safe_zip_member_path
from core.security import (
    _token_from_headers,
    api_devices_exist,
    token_is_valid,
    token_is_valid_for_roles,
)


class TestSecurityPrimitives(unittest.TestCase):
    def setUp(self):
        self.old_api = os.environ.get("TITAN_API_TOKEN")
        self.old_satellite = os.environ.get("TITAN_SATELLITE_TOKEN")
        os.environ["TITAN_API_TOKEN"] = "api-secret"
        os.environ["TITAN_SATELLITE_TOKEN"] = "satellite-secret"

    def tearDown(self):
        for name, value in (("TITAN_API_TOKEN", self.old_api), ("TITAN_SATELLITE_TOKEN", self.old_satellite)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_tokens_are_role_specific(self):
        self.assertTrue(token_is_valid("api-secret", "api"))
        self.assertFalse(token_is_valid("api-secret", "satellite"))
        self.assertTrue(token_is_valid("satellite-secret", "satellite"))
        self.assertFalse(token_is_valid("wrong", "api"))

    def test_websocket_roles_accept_only_expected_tokens(self):
        self.assertTrue(token_is_valid_for_roles("api-secret", ("api", "satellite")))
        self.assertTrue(token_is_valid_for_roles("satellite-secret", ("api", "satellite")))
        self.assertFalse(token_is_valid_for_roles("wrong", ("api", "satellite")))

    def test_headers_support_bearer_custom_header_and_cookie(self):
        self.assertEqual(_token_from_headers({"authorization": "Bearer abc"}), "abc")
        self.assertEqual(_token_from_headers({"x-titan-token": "custom"}), "custom")
        self.assertEqual(_token_from_headers({"cookie": "foo=bar; titan_token=cookie-token"}), "cookie-token")

    def test_api_devices_exist(self):
        # P0: sin dispositivos con rol api -> False (dispara código de setup)
        import core.security as security_mod
        from core.device_registry import DeviceRegistry
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as d:
            tmp_reg = DeviceRegistry(path=Path(d) / "auth.json")
            old = security_mod.registry
            security_mod.registry = tmp_reg
            try:
                self.assertFalse(api_devices_exist())
                tmp_reg.enroll("satelite", ["satellite"])
                self.assertFalse(api_devices_exist())
                tmp_reg.enroll("pc", ["api"])
                self.assertTrue(api_devices_exist())
            finally:
                security_mod.registry = old

    def test_zip_paths_stay_inside_destination(self):
        destination = Path("C:/Titan/exports")
        safe = safe_zip_member_path(destination, "folder/report.txt")
        self.assertEqual(safe, destination.resolve() / "folder/report.txt")
        with self.assertRaises(ValueError):
            safe_zip_member_path(destination, "../outside.txt")
        with self.assertRaises(ValueError):
            safe_zip_member_path(destination, "C:/outside.txt")


if __name__ == "__main__":
    unittest.main()