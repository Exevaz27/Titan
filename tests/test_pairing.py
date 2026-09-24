import unittest

from core.pairing import PairingManager


class TestPairingManager(unittest.TestCase):
    def test_code_is_single_use(self):
        manager = PairingManager(ttl_seconds=60)
        code = manager.create("j2", "token")
        claimed = manager.claim(code)
        self.assertEqual(claimed["kind"], "pair")
        self.assertEqual(claimed["device_id"], "j2")
        self.assertEqual(claimed["token"], "token")
        self.assertIsNone(manager.claim(code))

    def test_invalid_code_is_rejected(self):
        manager = PairingManager()
        self.assertIsNone(manager.claim("000000"))

    def test_setup_code_claims_with_roles(self):
        manager = PairingManager(ttl_seconds=60)
        code = manager.create_setup(["api"])
        claimed = manager.claim(code)
        self.assertEqual(claimed["kind"], "setup")
        self.assertEqual(claimed["roles"], ["api"])
        # Un solo uso
        self.assertIsNone(manager.claim(code))


if __name__ == "__main__":
    unittest.main()
