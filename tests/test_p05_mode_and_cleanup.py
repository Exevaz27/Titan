"""P0-5 — Tests: freno central de modos restrictivos + limpieza de artefactos."""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.mode_policy import (
    actions_blocked,
    current_mode,
    telegram_callback_allowed,
    TELEGRAM_NAVIGATION_CALLBACKS,
)
from core.artifact_cleanup import ArtifactSpec, sweep_spec, sweep_all


class TestModePolicy(unittest.TestCase):
    def setUp(self):
        from brain.gemini_client import brain

        self._brain = brain
        self._prev = getattr(brain, "current_mode", "normal")

    def tearDown(self):
        self._brain.set_mode(self._prev if self._prev in ("normal", "rebel", "kids", "termo") else "normal")

    def test_normal_no_bloquea(self):
        self._brain.set_mode("normal")
        self.assertEqual(current_mode(), "normal")
        self.assertFalse(actions_blocked())

    def test_termo_no_bloquea(self):
        self._brain.set_mode("termo")
        self.assertFalse(actions_blocked())

    def test_rebel_bloquea(self):
        self._brain.set_mode("rebel")
        self.assertTrue(actions_blocked())

    def test_kids_bloquea(self):
        self._brain.set_mode("kids")
        self.assertTrue(actions_blocked())

    def test_callbacks_modo_siempre_permitidos(self):
        self._brain.set_mode("rebel")
        for mode in ("normal", "rebel", "kids", "termo"):
            self.assertTrue(telegram_callback_allowed(f"mode:{mode}"))

    def test_callbacks_navegacion_permitidos(self):
        self._brain.set_mode("rebel")
        for cb in TELEGRAM_NAVIGATION_CALLBACKS:
            self.assertTrue(telegram_callback_allowed(cb), cb)

    def test_callbacks_accion_bloqueados(self):
        self._brain.set_mode("rebel")
        bloqueados = [
            "power:sleep", "power:shutdown_confirm", "power:restart_confirm",
            "tv:power", "tv:volup", "tv:ch:6", "tv:youtube",
            "cmd:lock", "cmd:screenshot", "cmd:clipboard", "cmd:j2_photo",
            "cmd:status", "cmd:toggle_voice", "cmd:j2_toggle_cam",
            "vigilance:full", "vigilance:j2", "vigilance:pc", "vigilance:sentry_toggle",
            "confirm:abc123",
        ]
        for cb in bloqueados:
            self.assertFalse(telegram_callback_allowed(cb), cb)


class TestLocalIntentsRebel(unittest.TestCase):
    def setUp(self):
        from brain.gemini_client import brain
        from brain.local_intents import local_intents
        from core.confirmation import confirmation_manager, set_channel

        self._brain = brain
        self._prev = getattr(brain, "current_mode", "normal")
        self._intents = local_intents
        self._mgr = confirmation_manager
        self._mgr._by_id.clear()
        self._mgr._latest.clear()
        self._mgr._recently_expired.clear()
        set_channel("voz", "voz-local")

    def tearDown(self):
        self._brain.set_mode(self._prev if self._prev in ("normal", "rebel", "kids", "termo") else "normal")
        self._mgr._by_id.clear()
        self._mgr._latest.clear()
        self._mgr._recently_expired.clear()

    def test_rebel_no_ejecuta_intent_local(self):
        self._brain.set_mode("rebel")
        handled, reply = self._intents.try_handle("subí el volumen")
        self.assertEqual((handled, reply), (False, None))

    def test_rebel_no_ejecuta_consulta(self):
        # En rebelde hasta las consultas van a Gemini (que putea sin herramientas).
        self._brain.set_mode("rebel")
        handled, reply = self._intents.try_handle("qué hora es")
        self.assertEqual((handled, reply), (False, None))

    def test_rebel_permite_salir_por_voz(self):
        self._brain.set_mode("rebel")
        handled, reply = self._intents.try_handle("desactivá el modo rebelde")
        self.assertTrue(handled)
        self.assertEqual(self._brain.current_mode, "normal")

    def test_kids_no_ejecuta_intent_local(self):
        self._brain.set_mode("kids")
        handled, reply = self._intents.try_handle("abrí el bloc de notas")
        self.assertEqual((handled, reply), (False, None))

    def test_normal_sigue_ejecutando(self):
        self._brain.set_mode("normal")
        handled, reply = self._intents.try_handle("qué hora es")
        self.assertTrue(handled)
        self.assertIn("Son las", reply)

    def test_confirmacion_pendiente_no_ejecuta_en_rebel(self):
        # P0-3: pedir confirmación en modo normal...
        self._brain.set_mode("normal")
        self._intents.request_confirmation("empty_recycle_bin")
        self.assertIsNotNone(self._mgr.get_pending("voz", "voz-local"))
        # ...cambiar a rebelde y decir "dale": NO debe ejecutar.
        self._brain.set_mode("rebel")
        handled, reply = self._intents.try_handle("dale")
        self.assertEqual((handled, reply), (False, None))
        # La confirmación sigue pendiente (expira por TTL, no se ejecuta).
        self.assertIsNotNone(self._mgr.get_pending("voz", "voz-local"))


class TestArtifactCleanup(unittest.TestCase):
    def _make_files(self, directory: Path, names_ages):
        for name, age_days in names_ages:
            p = directory / name
            p.write_bytes(b"x" * 100)
            old = time.time() - age_days * 86400.0
            os.utime(p, (old, old))

    def test_ttl_borra_viejos_y_conserva_nuevos(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._make_files(d, [("captura_20200101.png", 60), ("captura_nueva.png", 1), ("otro.txt", 60)])
            spec = ArtifactSpec(
                name="t", directory=d, patterns=["captura_*.png"],
                ttl_days=30.0, max_bytes=10**9,
            )
            res = sweep_spec(spec)
            self.assertEqual(res["deleted"], 1)
            self.assertFalse((d / "captura_20200101.png").exists())
            self.assertTrue((d / "captura_nueva.png").exists())
            self.assertTrue((d / "otro.txt").exists())  # no matchea el patrón

    def test_tope_de_tamanio_borra_mas_viejos_primero(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            # 5 archivos de 100 bytes, tope de 250 → deben quedar los 2 más nuevos.
            self._make_files(d, [(f"captura_{i}.png", i) for i in range(5)])
            spec = ArtifactSpec(
                name="t", directory=d, patterns=["captura_*.png"],
                ttl_days=365.0, max_bytes=250,
            )
            res = sweep_spec(spec)
            self.assertEqual(res["deleted"], 3)
            restantes = sorted(p.name for p in d.glob("captura_*.png"))
            self.assertEqual(restantes, ["captura_0.png", "captura_1.png"])

    def test_directorio_inexistente_no_falla(self):
        spec = ArtifactSpec(
            name="t", directory=Path("/no/existe/titan_test_xyz"),
            patterns=["*"], ttl_days=1.0, max_bytes=10,
        )
        self.assertEqual(sweep_spec(spec), {"deleted": 0, "bytes_freed": 0})

    def test_plataforma_restringida_se_omite(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            self._make_files(d, [("captura_vieja.png", 60)])
            spec = ArtifactSpec(
                name="t", directory=d, patterns=["captura_*.png"],
                ttl_days=30.0, max_bytes=10**9,
                only_platform="sistema_inexistente",
            )
            res = sweep_spec(spec)
            self.assertEqual(res["deleted"], 0)
            self.assertTrue((d / "captura_vieja.png").exists())

    def test_sweep_all_devuelve_reporte(self):
        report = sweep_all([])
        self.assertEqual(report, {})


if __name__ == "__main__":
    unittest.main()
