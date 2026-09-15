import asyncio
import base64
import os
import time
from typing import Dict, Any, Optional, Tuple
from core.logger import log_info, log_warning, log_error, log_success
from core.state_manager import state_mgr, AssistantState
from tools.j2_camera import j2_camera
from tools.system_control import system_control
from brain.gemini_client import brain

class SurveillanceService:
    """
    Servicio de Vigilancia y Seguridad del Escritorio (Telegram / J2 / Windows).
    - Orquesta inspecciones de la habitación mediante la cámara del Samsung J2 y Gemini Visión.
    - Captura el estado en vivo de la computadora Windows (captura de pantalla, tiempo de inactividad, bloqueo).
    - Emite reportes integrales por texto y notas de voz nativas de Telegram.
    - Administra el Modo Centinela (alertas proactivas a Telegram si detecta presencia o intrusos).
    """

    def __init__(self):
        self.sentry_mode: bool = False
        self.last_sentry_alert_time: float = 0.0
        self.sentry_cooldown_seconds: float = 180.0  # 3 minutos entre alertas de intrusión

    def enable_sentry(self) -> str:
        """Activa el Modo Centinela (alerta automática por Telegram si alguien entra a la habitación)"""
        self.sentry_mode = True
        log_info("[Vigilancia] Modo Centinela ACTIVADO.")
        return "Modo Centinela activado 🚨. Si el sensor de presencia detecta a alguien en tu habitación, te mando una alerta inmediata con foto a Telegram."

    def disable_sentry(self) -> str:
        """Desactiva el Modo Centinela"""
        self.sentry_mode = False
        log_info("[Vigilancia] Modo Centinela DESACTIVADO.")
        return "Modo Centinela desactivado 🛡️. Ya no te voy a enviar alertas automáticas de intrusión."

    def get_status(self) -> Dict[str, Any]:
        from server.websocket_hub import ws_hub
        return {
            "sentry_mode": self.sentry_mode,
            "j2_connected": len(ws_hub.active_connections) > 0,
            "windows_satellite_connected": ws_hub.has_windows_satellite() if hasattr(ws_hub, "has_windows_satellite") else False,
            "last_alert_time": self.last_sentry_alert_time
        }

    async def on_presence_detected(self, photo_bytes: bytes, details: str):
        """Llamado cuando el detector de presencia registra una persona frente al J2"""
        if not self.sentry_mode:
            return

        now = time.time()
        if now - self.last_sentry_alert_time < self.sentry_cooldown_seconds:
            log_info("[Vigilancia Centinela] Alerta omitida por cooldown reciente.")
            return

        self.last_sentry_alert_time = now
        log_warning(f"[Vigilancia Centinela] 🚨 ¡INTRUSO DETECTADO! Disparando alerta a Telegram: {details}")

        try:
            from integrations.telegram_bot import telegram_service
            caption = (
                "🚨 *¡ALERTA DE SEGURIDAD DE TITÁN!*\n\n"
                "Se detectó una persona frente a tu escritorio mientras estás ausente y el Modo Centinela está activo.\n"
                f"• Detalle IA: _{details}_\n\n"
                "Te adjunto la foto capturada en vivo por el Samsung J2."
            )
            await telegram_service.broadcast_photo(photo_bytes, caption=caption)
        except Exception as e:
            log_error(f"[Vigilancia Centinela] Error enviando alerta de intrusión a Telegram: {e}")

    async def get_j2_visual_report(self) -> Tuple[Optional[bytes], str]:
        """Captura foto con el J2 y genera análisis visual con Gemini"""
        photo_bytes = await j2_camera.capture_photo(timeout=8.0)
        if not photo_bytes:
            return None, "No se pudo obtener imagen del Samsung J2 (¿pantalla encendida y conectada al HUD?)."

        question = (
            "Actuá como Titán, el asistente compinche con tonada y personalidad argentina, vigilando la habitación o el escritorio del usuario. "
            "Analizá esta foto tomada desde la cámara del Samsung J2: "
            "1. ¿Hay personas o intrusos visibles? "
            "2. ¿Cómo está la luz (prendida, apagada, luz de día)? "
            "3. ¿Se ven puertas o cosas fuera de lugar o está todo en orden? "
            "Respondé en 2 o 3 oraciones concisas y directas para ser enviado como reporte de seguridad."
        )

        try:
            analysis = await brain.analyze_vision(photo_bytes, question=question)
            return photo_bytes, analysis
        except Exception as e:
            log_error(f"[Vigilancia] Error en análisis con Gemini Visión: {e}")
            return photo_bytes, "Foto capturada, pero ocurrió un problema al procesarla con IA."

    async def get_pc_surveillance(self) -> Tuple[Optional[bytes], Dict[str, Any]]:
        """Captura pantalla y telemetría de seguridad de Windows"""
        loop = asyncio.get_running_loop()

        # 1. Telemetría de seguridad (Inactividad, bloqueo, ventana)
        sec_info = await loop.run_in_executor(None, system_control.get_pc_security_info)

        # 2. Captura de pantalla
        scr_res = await loop.run_in_executor(None, system_control.take_screenshot)
        photo_bytes = None

        if scr_res.get("status") == "success":
            if scr_res.get("photo_base64"):
                try:
                    photo_bytes = base64.b64decode(scr_res["photo_base64"])
                except Exception:
                    pass
            elif scr_res.get("path") and os.path.exists(scr_res["path"]):
                try:
                    with open(scr_res["path"], "rb") as f:
                        photo_bytes = f.read()
                except Exception:
                    pass

        return photo_bytes, sec_info

    async def get_full_security_report(self) -> Dict[str, Any]:
        """Ejecuta inspección completa paralela: J2 + PC + Telemetría"""
        j2_task = asyncio.create_task(self.get_j2_visual_report())
        pc_task = asyncio.create_task(self.get_pc_surveillance())

        (j2_bytes, j2_text), (pc_bytes, pc_info) = await asyncio.gather(j2_task, pc_task)

        is_locked = pc_info.get("is_locked", False)
        idle_min = pc_info.get("idle_minutes", 0)
        active_win = pc_info.get("active_window", "Desconocida")

        pc_status_str = "BLOQUEADA 🔒" if is_locked else "ACTIVA / DESBLOQUEADA 🔓"

        # Conclusión hablada para nota de voz
        summary_spoken = (
            f"Che Eze, acá tenés el parte de seguridad. "
            f"En la pieza: {j2_text} "
            f"En la compu, la sesión está {pc_status_str.lower()}, "
            f"el último movimiento fue hace {idle_min} minutos y está en la ventana {active_win}. "
            f"Te mando las fotos para que te quedes tranquilo."
        )

        return {
            "j2_photo": j2_bytes,
            "j2_report": j2_text,
            "pc_photo": pc_bytes,
            "pc_info": pc_info,
            "summary_spoken": summary_spoken
        }

surveillance_service = SurveillanceService()
