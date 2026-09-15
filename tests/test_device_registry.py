import tempfile
import unittest
from pathlib import Path

from core.device_registry import DeviceRegistry


class TestDeviceRegistry(unittest.TestCase):
    def test_enroll_verify_and_revoke_by_role(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = DeviceRegistry(Path(temp_dir) / "authorized_devices.json")
            token, _ = registry.enroll("hud-celular", ["api"])
            self.assertTrue(registry.verify("hud-celular", token, "api"))
            self.assertFalse(registry.verify("hud-celular", token, "satellite"))
            self.assertFalse(registry.verify("otro", token, "api"))
            self.assertTrue(registry.revoke("hud-celular"))
            self.assertFalse(registry.verify("hud-celular", token, "api"))

    def test_registry_stores_hash_not_plain_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "authorized_devices.json"
            registry = DeviceRegistry(path)
            token, _ = registry.enroll("device", ["api"])
            self.assertNotIn(token, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
