"""Base de SystemControl: __init__, audio y puente RPC a Windows."""

from core.logger import log_warning

import ctypes

import os

import psutil

from core.state_manager import state_mgr

from typing import Any, Dict, Optional


class SystemControlBase:

    def __init__(self):
        self._volume_interface = None
        self.max_session_temp: float = 0.0
        self.last_temp: Optional[float] = None
        self.thermal_alert_threshold: float = 80.0
        # B-26: bandera real de voz de Titán en la PC (antes la rama Windows
        # devolvía "comando recibido" sin tocar nada).
        self.pc_voice_enabled = False
        self._init_audio()
        # B-27: "priming" de psutil. cpu_percent(interval=None) compara contra
        # la llamada anterior; la primera siempre da 0.0 (sin muestra previa).
        # Se establece la línea base acá para que get_system_metrics devuelva
        # valores reales desde la primera telemetría (ambas variantes: global
        # y por núcleo, que psutil trackea por separado).
        try:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            pass

    def _init_audio(self):
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, "EndpointVolume"):
                self._volume_interface = speakers.EndpointVolume
            else:
                from pycaw.pycaw import IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._volume_interface = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        except Exception as e:
            log_warning(f"No se pudo enlazar con pycaw directamente: {e}")

    def _remote_exec_if_linux(self, action: str, args: dict, success_msg: str) -> Optional[Dict[str, Any]]:
        """Si corre en Linux (servidor DDR3), delega la acción a cualquier satélite Windows conectado vía WebSocket RPC bidireccional."""
        if os.name != 'nt':
            try:
                from server.websocket_hub import ws_hub
                if ws_hub.has_windows_satellite():
                    loop = getattr(state_mgr, "_loop", None)
                    if loop and loop.is_running():
                        import asyncio

                        # Prevenir deadlock: si la llamada se hizo sincrónicamente desde el hilo del event loop
                        try:
                            current_loop = asyncio.get_running_loop()
                        except RuntimeError:
                            current_loop = None

                        if current_loop is loop:
                            # Estamos en el hilo del event loop: NO podemos bloquear con fut.result()
                            log_warning(f"[RPC] _remote_exec_if_linux llamado sincrónicamente desde el event loop para '{action}'. Disparando en background.")
                            asyncio.create_task(ws_hub.call_remote(action, args, timeout=15.0))
                            state_mgr.emit_tool_call(action, args, success_msg)
                            return {"status": "pending", "message": success_msg}

                        fut = asyncio.run_coroutine_threadsafe(
                            ws_hub.call_remote(action, args, timeout=15.0), loop
                        )
                        try:
                            result = fut.result(timeout=16.0)
                            if not isinstance(result, dict):
                                result = {"status": "success", "message": str(result)}
                            msg = result.get("message", success_msg)
                            state_mgr.emit_tool_call(action, args, msg)
                            res = dict(result)
                            if "message" not in res:
                                res["message"] = msg
                            if "status" not in res:
                                res["status"] = "success"
                            return res
                        except Exception as e:
                            log_warning(f"[RPC] Error esperando respuesta del satélite para '{action}': {e}")
                            error_msg = f"El satélite Windows no confirmó la operación '{action}'."
                            state_mgr.emit_tool_call(action, args, error_msg)
                            return {"status": "timeout", "message": error_msg}
                    else:
                        # Sin loop activo: fallback fire-and-forget
                        state_mgr._notify({
                            "type": "remote_exec",
                            "action": action,
                            "args": args
                        })
                        state_mgr.emit_tool_call(action, args, success_msg)
                        return {"status": "success", "message": success_msg}
                else:
                    return {
                        "status": "warning",
                        "message": "Che, no detecto la compu principal conectada para ejecutar esa orden. Asegurate de tener Titán abierto en Windows."
                    }
            except Exception as e:
                log_warning(f"Error delegando acción remota {action}: {e}")
        return None
