import os
import time
import json
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
        self._saved_spotify_volume = None
        self._lock = threading.Lock()
        self._cli_path = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        self._failsafe_timer: threading.Timer = None

    def _read_spotify_volume(self):
        """R-13: lee el volumen real de Spotify (0.0-1.0) antes de atenuar.
        Retorna None si no se puede determinar."""
        try:
            res = run_silent(
                [self._cli_path, "devices", "--format", "json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
            )
            if res.stdout:
                data = json.loads(res.stdout)
                for d in data.get("devices", []):
                    if d.get("is_active") or d.get("is_self"):
                        v = d.get("volume")
                        if v is not None:
                            return max(0.0, min(1.0, float(v) / 100.0))
        except Exception:
            pass
        return None

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
                        # R-13: guardar el volumen REAL de Spotify antes de
                        # atenuar, para restaurarlo después (antes se
                        # restauraba un 0.8 fijo, ignorando el volumen previo).
                        self._saved_spotify_volume = self._read_spotify_volume()
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
                        # R-13: restaurar el volumen previo real; 0.8 solo como
                        # último recurso si no se pudo leer al atenuar.
                        restore_vol = self._saved_spotify_volume if self._saved_spotify_volume is not None else 0.8
                        self._saved_spotify_volume = None
                        run_silent(
                            [self._cli_path, "volume", str(restore_vol)],
                            capture_output=True,
                            timeout=0.6
                        )
                    except Exception:
                        pass

                self._is_ducked = False

            except Exception as e:
                log_warning(f"[Audio Ducking] Error al restaurar volumen: {e}")

    def is_media_active(self) -> bool:
        """B-11: True si hay audio saliendo por los parlantes de la PC
        (música, YouTube, juegos). La DDR3 lo consulta por RPC porque en
        Linux pycaw no existe."""
        # 1. Pico del medidor de los parlantes (pycaw, Windows)
        try:
            import comtypes
            comtypes.CoInitialize()
            try:
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
                from comtypes import CLSCTX_ALL
                device = AudioUtilities.GetSpeakers()
                if device and device._dev:
                    meter = device._dev.Activate(
                        IAudioMeterInformation._iid_, CLSCTX_ALL, None
                    ).QueryInterface(IAudioMeterInformation)
                    if float(meter.GetPeakValue()) > 0.035:
                        return True
            finally:
                comtypes.CoUninitialize()
        except Exception:
            pass
        # 2. Spotify sonando aunque el pico esté momentáneamente bajo
        try:
            if os.path.exists(self._cli_path):
                res = run_silent(
                    [self._cli_path, "now-playing", "--format", "json"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=1.0,
                )
                if res.stdout:
                    data = json.loads(res.stdout)
                    if data.get("currently_playing", {}).get("is_playing"):
                        return True
        except Exception:
            pass
        return False

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
