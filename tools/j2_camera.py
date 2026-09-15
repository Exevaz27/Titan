import asyncio
import base64
import time
from typing import Dict, Any, Optional
from core.logger import log_info, log_warning, log_error

class J2CameraService:
    def __init__(self):
        # Modo de camara actual: 'environment' (trasera/habitacion) o 'user' (frontal/selfie)
        self.current_facing: str = "environment"
        self._pending_requests: Dict[str, asyncio.Future] = {}

    def toggle_facing(self) -> str:
        """Alterna entre la camara trasera (habitacion) y frontal (escritorio)"""
        self.current_facing = "user" if self.current_facing == "environment" else "environment"
        label = "FRONTAL (Escritorio / Silla)" if self.current_facing == "user" else "TRASERA (Habitacion / Puerta)"
        log_info(f"[J2 Camera] Camara cambiada a: {label}")
        return label

    def get_facing_label(self) -> str:
        return "FRONTAL (Escritorio)" if self.current_facing == "user" else "TRASERA (Habitacion)"

    async def capture_photo(self, facing_mode: Optional[str] = None, timeout: float = 8.0) -> Optional[bytes]:
        """Solicita una foto al Samsung J2 a traves de WebSocket y espera la respuesta en crudo (bytes JPEG)"""
        from server.websocket_hub import ws_hub

        if not ws_hub.active_connections:
            log_warning("[J2 Camera] No hay clientes HUD conectados al WebSocket (J2 desconectado)")
            return None

        target_facing = facing_mode or self.current_facing
        req_id = f"j2_cam_{int(time.time() * 1000)}"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        try:
            await ws_hub.broadcast_event({
                "type": "capture_j2_photo",
                "request_id": req_id,
                "facing_mode": target_facing
            })
            log_info(f"[J2 Camera] Solicitud de captura enviada ({target_facing}) [ID: {req_id}]")

            photo_bytes = await asyncio.wait_for(future, timeout=timeout)
            return photo_bytes

        except asyncio.TimeoutError:
            log_warning(f"[J2 Camera] Timeout ({timeout}s) esperando foto del J2 [ID: {req_id}]")
            return None
        except Exception as e:
            log_error(f"[J2 Camera] Error en captura: {e}")
            return None
        finally:
            self._pending_requests.pop(req_id, None)

    def handle_photo_result(self, data: Dict[str, Any]):
        """Procesa el resultado en Base64 enviado por el navegador del J2"""
        req_id = data.get("request_id")
        if not req_id or req_id not in self._pending_requests:
            return

        future = self._pending_requests[req_id]
        if future.done():
            return

        status = data.get("status", "success")
        if status != "success":
            err = data.get("error", "Error desconocido en J2")
            log_error(f"[J2 Camera] Error reportado por J2: {err}")
            future.set_exception(RuntimeError(err))
            return

        b64_str = data.get("image_base64", "")
        if not b64_str:
            future.set_exception(ValueError("Imagen vacia"))
            return

        try:
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            photo_bytes = base64.b64decode(b64_str)
            log_info(f"[J2 Camera] Foto recibida exitosamente ({len(photo_bytes) / 1024:.1f} KB)")
            future.set_result(photo_bytes)
        except Exception as e:
            log_error(f"[J2 Camera] Error decodificando base64: {e}")
            future.set_exception(e)

j2_camera = J2CameraService()
