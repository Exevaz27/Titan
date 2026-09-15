import asyncio
import os
import sys
import threading
import time
import webview
import ctypes

# Registrar AppUserModelID oficial para que la barra de tareas y Alt+Tab muestren el logo de Titán
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("titan.assistant.ai.v2")
except Exception:
    pass

from desktop.tray_app import TitanTrayApp
from desktop.window_manager import WindowManager
from desktop.notifications import notifier
from desktop.remote_satellite import TitanSatellite
from core.logger import log_info, log_success, log_warning
from core.config import config

class TitanDesktopApp:
    def __init__(self, start_hidden: bool = False):
        self.start_hidden = start_hidden
        server_host = os.getenv("TITAN_SERVER_HOST", "192.168.100.5")
        self.server_host = server_host
        self.window_mgr = WindowManager(port=config.server_port, host=server_host)
        self.tray = TitanTrayApp(
            on_open_window=self.open_window,
            on_exit=self.exit_app
        )
        self.satellite = TitanSatellite(host=server_host, port=config.server_port)
        self.satellite_thread = None
        self._is_terminating = False

    def _run_satellite(self):
        """Ejecuta el satélite de comunicación con el servidor Titán DDR3"""
        try:
            log_info(f"[Desktop] Conectando satélite a Titán en {self.server_host}:{config.server_port}...")
            asyncio.run(self.satellite.connect_and_listen())
        except Exception as e:
            if not self._is_terminating:
                log_warning(f"[Desktop] Excepción en satélite: {e}")

    def open_window(self):
        """Muestra y enfoca la ventana gráfica de Titán"""
        self.window_mgr.show()

    def exit_app(self):
        """Apaga ordenadamente todos los servicios y sale de la aplicación"""
        if self._is_terminating:
            return
        self._is_terminating = True
        log_info("[Desktop] Cerrando Titán y liberando recursos de Windows...")

        self.satellite.stop()
        self.tray.stop()
        self.window_mgr.destroy()

        def _force_exit():
            time.sleep(0.8)
            os._exit(0)

        threading.Thread(target=_force_exit, daemon=True).start()

    def run(self):
        # 1. Iniciar satélite en segundo plano
        self.satellite_thread = threading.Thread(target=self._run_satellite, daemon=True)
        self.satellite_thread.start()

        # 2. Iniciar icono en la bandeja del sistema
        self.tray.start_detached()

        # 3. Crear ventana gráfica nativa (WebView2)
        self.window_mgr.create_window(start_hidden=self.start_hidden)

        log_success(f"✅ Titán Satélite activo conectado a {self.server_host}.")
        notifier.notify("Titán está activo", f"Conectado al servidor DDR3 ({self.server_host}). Listo para música y órdenes.")

        # 4. Iniciar bucle de eventos GUI de Windows en el hilo principal
        try:
            webview.start(debug=False)
        except Exception as e:
            log_warning(f"[Desktop] Error en bucle GUI: {e}")
        finally:
            self.exit_app()

if __name__ == "__main__":
    # Si se invoca con --tray o --hidden arranca minimizado
    hidden = ("--tray" in sys.argv or "--hidden" in sys.argv)
    app = TitanDesktopApp(start_hidden=hidden)
    app.run()
