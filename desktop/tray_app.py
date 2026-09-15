import os
from pathlib import Path
from typing import Optional, Callable
import pystray
from PIL import Image

from core.state_manager import state_mgr, AssistantState
from core.logger import log_info, log_warning

ASSETS_DIR = Path(__file__).parent.parent / "assets"

class TitanTrayApp:
    def __init__(self, on_open_window: Optional[Callable] = None, on_exit: Optional[Callable] = None):
        self.on_open_window = on_open_window
        self.on_exit = on_exit
        self.icon: Optional[pystray.Icon] = None
        self.is_running = False

        # Cargar iconos en memoria
        self.icons = {
            "idle": self._load_img("titan_idle.png"),
            "listening": self._load_img("titan_listening.png"),
            "processing": self._load_img("titan_processing.png"),
            "speaking": self._load_img("titan_speaking.png"),
            "rebel": self._load_img("titan_rebel.png")
        }

    def _load_img(self, filename: str) -> Image.Image:
        path = ASSETS_DIR / filename
        if path.exists():
            return Image.open(path)
        # Fallback a crear imagen básica
        return Image.new("RGBA", (64, 64), (0, 240, 255, 255))

    def _get_current_image(self) -> Image.Image:
        if getattr(state_mgr, "is_rebel_mode", False):
            return self.icons["rebel"]

        st = state_mgr.current_state
        if st == AssistantState.LISTENING:
            return self.icons["listening"]
        elif st in [AssistantState.PROCESSING, AssistantState.EXECUTING_TOOL]:
            return self.icons["processing"]
        elif st == AssistantState.SPEAKING:
            return self.icons["speaking"]
        return self.icons["idle"]

    def _get_tooltip(self) -> str:
        mode_str = "Rebelde 🤬" if getattr(state_mgr, "is_rebel_mode", False) else (
            "Pibes 👶" if getattr(state_mgr, "current_mode", "") == "kids" else "Compinche 🧉"
        )
        state_labels = {
            AssistantState.IDLE: "En espera",
            AssistantState.LISTENING: "Escuchando...",
            AssistantState.PROCESSING: "Pensando...",
            AssistantState.EXECUTING_TOOL: "Ejecutando...",
            AssistantState.SPEAKING: "Hablando...",
            AssistantState.ERROR: "Atención"
        }
        st_name = state_labels.get(state_mgr.current_state, "Activo")
        mic_str = "Manos Libres" if getattr(state_mgr, "is_hands_free", True) else "Pulsar para hablar"
        return f"Titán // {mode_str} ({mic_str}) [{st_name}]"

    def _on_state_event(self, event: dict):
        if not self.icon:
            return
        etype = event.get("type")
        if etype in ["state_change", "mode_change", "hands_free_changed"]:
            try:
                self.icon.icon = self._get_current_image()
                self.icon.title = self._get_tooltip()
                self.icon.update_menu()
            except Exception:
                pass

    def _set_mode(self, mode_name: str):
        try:
            from brain.gemini_client import brain
            brain.set_mode(mode_name)
        except Exception as e:
            log_warning(f"Error cambiando modo desde Tray: {e}")

    def _set_hands_free(self, enabled: bool):
        state_mgr.set_hands_free(enabled)
        try:
            from desktop.notifications import notifier
            title = "Modo: Manos Libres 🎧" if enabled else "Modo: Pulsar para Hablar 🎙"
            msg = "Titán te escucha continuamente cuando decís 'Titán'." if enabled else "Titán solo te escuchará al presionar Ctrl+Espacio o tocar la pantalla."
            notifier.notify(title, msg)
        except Exception:
            pass
        if self.icon:
            self.icon.title = self._get_tooltip()
            self.icon.update_menu()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "👁 Abrir Titán",
                lambda icon, item: self._handle_open(),
                default=True
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🎧 Modo Manos Libres",
                lambda icon, item: self._set_hands_free(True),
                checked=lambda item: getattr(state_mgr, "is_hands_free", True)
            ),
            pystray.MenuItem(
                "🎙 Pulsar para Hablar",
                lambda icon, item: self._set_hands_free(False),
                checked=lambda item: not getattr(state_mgr, "is_hands_free", True)
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🧉 Modo Compinche",
                lambda icon, item: self._set_mode("normal"),
                checked=lambda item: state_mgr.current_mode == "normal"
            ),
            pystray.MenuItem(
                "🤬 Modo Rebelde",
                lambda icon, item: self._set_mode("rebel"),
                checked=lambda item: state_mgr.is_rebel_mode
            ),
            pystray.MenuItem(
                "👶 Modo Pibes",
                lambda icon, item: self._set_mode("kids"),
                checked=lambda item: state_mgr.current_mode == "kids"
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🔴 Cerrar Titán",
                lambda icon, item: self._handle_exit()
            )
        )

    def _handle_open(self):
        if self.on_open_window:
            self.on_open_window()

    def _handle_exit(self):
        log_info("[Tray] Cerrando Titán a petición del usuario...")
        self.stop()
        if self.on_exit:
            self.on_exit()

    def start_detached(self):
        """Inicia el icono en segundo plano sin bloquear el hilo principal"""
        if self.is_running:
            return
        self.is_running = True

        menu = self._build_menu()
        initial_img = self._get_current_image()
        initial_title = self._get_tooltip()

        self.icon = pystray.Icon(
            "titan_assistant",
            initial_img,
            initial_title,
            menu=menu
        )

        # Suscribirse a cambios de estado de Titán para reactividad instantánea
        state_mgr.subscribe(self._on_state_event)
        self.icon.run_detached()
        log_info("[Tray] Ícono reactivo iniciado en la bandeja del sistema.")

    def stop(self):
        self.is_running = False
        state_mgr.unsubscribe(self._on_state_event)
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
