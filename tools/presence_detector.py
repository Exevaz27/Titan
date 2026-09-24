import asyncio
import io
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from core.logger import log_info, log_warning, log_error, log_success
from core.state_manager import state_mgr, AssistantState
from tools.j2_camera import j2_camera
from server.websocket_hub import ws_hub
from audio.tts import tts
from brain.gemini_client import brain
from core.config import config

try:
    from PIL import Image
    import numpy as np
    HAS_VISION_LIBS = True
except ImportError:
    HAS_VISION_LIBS = False

# Zona horaria oficial de Argentina (UTC-3)
ART_TZ = timezone(timedelta(hours=-3))

class PresenceDetectorService:
    """
    Servicio de Detección de Presencia por Cámara Frontal (Samsung J2).
    - Monitorea la inactividad del usuario (ausencia > 5 minutos).
    - Realiza sondeos discretos cada 45s de la cámara frontal sin mantenerla abierta.
    - Utiliza prefiltro de diferencia de fotogramas y verificación con Gemini Flash-Lite.
    - Al detectar el regreso del usuario, lo saluda proactivamente por voz con acento argentino
      y envía un pulso de bienvenida (wake_pulse) a la pantalla del J2.
    - Respeta un cooldown anti-spam (por defecto 20 minutos) para evitar molestias.
    """

    def __init__(self):
        # DESACTIVADO por defecto (pedido del usuario 2026-09-15):
        # la cámara del J2 solo se usa cuando él la pide explícitamente
        # (vigilancia, foto) o cuando activa el sensor por voz/Telegram.
        self.enabled: bool = False
        self.absence_threshold: float = 300.0    # 5 minutos sin actividad para considerarse ausente
        self.check_interval: float = 45.0        # Sondeo cada 45s cuando está ausente
        self.cooldown_seconds: float = 1200.0    # 20 minutos de cooldown tras dar una bienvenida

        self.is_absent: bool = False
        self.last_activity_time: float = time.time()
        self.last_greeted_time: float = 0.0
        self.last_check_time: float = 0.0
        self.consecutive_empty_checks: int = 0

        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._last_frame_bytes: Optional[bytes] = None

    def record_user_activity(self):
        """Registra actividad del usuario (comando de voz, interacción con J2, Telegram, etc.)"""
        self.last_activity_time = time.time()
        if self.is_absent:
            log_info("[Sensor Presencia] Usuario detectado activo por interacción directa.")
            self.is_absent = False

    def start(self, loop: asyncio.AbstractEventLoop):
        """Inicia la tarea de fondo del detector de presencia"""
        if self._running:
            return
        self._running = True
        self._loop_task = loop.create_task(self._presence_loop())
        if self.enabled:
            log_success("[Sensor Presencia] Servicio de presencia frontal J2 iniciado.")
        else:
            log_success("[Sensor Presencia] Servicio iniciado con sensor automático DESACTIVADO (la cámara del J2 solo se usa a pedido).")

    def stop(self):
        """Detiene la tarea de fondo"""
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        log_info("[Sensor Presencia] Servicio de presencia detenido.")

    def enable(self) -> str:
        self.enabled = True
        self.record_user_activity()
        log_info("[Sensor Presencia] Sensor HABILITADO por el usuario.")
        return "Sensor de presencia frontal activado. Cuando vuelvas al escritorio te doy la bienvenida."

    def disable(self) -> str:
        self.enabled = False
        self._last_frame_bytes = None
        log_info("[Sensor Presencia] Sensor DESHABILITADO por el usuario.")
        return "Sensor de presencia frontal desactivado. Ya no voy a mirar la cámara frontal en reposo."

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        inactivity_sec = int(now - self.last_activity_time)
        time_since_greeted = int(now - self.last_greeted_time) if self.last_greeted_time > 0 else None
        in_cooldown = (now - self.last_greeted_time < self.cooldown_seconds) if self.last_greeted_time > 0 else False

        return {
            "enabled": self.enabled,
            "running": self._running,
            "is_absent": self.is_absent,
            "inactivity_seconds": inactivity_sec,
            "in_cooldown": in_cooldown,
            "seconds_since_last_greet": time_since_greeted,
            "cooldown_remaining_seconds": max(0, int(self.cooldown_seconds - (now - self.last_greeted_time))) if in_cooldown else 0,
            "active_hud_clients": len(ws_hub.active_connections)
        }

    async def _presence_loop(self):
        """Bucle periódico asíncrono con bajo consumo de CPU"""
        while self._running:
            try:
                await asyncio.sleep(5.0)

                if not self.enabled:
                    continue

                now = time.time()
                inactivity = now - self.last_activity_time

                # 1. Chequeo de paso a estado AUSENTE
                if not self.is_absent:
                    if inactivity >= self.absence_threshold:
                        self.is_absent = True
                        log_info(f"[Sensor Presencia] Usuario marcado como AUSENTE tras {inactivity/60:.1f} minutos sin actividad.")
                    else:
                        continue

                # 2. Solo sondear si el sistema está en IDLE (no interrumpe habla ni procesamiento)
                if state_mgr.current_state != AssistantState.IDLE:
                    continue

                # 3. Solo sondear cada check_interval
                if now - self.last_check_time < self.check_interval:
                    continue

                # 4. Si no hay clientes HUD (el J2 no está conectado), esperar
                if not ws_hub.active_connections:
                    continue

                self.last_check_time = now

                # 5. Ejecutar chequeo de presencia por cámara
                is_present, details = await self.check_presence()

                if is_present:
                    self.consecutive_empty_checks = 0

                    # Notificar al servicio de vigilancia si el Modo Centinela está activo
                    try:
                        from tools.surveillance_service import surveillance_service
                        if surveillance_service.sentry_mode and self._last_frame_bytes:
                            await surveillance_service.on_presence_detected(self._last_frame_bytes, details)
                    except Exception as e_sentry:
                        log_warning(f"[Sensor Presencia] Error alertando a vigilancia centinela: {e_sentry}")

                    time_since_greet = now - self.last_greeted_time

                    if time_since_greet >= self.cooldown_seconds:
                        log_success(f"[Sensor Presencia] ¡Usuario detectado frente al escritorio! ({details})")
                        await self.welcome_user()
                    else:
                        rem = int(self.cooldown_seconds - time_since_greet)
                        log_info(f"[Sensor Presencia] Usuario detectado, pero en cooldown anti-spam ({rem}s restantes).")
                        self.is_absent = False
                        self.last_activity_time = now
                else:
                    self.consecutive_empty_checks += 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"[Sensor Presencia] Error en bucle de presencia: {e}")
                await asyncio.sleep(10.0)

    def _compute_frame_difference(self, current_bytes: bytes) -> float:
        """Calcula la diferencia media de píxeles entre el cuadro actual y el anterior"""
        if not HAS_VISION_LIBS or not self._last_frame_bytes:
            return 999.0
        try:
            img1 = Image.open(io.BytesIO(self._last_frame_bytes)).convert("L").resize((64, 48))
            img2 = Image.open(io.BytesIO(current_bytes)).convert("L").resize((64, 48))
            arr1 = np.array(img1, dtype=np.int16)
            arr2 = np.array(img2, dtype=np.int16)
            return float(np.mean(np.abs(arr1 - arr2)))
        except Exception:
            return 999.0

    async def check_presence(self) -> Tuple[bool, str]:
        """Toma una foto con la cámara frontal del J2 y analiza si hay una persona frente al escritorio"""
        log_info("[Sensor Presencia] Verificando presencia con cámara frontal del J2...")

        # Captura discreta de 1 fotograma (el J2 apaga la cámara inmediatamente tras el disparo)
        photo_bytes = await j2_camera.capture_photo(facing_mode="user", timeout=6.0)
        if not photo_bytes:
            return False, "Fallo al obtener captura de la cámara frontal"

        # Prefiltro de movimiento: si la imagen es idéntica al cuadro vacío anterior, nadie se movió
        diff = self._compute_frame_difference(photo_bytes)
        self._last_frame_bytes = photo_bytes

        if diff < 4.5 and self.consecutive_empty_checks > 1:
            log_info(f"[Sensor Presencia] Sin cambios visuales respecto al fondo vacío (diff: {diff:.2f}).")
            return False, "Escritorio estático sin cambios"

        # Análisis visual con Gemini Flash-Lite
        return await self._analyze_presence_with_gemini(photo_bytes)

    async def _analyze_presence_with_gemini(self, photo_bytes: bytes) -> Tuple[bool, str]:
        """Consulta a Gemini Flash-Lite si hay una persona sentada o de pie frente al escritorio"""
        from google.genai import types

        if not brain.client:
            return False, "Cliente Gemini no inicializado"

        prompt = (
            "Analizá esta imagen tomada desde un celular apoyado en el escritorio con la cámara frontal "
            "apuntando hacia la silla o el espacio de trabajo. "
            "¿Hay una persona sentada frente al escritorio o acercándose al escritorio? "
            "Respondé ESTRICTAMENTE en formato JSON con la siguiente estructura y sin código markdown extra:\n"
            "{\"persona_presente\": true, \"confianza\": 0.9, \"descripcion\": \"persona sentada trabajando\"}\n"
            "Si el asiento está vacío, no hay nadie visible o solo hay objetos/ropa inanimada, devolvé persona_presente: false."
        )

        image_part = types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg")
        candidates = [config.gemini_model or "gemini-2.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.0-flash-lite"]

        loop = asyncio.get_running_loop()

        for model_name in candidates:
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda m=model_name: brain.client.models.generate_content(
                        model=m,
                        contents=[image_part, prompt]
                    )
                )

                if resp and resp.text:
                    raw = resp.text.strip()
                    if raw.startswith("```json"):
                        raw = raw[7:]
                    if raw.startswith("```"):
                        raw = raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()

                    data = json.loads(raw)
                    is_present = bool(data.get("persona_presente", False))
                    confidence = float(data.get("confianza", 0.0))
                    desc = data.get("descripcion", "Sin detalle")

                    if is_present and confidence >= 0.65:
                        return True, f"Persona detectada ({desc}, confianza: {confidence:.2f})"
                    else:
                        return False, f"Escritorio vacío ({desc})"

            except Exception as e:
                log_warning(f"[Sensor Presencia] Error analizando con {model_name}: {e}")
                continue

        return False, "No se pudo clasificar la presencia visual"

    def get_contextual_welcome(self) -> str:
        """Genera un saludo proactivo en tono argentino acorde a la hora y modo activo"""
        now_art = datetime.now(ART_TZ)
        hour = now_art.hour
        mode = getattr(brain, "current_mode", "normal")

        # Saludos específicos según el modo
        if mode == "rebel":
            rebel_greetings = [
                "¡Al fin apareciste, loco! Ya pensé que te habías ido a vivir a otra galaxia. ¿Qué rompemos hoy?",
                "¡Epa, volvió el vago! Ya me estaba pudriendo de mirar la pared. ¿En qué andamos?",
                "¡Mirá quién volvió! Pensé que te habías tomado el palo. Decime qué hacés."
            ]
            import random
            return random.choice(rebel_greetings)

        if mode == "kids":
            kids_greetings = [
                "¡Hola Eze! ¡Qué bueno que volviste! ¿Jugamos a algo o me vas a hacer una pregunta?",
                "¡Exequiel! Ya estoy listo acá en la pantalla, ¿qué vamos a hacer hoy?"
            ]
            import random
            return random.choice(kids_greetings)

        if mode == "pollera":
            pollera_greetings = [
                "¡Buenas! Acá el pollerudo oficial de servicio. ¿La jefa necesita algo?",
                "¡Presente, fiera! En modo pollera: la patrona manda y yo obedezco.",
                "¡Qué hacés! Listo para servir a Orianita. ¿En qué andamos?",
            ]
            import random
            return random.choice(pollera_greetings)

        if mode == "termo":
            termo_greetings = [
                "¡Buenas fiera! Justo estaba repasando la táctica del Xeneize. ¿Listo para meter debate futbolero?",
                "¡Volvió el DT! Acomodate che, ¿qué opinás del partido que se viene?",
                "¡Qué hacés maestro! Firme en la mesa de café, contame qué se debate hoy."
            ]
            import random
            return random.choice(termo_greetings)

        # Modo Normal (Compinche) por franja horaria argentina
        import random
        if 6 <= hour < 12:
            morning_greetings = [
                "¡Buen día Ezequiel! ¿Cómo andás, papá? Mate en mano y al pie del cañón cuando me digas.",
                "¡Buenas mañanas fiera! Ya me acomodé acá en el escritorio, decime en qué te doy una mano.",
                "¡Buen día máquina! Firme acá listo para arrancar el día con todo. Decime nomás."
            ]
            return random.choice(morning_greetings)
        elif 12 <= hour < 20:
            afternoon_greetings = [
                "¡Buenas tardes che! ¿Todo bien? Firme acá en el escritorio, decime qué hacemos.",
                "¡Qué hacés fiera! ¿Cómo viene esa tarde? Te escucho cuando quieras.",
                "¡Buenas tardes papá! Ya me acomodé, decime si necesitás una mano con la compu."
            ]
            return random.choice(afternoon_greetings)
        else:
            night_greetings = [
                "¡Buenas noches fiera! ¿En qué andamos hoy? Acá estoy atento a lo que precises.",
                "¡Qué hacés che! Firme acá en el escritorio para meterle, decime nomás.",
                "¡Buenas noches papá! Al pie del cañón cuando quieras, ¿qué sale hoy?"
            ]
            return random.choice(night_greetings)

    async def welcome_user(self):
        """Ejecuta la secuencia de bienvenida proactiva en el J2 y altavoces"""
        self.last_greeted_time = time.time()
        self.last_activity_time = time.time()
        self.is_absent = False

        greeting = self.get_contextual_welcome()

        # 1. Pulso visual alegre en el rostro del J2
        try:
            await ws_hub.broadcast_event({"type": "wake_pulse"})
        except Exception as e:
            log_warning(f"[Sensor Presencia] Error emitiendo wake_pulse al HUD: {e}")

        # 2. Síntesis de voz con animación labial
        log_info(f"[Sensor Presencia] Titán saluda: '{greeting}'")
        try:
            await tts.speak(greeting, auto_listen=True)
        except Exception as e:
            log_error(f"[Sensor Presencia] Error al reproducir saludo por voz: {e}")

presence_detector = PresenceDetectorService()
