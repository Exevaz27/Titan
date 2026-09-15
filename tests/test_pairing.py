import unittest

from core.pairing import PairingManager


class TestPairingManager(unittest.TestCase):
    def test_code_is_single_use(self):
        manager = PairingManager(ttl_seconds=60)
        code = manager.create("j2", "token")
        self.assertEqual(manager.claim(code), ("j2", "token"))
        self.assertIsNone(manager.claim(code))

    def test_invalid_code_is_rejected(self):
        manager = PairingManager()
        self.assertIsNone(manager.claim("000000"))


if __name__ == "__main__":
    unittest.main()
