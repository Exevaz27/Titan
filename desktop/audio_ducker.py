import os
import time
import threading
import subprocess
from core.logger import log_info, log_warning
from core.process_utils import run_silent
from tools.system_control import system_control

class AudioDucker:
    def __init__(self, target_volume: int = 15, timeout_failsafe: float = 35.0):
        self.target_volume = target_volume
        self.timeout_failsafe = timeout_failsafe
        self._is_ducked = False
        self._saved_master_volume = None
        self._lock = threading.Lock()
        self._cli_path = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        self._failsafe_timer: threading.Timer = None

    def duck(self, target_percent: int = None):
        """Atenúa la música / audio general de Windows a un volumen bajo (por defecto 15%)"""
        target = target_percent if target_percent is not None else self.target_volume
        with self._lock:
            if self._is_ducked:
                self._reset_failsafe()
                return

            try:
                curr_vol = system_control.get_volume()
                if curr_vol > target:
                    self._saved_master_volume = curr_vol
                    system_control.set_volume_silent(target)
                    log_info(f"🔉 [Audio Ducking] Música y sonido atenuados: {curr_vol}% -> {target}%")
                else:
                    self._saved_master_volume = None

                if os.path.exists(self._cli_path):
                    try:
                        run_silent(
                            [self._cli_path, "volume", str(target / 100.0)],
                            capture_output=True,
                            timeout=0.6
                        )
                    except Exception:
                        pass

                self._is_ducked = True
                self._reset_failsafe()
            except Exception as e:
                log_warning(f"[Audio Ducking] Error al atenuar: {e}")

    def unduck(self):
        """Restaura el volumen original de Windows y Spotify"""
        with self._lock:
            if not self._is_ducked:
                return

            self._cancel_failsafe()
            try:
                if self._saved_master_volume is not None:
                    system_control.set_volume_silent(self._saved_master_volume)
                    log_info(f"🔊 [Audio Ducking] Volumen restaurado a {self._saved_master_volume}%")
                    self._saved_master_volume = None

                if os.path.exists(self._cli_path):
                    try:
                        run_silent(
                            [self._cli_path, "volume", "0.8"],
                            capture_output=True,
                            timeout=0.6
                        )
                    except Exception:
                        pass

                self._is_ducked = False

            except Exception as e:
                log_warning(f"[Audio Ducking] Error al restaurar volumen: {e}")

    def _reset_failsafe(self):
        self._cancel_failsafe()
        self._failsafe_timer = threading.Timer(self.timeout_failsafe, self._on_failsafe)
        self._failsafe_timer.daemon = True
        self._failsafe_timer.start()

    def _cancel_failsafe(self):
        if self._failsafe_timer and self._failsafe_timer.is_alive():
            self._failsafe_timer.cancel()
        self._failsafe_timer = None

    def _on_failsafe(self):
        log_info("[Audio Ducking] Failsafe timer activado: restaurando volumen por inactividad.")
        self.unduck()

audio_ducker = AudioDucker()
