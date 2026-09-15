try:
    import keyboard
except ImportError:
    keyboard = None
from core.config import config
from core.logger import log_info, log_error, log_warning

class HotkeyListener:
    def __init__(self):
        self._is_active = False

    def start(self, on_trigger_callback):
        """Inicia la captura de atajos de teclado globales en segundo plano"""
        if not keyboard:
            return
        hotkey_primary = config.hotkey
        hotkey_alt = config.settings.get("hotkey", {}).get("activacion_alternativa", "alt+a")

        def _handler():
            log_info("Atajo global presionado -> Activando asistente")
            on_trigger_callback()

        try:
            keyboard.add_hotkey(hotkey_primary, _handler)
            if hotkey_alt:
                keyboard.add_hotkey(hotkey_alt, _handler)
            self._is_active = True
            log_info(f"Atajos globales activos: '{hotkey_primary}' y '{hotkey_alt}'")
        except Exception as e:
            log_warning(f"No se pudieron registrar atajos de teclado globales (puede requerir permisos): {e}")

    def stop(self):
        if not keyboard:
            return
        try:
            keyboard.unhook_all_hotkeys()
            self._is_active = False
        except Exception:
            pass

hotkey_listener = HotkeyListener()
