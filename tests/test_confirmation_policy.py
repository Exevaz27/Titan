"""Tests P0-3: política central de confirmaciones.

Verifica TTL, atadura a origen+solicitante, un solo uso, reemplazo,
cierre ante acciones desconocidas y el flujo punta a punta por voz
y el aislamiento entre canales (voz vs Telegram).
"""

import time
import unittest

from core.confirmation import (
    ConfirmationManager,
    confirmation_manager,
    is_confirmation,
    requires_confirmation,
    set_channel,
)


def _reset_singleton():
    confirmation_manager._by_id.clear()
    confirmation_manager._latest.clear()
    confirmation_manager._recently_expired.clear()


class TestTTL(unittest.TestCase):
    def test_vence_y_no_se_puede_confirmar(self):
        mgr = ConfirmationManager()
        conf = mgr.request("shutdown", origin="voz", requester="voz-local", ttl_seconds=0.05)
        time.sleep(0.1)
        self.assertIsNone(mgr.confirm(conf.id, origin="voz", requester="voz-local"))
        self.assertIsNone(mgr.get_pending("voz", "voz-local"))

    def test_vigente_se_puede_confirmar(self):
        mgr = ConfirmationManager()
        conf = mgr.request("shutdown", origin="voz", requester="voz-local", ttl_seconds=60)
        got = mgr.confirm(conf.id, origin="voz", requester="voz-local")
        self.assertIsNotNone(got)
        self.assertEqual(got.action, "shutdown")


class TestAtaduraOrigenSolicitante(unittest.TestCase):
    def test_otro_origen_no_confirma(self):
        mgr = ConfirmationManager()
        conf = mgr.request("shutdown", origin="voz", requester="voz-local")
        # Un "sí" por Telegram no puede confirmar lo pedido por voz.
        self.assertIsNone(mgr.confirm(conf.id, origin="telegram", requester="telegram:123"))
        # Y lo pedido por voz sigue pendiente para voz.
        self.assertIsNotNone(mgr.get_pending("voz", "voz-local"))

    def test_otro_solicitante_no_confirma(self):
        mgr = ConfirmationManager()
        conf = mgr.request("restart", origin="telegram", requester="telegram:111")
        self.assertIsNone(mgr.confirm(conf.id, origin="telegram", requester="telegram:222"))
        self.assertFalse(mgr.cancel(conf.id, origin="telegram", requester="telegram:222"))

    def test_mismo_origen_y_solicitante_si(self):
        mgr = ConfirmationManager()
        conf = mgr.request("sleep", origin="telegram", requester="telegram:111")
        self.assertIsNotNone(mgr.confirm(conf.id, origin="telegram", requester="telegram:111"))


class TestUnSoloUso(unittest.TestCase):
    def test_confirmar_dos_veces_falla_la_segunda(self):
        mgr = ConfirmationManager()
        conf = mgr.request("shutdown", origin="voz", requester="voz-local")
        self.assertIsNotNone(mgr.confirm(conf.id, origin="voz", requester="voz-local"))
        self.assertIsNone(mgr.confirm(conf.id, origin="voz", requester="voz-local"))

    def test_id_invalido_no_confirma(self):
        mgr = ConfirmationManager()
        mgr.request("shutdown", origin="voz", requester="voz-local")
        self.assertIsNone(mgr.confirm("id-que-no-existe", origin="voz", requester="voz-local"))


class TestReemplazo(unittest.TestCase):
    def test_nuevo_pedido_reemplaza_al_anterior(self):
        mgr = ConfirmationManager()
        viejo = mgr.request("shutdown", origin="voz", requester="voz-local")
        nuevo = mgr.request("restart", origin="voz", requester="voz-local")
        self.assertIsNone(mgr.confirm(viejo.id, origin="voz", requester="voz-local"))
        got = mgr.confirm(nuevo.id, origin="voz", requester="voz-local")
        self.assertIsNotNone(got)
        self.assertEqual(got.action, "restart")

    def test_canales_distintos_no_se_pisan(self):
        mgr = ConfirmationManager()
        a = mgr.request("shutdown", origin="voz", requester="voz-local")
        b = mgr.request("shutdown", origin="telegram", requester="telegram:1")
        self.assertIsNotNone(mgr.confirm(a.id, origin="voz", requester="voz-local"))
        self.assertIsNotNone(mgr.confirm(b.id, origin="telegram", requester="telegram:1"))


class TestMatriz(unittest.TestCase):
    def test_accion_desconocida_falla_cerrado(self):
        mgr = ConfirmationManager()
        with self.assertRaises(ValueError):
            mgr.request("formatear_disco", origin="voz", requester="voz-local")

    def test_acciones_sensibles_registradas(self):
        for action in ("shutdown", "restart", "sleep", "empty_recycle_bin",
                       "kill_process", "trash_file", "move_file",
                       "send_file_to_telegram", "register_portable_app"):
            self.assertTrue(requires_confirmation(action), action)


class TestPalabras(unittest.TestCase):
    def test_confirmaciones(self):
        for t in ("sí", "SI", "sí, confirmo", "confirmo", "dale", "de una", "metele", "obvio"):
            self.assertTrue(is_confirmation(t), t)

    def test_no_confirmaciones(self):
        for t in ("hola", "apagá la compu", "qué hora es", "", "siesta"):
            self.assertFalse(is_confirmation(t), t)


class TestFlujoVoz(unittest.TestCase):
    def setUp(self):
        _reset_singleton()
        # gemini_client requiere google.genai (instalado en la DDR3, no en el
        # venv de pruebas): stub mínimo para que try_handle pueda pasar de largo.
        import sys
        import types
        stub = types.ModuleType("brain.gemini_client")
        stub.brain = types.SimpleNamespace(current_mode="normal")
        sys.modules["brain.gemini_client"] = stub

        import core.confirmation as cc
        self._orig_exec = cc.execute_action
        self.executed = []
        def fake_execute(action, args):
            self.executed.append((action, args))
            return {"status": "success", "message": f"[TEST] ejecutado {action}"}
        cc.execute_action = fake_execute

    def tearDown(self):
        import sys
        import core.confirmation as cc
        cc.execute_action = self._orig_exec
        sys.modules.pop("brain.gemini_client", None)
        _reset_singleton()

    def test_pedir_y_confirmar_por_voz(self):
        from brain.local_intents import local_intents
        set_channel("voz", "voz-local")
        msg = local_intents.request_confirmation("empty_recycle_bin")
        self.assertIn("vaciar la papelera", msg)
        self.assertIn("2 minutos", msg)

        handled, reply = local_intents.try_handle("sí, confirmo")
        self.assertTrue(handled)
        self.assertEqual(self.executed, [("empty_recycle_bin", {})])
        self.assertIn("[TEST] ejecutado", reply)

    def test_confirmacion_vencida_no_ejecuta(self):
        from brain.local_intents import local_intents
        from core.confirmation import confirmation_manager as mgr
        set_channel("voz", "voz-local")
        conf = mgr.request("shutdown", origin="voz", requester="voz-local", ttl_seconds=0.05)
        time.sleep(0.1)
        handled, reply = local_intents.try_handle("sí")
        self.assertTrue(handled)
        self.assertEqual(self.executed, [])
        self.assertIn("venc", reply.lower())

    def test_cancelar_por_voz(self):
        from brain.local_intents import local_intents
        set_channel("voz", "voz-local")
        local_intents.request_confirmation("restart")
        handled, reply = local_intents.try_handle("no, mejor no")
        self.assertTrue(handled)
        self.assertEqual(self.executed, [])
        self.assertIn("cancelado", reply.lower())

    def test_telegram_no_confirma_lo_de_voz(self):
        """El ataque que motivó P0-3: 'dale' por Telegram no confirma el
        apagado pedido por voz, y el pedido de voz sigue intacto."""
        from brain.local_intents import local_intents
        from core.confirmation import confirmation_manager as mgr
        set_channel("voz", "voz-local")
        local_intents.request_confirmation("shutdown")

        set_channel("telegram", "telegram:999")
        handled, reply = local_intents.try_handle("dale")

        self.assertEqual(self.executed, [])
        # El pendiente de voz sigue ahí, esperando confirmación por voz.
        self.assertIsNotNone(mgr.get_pending("voz", "voz-local"))
        self.assertIsNone(mgr.get_pending("telegram", "telegram:999"))

    def test_telegram_confirma_lo_de_telegram(self):
        from brain.local_intents import local_intents
        set_channel("telegram", "telegram:999")
        local_intents.request_confirmation("sleep")
        handled, reply = local_intents.try_handle("sí")
        self.assertTrue(handled)
        self.assertEqual(self.executed, [("sleep", {})])


if __name__ == "__main__":
    unittest.main()
