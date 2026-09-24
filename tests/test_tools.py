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

    def test_organize_delega_al_satelite_en_linux(self):
        """organize_folder delega al satélite Windows en Linux (2026-09-23)"""
        import tools.file_manager as fm_mod
        llamadas = []
        orig = fm_mod.FileManager._remote_exec_if_linux
        fm_mod.FileManager._remote_exec_if_linux = lambda self, action, args, msg: llamadas.append((action, args)) or {"status": "success", "message": "ok"}
        try:
            # En Linux (este entorno) debe delegar, no resolver local
            res = file_manager.organize_folder("Downloads")
            self.assertEqual(res["status"], "success")
            self.assertEqual(len(llamadas), 1)
            self.assertEqual(llamadas[0][0], "organize_folder")
            self.assertEqual(llamadas[0][1], {"folder_name": "Downloads"})
        finally:
            fm_mod.FileManager._remote_exec_if_linux = orig

    def test_organize_folder_en_satelite_permitida(self):
        """El satélite Windows acepta la acción organize_folder (2026-09-23)"""
        src = Path(__file__).resolve().parent.parent / "desktop" / "remote_satellite.py"
        texto = src.read_text(encoding="utf-8")
        self.assertIn('"organize_folder"', texto)
        self.assertRegex(texto, r'elif action == "organize_folder"')

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

    def test_organize_stl_y_3mf_van_a_modelos_3d(self):
        """2026-09-24 (pedido de Exequiel): al ordenar, los .stl y .3mf van
        juntos a la carpeta 'Modelos 3D'."""
        import tempfile
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "pieza.stl").touch()
            (d / "modelo.3MF").touch()
            (d / "foto.png").touch()
            with mock.patch.object(file_manager, "_resolve_folder", return_value=d), \
                 mock.patch("os.name", "nt"):
                res = file_manager.organize_folder("Downloads")
            self.assertEqual(res["status"], "success")
            self.assertTrue((d / "Modelos 3D" / "pieza.stl").exists())
            self.assertTrue((d / "Modelos 3D" / "modelo.3MF").exists())
            self.assertTrue((d / "Imágenes" / "foto.png").exists())

if __name__ == "__main__":
    unittest.main()

