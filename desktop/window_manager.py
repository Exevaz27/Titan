import os
import time
import ctypes
import threading
from pathlib import Path
from typing import Optional
import webview

from desktop.notifications import notifier
from core.logger import log_info, log_warning

ASSETS_DIR = Path(__file__).parent.parent / "assets"
ICON_PATH = ASSETS_DIR / "titan.ico"

class WindowManager:
    def __init__(self, port: int = 8000, host: str = "192.168.100.5"):
        self.port = port
        self.host = host
        self.window: Optional[webview.Window] = None
        self._is_visible = False
        self._has_notified_minimize = False
        self._force_exit = False

    def create_window(self, start_hidden: bool = True) -> webview.Window:
        """Crea la ventana nativa de escritorio vinculada a la interfaz local o del servidor DDR3"""
        target_host = self.host or "127.0.0.1"
        self.window = webview.create_window(
            title="Titán // Asistente Virtual",
            url=f"http://{target_host}:{self.port}/",
            width=460,
            height=760,
            resizable=True,
            hidden=start_hidden,
            text_select=False,
            confirm_close=False
        )

        self._is_visible = not start_hidden
        self.window.events.closing += self._on_closing
        self.window.events.shown += self._on_shown
        return self.window

    def _apply_native_icon(self):
        """Aplica el icono .ico en la barra de título y la barra de tareas de Windows"""
        if not self.window or not ICON_PATH.exists():
            return
        try:
            time.sleep(0.4)
            if hasattr(self.window, "native") and self.window.native:
                hwnd = self.window.native.Handle.ToInt32()
                h_icon = ctypes.windll.user32.LoadImageW(
                    0, str(ICON_PATH), 1, 0, 0, 0x00000010 | 0x00008000
                )
                if h_icon and hwnd:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, h_icon)  # ICON_SMALL
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, h_icon)  # ICON_BIG
        except Exception as e:
            log_warning(f"No se pudo aplicar icono nativo a la ventana: {e}")

    def _on_shown(self):
        self._is_visible = True
        threading.Thread(target=self._apply_native_icon, daemon=True).start()

    def _on_closing(self):
        """Intercepta el botón de cerrar (X) para ocultar a la bandeja en lugar de matar el asistente"""
        if self._force_exit:
            return True  # Permite cerrar

        self.hide()

        # Notificar una vez para que el usuario sepa que Titán sigue activo
        if not self._has_notified_minimize:
            notifier.notify("Titán sigue activo", "Hacé clic en el ícono junto al reloj para abrirlo.")
            self._has_notified_minimize = True

        return False  # Cancela la destrucción de la ventana

    def show(self):
        if self.window:
            try:
                self.window.show()
                self.window.restore()
                self._is_visible = True
            except Exception as e:
                log_warning(f"Error mostrando ventana: {e}")

    def hide(self):
        if self.window:
            try:
                self.window.hide()
                self._is_visible = False
            except Exception as e:
                log_warning(f"Error ocultando ventana: {e}")

    def toggle(self):
        if self._is_visible:
            self.hide()
        else:
            self.show()

    def destroy(self):
        self._force_exit = True
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
            self.window = None
