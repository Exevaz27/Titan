"""Tests P0 — Seguridad del bot de Telegram.

Cubre:
  1. Que NO existe auto-vinculación del primer usuario (se eliminó).
  2. Vinculación con código secreto: válido / inválido / expirado / un solo uso.
  3. Que nadie puede robar la vinculación cuando ya hay dueño.
  4. /desvincular solo por el dueño.
  5. Persistencia del offset de getUpdates (no reprocesar órdenes viejas).
"""
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from integrations.telegram_bot import TelegramBotService
from core.config import config


def make_service():
    svc = TelegramBotService()
    svc.allowed_user_id = None
    svc._pairing_code = None
    svc._pairing_code_expires = 0.0
    svc._send_text = AsyncMock()
    return svc


class TestNoAutoBind(unittest.IsolatedAsyncioTestCase):
    async def test_first_user_does_not_become_owner(self):
        """El cambio P0: sin dueño, el primer usuario NO se auto-vincula."""
        svc = make_service()
        ok = await svc._check_authorization(12345, 999)
        self.assertFalse(ok)
        self.assertIsNone(svc.allowed_user_id)
        svc._send_text.assert_awaited_once()

    async def test_unknown_user_rejected_when_owner_exists(self):
        svc = make_service()
        svc.allowed_user_id = "111"
        ok = await svc._check_authorization(222, 999)
        self.assertFalse(ok)

    async def test_owner_accepted(self):
        svc = make_service()
        svc.allowed_user_id = "111"
        ok = await svc._check_authorization(111, 999)
        self.assertTrue(ok)


class TestPairingCode(unittest.IsolatedAsyncioTestCase):
    async def test_valid_code_binds_owner(self):
        svc = make_service()
        svc._pairing_code = "123456"
        svc._pairing_code_expires = time.time() + 600
        with patch.object(config, "set_telegram_allowed_user_id") as mock_set:
            await svc._handle_pairing(777, 999, "/vincular 123456")
        self.assertEqual(svc.allowed_user_id, "777")
        mock_set.assert_called_once_with("777")
        # Un solo uso: el código queda invalidado
        self.assertIsNone(svc._pairing_code)

    async def test_wrong_code_does_not_bind(self):
        svc = make_service()
        svc._pairing_code = "123456"
        svc._pairing_code_expires = time.time() + 600
        with patch.object(config, "set_telegram_allowed_user_id") as mock_set:
            await svc._handle_pairing(777, 999, "/vincular 000000")
        self.assertIsNone(svc.allowed_user_id)
        mock_set.assert_not_called()

    async def test_expired_code_regenerates(self):
        svc = make_service()
        svc._pairing_code = "123456"
        svc._pairing_code_expires = time.time() - 1
        with patch("builtins.print"):
            with patch.object(config, "set_telegram_allowed_user_id"):
                await svc._handle_pairing(777, 999, "/vincular 123456")
        self.assertIsNone(svc.allowed_user_id)
        # Se generó un código nuevo distinto
        self.assertIsNotNone(svc._pairing_code)
        self.assertNotEqual(svc._pairing_code, "123456")

    async def test_cannot_steal_pairing_when_owner_exists(self):
        svc = make_service()
        svc.allowed_user_id = "111"
        svc._pairing_code = "123456"
        svc._pairing_code_expires = time.time() + 600
        with patch.object(config, "set_telegram_allowed_user_id") as mock_set:
            await svc._handle_pairing(222, 999, "/vincular 123456")
        self.assertEqual(svc.allowed_user_id, "111")
        mock_set.assert_not_called()

    def test_generate_code_format(self):
        svc = make_service()
        with patch("builtins.print"):
            code = svc._generate_pairing_code(ttl_seconds=60)
        self.assertTrue(code.isdigit() and len(code) == 6)
        self.assertGreater(svc._pairing_code_expires, time.time())


class TestOffsetPersistence(unittest.TestCase):
    def test_offset_roundtrip(self):
        with TemporaryDirectory() as d:
            svc = make_service()
            svc._offset_file = Path(d) / "offset.json"
            self.assertEqual(svc._load_offset(), 0)
            svc._save_offset(4242)
            self.assertEqual(svc._load_offset(), 4242)
            # Simula un reinicio: otra instancia con el mismo archivo
            svc2 = make_service()
            svc2._offset_file = svc._offset_file
            self.assertEqual(svc2._load_offset(), 4242)

    def test_corrupt_offset_file_returns_zero(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "offset.json"
            p.write_text("no-json{{{", encoding="utf-8")
            svc = make_service()
            svc._offset_file = p
            self.assertEqual(svc._load_offset(), 0)


class TestPairingRouting(unittest.IsolatedAsyncioTestCase):
    async def test_vincular_handled_before_authorization(self):
        """/vincular debe funcionar sin estar autorizado (es como se obtiene)."""
        svc = make_service()
        svc._pairing_code = "654321"
        svc._pairing_code_expires = time.time() + 600
        update = {
            "update_id": 10,
            "message": {"chat": {"id": 999}, "from": {"id": 777}, "text": "/vincular 654321"},
        }
        with patch.object(config, "set_telegram_allowed_user_id"):
            await svc._process_update(update)
        self.assertEqual(svc.allowed_user_id, "777")

    async def test_unpair_by_owner(self):
        svc = make_service()
        svc.allowed_user_id = "777"
        update = {
            "update_id": 11,
            "message": {"chat": {"id": 999}, "from": {"id": 777}, "text": "/desvincular"},
        }
        with patch("builtins.print"):
            with patch.object(config, "set_telegram_allowed_user_id"):
                await svc._process_update(update)
        self.assertIsNone(svc.allowed_user_id)
        self.assertIsNotNone(svc._pairing_code)

    async def test_unpair_by_stranger_denied(self):
        svc = make_service()
        svc.allowed_user_id = "777"
        update = {
            "update_id": 12,
            "message": {"chat": {"id": 999}, "from": {"id": 666}, "text": "/desvincular"},
        }
        with patch.object(config, "set_telegram_allowed_user_id"):
            await svc._process_update(update)
        self.assertEqual(svc.allowed_user_id, "777")


if __name__ == "__main__":
    unittest.main()
