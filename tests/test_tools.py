import unittest
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.app_launcher import app_launcher
from tools.file_manager import file_manager
from tools.system_control import system_control

class TestTools(unittest.TestCase):
    def test_app_launcher_catalog(self):
        """Verifica que el catálogo detecte las apps configuradas"""
        catalog = app_launcher.list_catalog_apps()
        self.assertIn("inkscape", catalog)
        match = app_launcher.find_app("inkscape")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "inkscape")

    def test_file_manager_search_and_trash(self):
        """Prueba búsqueda de archivos y envío a la papelera segura"""
        test_file = Path(__file__).resolve().parent / "temp_test_trash.txt"
        test_file.write_text("Prueba de archivo para el asistente", encoding="utf-8")
        self.assertTrue(test_file.exists())

        # Probar lectura
        read_res = file_manager.read_file_content(str(test_file))
        self.assertEqual(read_res["status"], "success")
        self.assertIn("Prueba", read_res["content"])

        # Probar trash
        trash_res = file_manager.trash_file(str(test_file))
        self.assertEqual(trash_res["status"], "success")
        self.assertFalse(test_file.exists())

    def test_system_metrics(self):
        """Prueba métricas de CPU, RAM y discos"""
        metrics = system_control.get_system_metrics()
        self.assertEqual(metrics["status"], "success")
        self.assertIn("cpu_percent", metrics)
        self.assertIn("ram_percent", metrics)
    def test_switch_screen_view(self):
        """Prueba conmutación de vistas de pantalla"""
        res_face = system_control.switch_screen_view("cara")
        self.assertEqual(res_face["active_view"], "face")

        res_telem = system_control.switch_screen_view("recursos")
        self.assertEqual(res_telem["active_view"], "telemetry")

        res_orb = system_control.switch_screen_view("control")
        self.assertEqual(res_orb["active_view"], "orb")

if __name__ == "__main__":
    unittest.main()
