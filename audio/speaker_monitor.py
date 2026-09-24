import os
import time
import json
import threading
import subprocess
from typing import Optional
from core.logger import log_info, log_warning
from core.process_utils import run_silent

class SpeakerMonitor:
    def __init__(self):
        self._cli_path = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        self._is_ducked = False
        self._saved_volume: float = 0.8
        self._last_duck_time: float = 0.0
        self._lock = threading.Lock()
        self._last_peak_check = 0.0
        self._cached_peak = 0.0
        self._last_spotify_check = 0.0
        self._cached_spotify_playing = False
        # B-11: en la DDR3 (Linux) pycaw no existe y la música suena en la PC
        # Windows, así que el valor viene del satélite (hilo poller, cacheado).
        self._cached_remote_media_active = False
        self._remote_media_poller_started = False

    def get_speaker_peak(self) -> float:
        """Retorna el pico actual del sonido que sale por los parlantes (0.0 a 1.0)"""
        now = time.time()
        if now - self._last_peak_check < 0.25:
            return self._cached_peak

        self._last_peak_check = now
        try:
            import comtypes
            comtypes.CoInitialize()
            try:
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
                from comtypes import CLSCTX_ALL
                device = AudioUtilities.GetSpeakers()
                if not device or not device._dev:
                    self._cached_peak = 0.0
                    return 0.0
                meter = device._dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None).QueryInterface(IAudioMeterInformation)
                self._cached_peak = float(meter.GetPeakValue())
            finally:
                comtypes.CoUninitialize()
        except Exception:
            self._cached_peak = 0.0
        return self._cached_peak

    def is_spotify_playing(self) -> bool:
        """Verifica si Spotify esta reproduciendo musica activamente"""
        now = time.time()
        if now - self._last_spotify_check < 0.5:
            return self._cached_spotify_playing

        self._last_spotify_check = now
        if not os.path.exists(self._cli_path):
            self._cached_spotify_playing = False
            return False

        try:
            res = run_silent(
                [self._cli_path, "now-playing", "--format", "json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0
            )
            if res.stdout:
                data = json.loads(res.stdout)
                self._cached_spotify_playing = bool(data.get("currently_playing", {}).get("is_playing", False))
            else:
                self._cached_spotify_playing = False
        except Exception:
            self._cached_spotify_playing = False
        return self._cached_spotify_playing

    def is_media_active(self) -> bool:
        """True si hay musica o sonido saliendo por los parlantes (Spotify, YouTube, juegos, etc.)"""
        if os.name == 'nt':
            return self.is_spotify_playing() or self.get_speaker_peak() > 0.035
        # B-11: en la DDR3 (Linux) pycaw no existe y la música suena en la PC
        # Windows → se usa el valor cacheado que reporta el satélite. Nunca
        # bloquea: es una simple lectura (seguro en cualquier hilo).
        self._ensure_remote_media_poller()
        return self._cached_remote_media_active

    def _ensure_remote_media_poller(self):
        """B-11: lanza (una sola vez) el hilo que pregunta al satélite cada 10s
        si hay audio sonando en la PC."""
        if self._remote_media_poller_started:
            return
        self._remote_media_poller_started = True
        t = threading.Thread(
            target=self._remote_media_poll_loop,
            name="titan-remote-media",
            daemon=True,
        )
        t.start()

    def _remote_media_poll_loop(self):
        """Hilo dedicado: consulta no bloqueante al satélite (este hilo SÍ
        puede esperar con fut.result(); nunca es el hilo del event loop)."""
        from core.state_manager import state_mgr
        from server.websocket_hub import ws_hub
        import asyncio
        loop = None
        while loop is None:
            loop = getattr(state_mgr, "_loop", None)
            if loop is None:
                time.sleep(1.0)
        while True:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    ws_hub.call_remote("is_media_active", {}, timeout=4.0),
                    loop,
                )
                res = fut.result(timeout=5.0)
                self._cached_remote_media_active = (
                    bool(res.get("media_active", False))
                    if isinstance(res, dict) else False
                )
            except Exception:
                # Satélite caído o sin respuesta → como antes del fix:
                # se asume que no hay música.
                self._cached_remote_media_active = False
            time.sleep(10.0)

    def duck(self, target_volume: float = 0.15):
        """Atenua la musica para que el microfono escuche al usuario con nitidez"""
        if os.name != 'nt':
            # B-11: no molestar al satélite atenuando si no hay música
            # sonando en la PC (antes se mandaba siempre).
            if not self.is_media_active():
                return
            try:
                from server.websocket_hub import ws_hub
                from core.state_manager import state_mgr
                loop = getattr(state_mgr, "_loop", None)
                if loop and loop.is_running():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        ws_hub.send_to_satellite({"type": "audio_duck", "action": "duck", "target": int(target_volume * 100)}),
                        loop
                    )
            except Exception:
                pass
            return

        with self._lock:
            if self._is_ducked:
                return

            if not os.path.exists(self._cli_path):
                return

            if not self.is_spotify_playing() and self.get_speaker_peak() < 0.02:
                return

            # Obtener volumen actual antes de atenuar
            saved_vol = 0.8
            try:
                res = run_silent(
                    [self._cli_path, "devices", "--format", "json"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=1.0
                )
                if res.stdout:
                    data = json.loads(res.stdout)
                    for d in data.get("devices", []):
                        if d.get("is_active") or d.get("is_self"):
                            v = d.get("volume")
                            if v is not None:
                                saved_vol = max(0.2, min(1.0, float(v) / 100.0))
                                break
            except Exception:
                pass

            self._saved_volume = saved_vol
            self._is_ducked = True
            self._last_duck_time = time.time()

            try:
                run_silent(
                    [self._cli_path, "volume", str(target_volume)],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                log_info(f"[Audio Ducking] Musica atenuada al {int(target_volume * 100)}% para escuchar con nitidez")
            except Exception as e:
                log_warning(f"[Audio Ducking] Error al atenuar musica: {e}")

    def unduck(self):
        """Restaura el volumen original de la musica"""
        if os.name != 'nt':
            try:
                from server.websocket_hub import ws_hub
                from core.state_manager import state_mgr
                loop = getattr(state_mgr, "_loop", None)
                if loop and loop.is_running():
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        ws_hub.send_to_satellite({"type": "audio_duck", "action": "unduck"}),
                        loop
                    )
            except Exception:
                pass
            return

        with self._lock:
            if not self._is_ducked:
                return

            self._is_ducked = False
            restore_vol = self._saved_volume or 0.8

            if os.path.exists(self._cli_path):
                try:
                    run_silent(
                        [self._cli_path, "volume", str(restore_vol)],
                        capture_output=True,
                        text=True,
                        timeout=1.0
                    )
                    log_info(f"[Audio Ducking] Volumen de musica restaurado al {int(restore_vol * 100)}%")
                except Exception as e:
                    log_warning(f"[Audio Ducking] Error al restaurar volumen: {e}")



speaker_monitor = SpeakerMonitor()
