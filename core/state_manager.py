import asyncio
from collections import deque
from datetime import datetime
from typing import Callable, List, Dict, Any, Optional, Tuple
from core.logger import log_state

# Versión de assets del HUD (CSS/JS). Se publica en init_snapshot para que el
# J2 detecte si quedó con archivos viejos en caché y se recargue solo.
# FIX 2026-09-23 (bug pava del mate). Subir en cada cambio a server/static/.
ASSET_VERSION = 67

# Bebidas del modo bebidas (bien de barrio, del pico). FIX 2026-09-23.
BEBIDAS_DRINKS = ["fernet", "birra", "vino"]

def is_weekend_night(now=None):
    """True viernes/sábado/domingo de 20:00 a 04:00 (noche de finde).

    Python weekday(): lunes=0 ... domingo=6.
    """
    import datetime
    now = now or datetime.datetime.now()
    day, h = now.weekday(), now.hour
    return ((day == 4 and h >= 20) or (day == 5 and (h < 4 or h >= 20))
            or (day == 6 and (h < 4 or h >= 20)) or (day == 0 and h < 4))

class AssistantState:
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"

class StateManager:
    def __init__(self):
        self.current_state: str = AssistantState.IDLE
        self.state_detail: str = "En espera de activación"
        self.subscribers: List[Callable[[Dict[str, Any]], Any]] = []
        # deque con cap fijo: nunca puede crecer más de 100 entradas, O(1) append/trim
        self.history: deque = deque(maxlen=100)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.current_mode: str = "normal"  # "normal" | "rebel" | "kids" | "termo"
        self.is_rebel_mode: bool = False
        self.is_hands_free: bool = True  # True: Manos libres (voz continua) | False: Pulsar para hablar (manual)
        import time
        self.last_speaker: Dict[str, Any] = {"type": "desconocido", "pitch": None}
        self.last_speaker_time: float = 0.0
        self.last_activity_time: float = self._load_last_activity()
        self.inactivity_stage: str = "idle"
        # Bebida actual del modo bebidas (None si no está en esa etapa).
        # FIX 2026-09-23 (modo bebidas).
        self.current_drink: Optional[str] = None
        self._inactivity_task: Optional[asyncio.Task] = None
        # Etapa diferida: un intent puede pedir el cambio de etapa para DESPUÉS
        # de que Titán termine de hablar (evita que la cara de mate/dormido
        # aparezca mientras todavía está diciendo el aviso por voz).
        self._pending_stage: Optional[str] = None

    def _get_activity_cache_path(self):
        try:
            from core.config import config
            return config.base_dir / ".last_activity"
        except Exception:
            return None

    def _load_last_activity(self) -> float:
        import time
        try:
            p = self._get_activity_cache_path()
            if p and p.exists():
                val = float(p.read_text(encoding="utf-8").strip())
                if 0 < val <= time.time():
                    return val
        except Exception:
            pass
        return time.time()

    def _save_last_activity(self, t: float):
        try:
            p = self._get_activity_cache_path()
            if p:
                p.write_text(str(t), encoding="utf-8")
        except Exception:
            pass

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self.start_inactivity_monitor(loop)

    def subscribe(self, callback: Callable[[Dict[str, Any]], Any]):
        """Registra un callback (usado por el hub de WebSockets)"""
        if callback not in self.subscribers:
            self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Dict[str, Any]], Any]):
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def _notify(self, event: Dict[str, Any]):
        """Notifica a todos los suscriptores (asíncronos y síncronos)"""
        for callback in self.subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(callback(event), self._loop)
                    else:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(callback(event))
                        except RuntimeError:
                            # Sin bucle de eventos activo en este contexto
                            pass
                else:
                    callback(event)
            except Exception:
                pass

    def set_state(self, state: str, detail: str = ""):
        # FIX 2026-09-23 (bug pava del mate): se quitó la guarda que impedía
        # despertar desde las etapas mate/drowsy/sleeping. Esa guarda hacía que,
        # una vez activa la etapa mate, nada la limpiara jamás: la pava quedaba
        # fija en la pantalla del J2 para siempre. Cualquier actividad de Titán
        # despierta la etapa de inactividad.
        if state != AssistantState.IDLE:
            self.record_activity(trigger_wake=True)
        self.current_state = state
        self.state_detail = detail
        log_state(state, detail)
        
        event = {
            "type": "state_change",
            "state": state,
            "detail": detail,
            "timestamp": datetime.now().isoformat()
        }
        self._notify(event)

    def add_user_message(self, text: str):
        # Solo disparar despertar si no es una orden explícita de descanso o reposo
        norm = text.lower()
        is_rest_cmd = any(w in norm for w in ["mate", "descans", "dormi", "mimir", "siesta", "pausa", "amargo"])
        # FIX 2026-09-23 (bug pava del mate): se quitó la guarda
        # "inactivity_stage not in ['mate','drowsy','sleeping']". Con esa guarda,
        # una vez activa la etapa mate el habla del usuario nunca la limpiaba.
        # El chequeo is_rest_cmd ya alcanza: una orden de descanso no despierta,
        # todo lo demás sí, sin importar la etapa actual.
        if not is_rest_cmd:
            self.record_activity(trigger_wake=True)
        entry = {
            "type": "user_speech",
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
        self.history.append(entry)  # deque(maxlen=100) descarta el más viejo automáticamente
        self._notify(entry)

    def add_assistant_message(self, text: str):
        entry = {
            "type": "assistant_speech",
            "text": text,
            "timestamp": datetime.now().isoformat()
        }
        self.history.append(entry)
        self._notify(entry)

    def emit_tool_call(self, tool_name: str, args: Dict[str, Any], result: Any = None):
        entry = {
            "type": "tool_execution",
            "tool": tool_name,
            "args": args,
            "result": str(result) if result is not None else None,
            "timestamp": datetime.now().isoformat()
        }
        self.history.append(entry)
        self._notify(entry)


    def emit_audio_level(self, level: float):
        """Emite nivel de volumen para el visualizador del HUD (0.0 a 1.0)"""
        self._notify({
            "type": "audio_level",
            "level": level
        })

    def emit_speech_level(self, level: float):
        """Emite nivel de volumen del habla del asistente en tiempo real para sincronización labial exacta"""
        self._notify({
            "type": "speech_level",
            "level": round(level, 3)
        })

    def emit_view_switch(self, view_name: str):
        """Notifica cambio de vista (face, orb, telemetry) a todas las pantallas"""
        self._notify({
            "type": "switch_view",
            "view": view_name
        })

    def emit_stage(self, stage: str, drink: Optional[str] = None):
        """Notifica cambio de etapa de animación/reposo ('mate', 'bebidas', 'drowsy',
        'sleeping', 'wake', 'idle') a todas las pantallas.

        drink: en etapa 'bebidas', cuál de BEBIDAS_DRINKS ("fernet"|"birra"|"vino").
        Si no se pasa, se usa la actual o se elige una al azar.
        FIX 2026-09-23 (modo bebidas).
        """
        import time, random
        # Un cambio explícito de etapa cancela cualquier etapa diferida
        # pendiente (ej: "despertate" pisa un mate diferido no aplicado).
        self._pending_stage = None
        if stage in ["mate", "bebidas", "drowsy", "sleeping", "idle"]:
            self.inactivity_stage = stage
            if stage == "sleeping":
                self.last_activity_time = time.time() - 2750
                self._save_last_activity(self.last_activity_time)
            elif stage == "drowsy":
                self.last_activity_time = time.time() - 1850
                self._save_last_activity(self.last_activity_time)
            elif stage in ("mate", "bebidas"):
                self.last_activity_time = time.time() - 950
                self._save_last_activity(self.last_activity_time)
            if stage == "bebidas":
                if drink not in BEBIDAS_DRINKS:
                    drink = self.current_drink if self.current_drink in BEBIDAS_DRINKS else random.choice(BEBIDAS_DRINKS)
                self.current_drink = drink
            else:
                self.current_drink = None
        elif stage == "wake":
            self.inactivity_stage = "idle"
            self.current_drink = None
            self.last_activity_time = time.time()
            self._save_last_activity(self.last_activity_time)

        self._notify({
            "type": "set_stage",
            "stage": stage,
            "drink": self.current_drink,
            "timestamp": datetime.now().isoformat()
        })

    def set_inactivity_stage(self, stage: str):
        """Alias para forzar o actualizar la etapa de animación/reposo"""
        self.emit_stage(stage)

    def defer_stage(self, stage: str, drink: Optional[str] = None):
        """Guarda un cambio de etapa para aplicarlo cuando Titán termine de
        hablar (lo consume el caller después del tts.speak).

        drink: en "bebidas", la bebida elegida; se guarda como "bebidas:fernet".
        FIX 2026-09-23 (modo bebidas).
        """
        s = stage.lower().strip()
        if s == "bebidas" and drink in BEBIDAS_DRINKS:
            self._pending_stage = f"bebidas:{drink}"
        else:
            self._pending_stage = s

    def pop_pending_stage(self) -> Optional[str]:
        """Devuelve y limpia la etapa diferida (None si no hay ninguna)."""
        pending, self._pending_stage = self._pending_stage, None
        return pending

    def peek_pending_stage(self) -> Optional[str]:
        """Mira la etapa diferida sin limpiarla (None si no hay ninguna)."""
        return self._pending_stage

    def record_activity(self, trigger_wake: bool = True):
        import time
        self.last_activity_time = time.time()
        self._save_last_activity(self.last_activity_time)
        if self.inactivity_stage != "idle":
            self.inactivity_stage = "idle"
            if trigger_wake:
                self.emit_stage("wake")
            else:
                self.emit_stage("idle")

    def get_inactivity_status(self) -> Tuple[str, int]:
        import time, random
        idle_sec = max(0, int(time.time() - self.last_activity_time))
        target_stage = "idle"
        if idle_sec >= 2700:
            target_stage = "sleeping"
        elif idle_sec >= 1800:
            target_stage = "drowsy"
        elif idle_sec >= 900:
            # Noche de finde (vie/sáb/dom 20:00-04:00): en vez del mate,
            # Titán se toma algo bien de barrio. FIX 2026-09-23 (modo bebidas).
            if is_weekend_night():
                target_stage = "bebidas"
                if self.inactivity_stage != "bebidas":
                    self.current_drink = random.choice(BEBIDAS_DRINKS)
            else:
                target_stage = "mate"

        # Si el usuario o el sistema ya había establecido un reposo explícito (mate/bebidas/drowsy/sleeping),
        # no degradar a idle a menos que haya habido record_activity explícito
        if self.inactivity_stage in ["mate", "bebidas", "drowsy", "sleeping"]:
            stages_rank = {"idle": 0, "mate": 1, "bebidas": 1, "drowsy": 2, "sleeping": 3}
            current_rank = stages_rank.get(self.inactivity_stage, 0)
            target_rank = stages_rank.get(target_stage, 0)
            if target_rank > current_rank:
                self.inactivity_stage = target_stage
        else:
            self.inactivity_stage = target_stage

        return self.inactivity_stage, idle_sec

    def start_inactivity_monitor(self, loop: asyncio.AbstractEventLoop):
        if self._inactivity_task and not self._inactivity_task.done():
            return
        self._inactivity_task = loop.create_task(self._inactivity_loop())

    async def _inactivity_loop(self):
        while True:
            try:
                await asyncio.sleep(5.0)
                old_stage = self.inactivity_stage
                new_stage, _ = self.get_inactivity_status()
                if new_stage != old_stage:
                    self.emit_stage(new_stage)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5.0)

    def set_mode(self, mode: str):
        valid_modes = ["normal", "rebel", "kids", "termo", "pollera"]
        if mode not in valid_modes:
            mode = "normal"
        self.current_mode = mode
        self.is_rebel_mode = (mode == "rebel")
        self._notify({
            "type": "mode_change",
            "mode": self.current_mode,
            "is_rebel_mode": self.is_rebel_mode,
            "timestamp": datetime.now().isoformat()
        })

    def set_speaker(self, speaker_type: str, pitch_hz: Optional[float] = None):
        import time
        self.last_speaker_time = time.time()
        self.last_speaker = {"type": speaker_type, "pitch": pitch_hz}
        self._notify({
            "type": "speaker_detected",
            "speaker": speaker_type,
            "pitch": pitch_hz,
            "timestamp": datetime.now().isoformat()
        })

    def get_current_speaker(self) -> Dict[str, Any]:
        import time
        if time.time() - getattr(self, "last_speaker_time", 0) > 15:
            return {"type": "hombre", "pitch": None}
        return self.last_speaker

    def set_speaker_identity(self, identity: str, score: Optional[float] = None):
        """Huella de voz (2026-09-17, multi-voz 2026-09-18): nombre interno
        ('exequiel', 'oriana', ...) o 'desconocido'."""
        import time
        try:
            from audio.speaker_id import display_name
            disp = "Otra persona" if identity == "desconocido" else display_name(identity)
        except Exception:
            disp = identity
        self.last_speaker_identity = {"identity": identity, "score": score, "time": time.time()}
        self._notify({
            "type": "speaker_identity",
            "identity": identity,
            "display": disp,
            "score": score,
            "timestamp": datetime.now().isoformat()
        })

    def set_face_expression(self, expression: str, ttl: float = 6.0):
        """Expresión facial transitoria del modo pollera (2026-09-18):
        'retado' | 'enojado'. El HUD la aplica unos segundos y vuelve sola
        a la expresión base (que depende de quién habla)."""
        self._notify({
            "type": "face_expression",
            "expression": expression,
            "ttl": ttl,
            "timestamp": datetime.now().isoformat()
        })

    def set_hands_free(self, enabled: bool):
        self.is_hands_free = bool(enabled)
        self._notify({
            "type": "hands_free_changed",
            "enabled": self.is_hands_free,
            "timestamp": datetime.now().isoformat()
        })

    def get_snapshot(self) -> Dict[str, Any]:
        stage, idle_sec = self.get_inactivity_status()
        return {
            "state": self.current_state,
            "detail": self.state_detail,
            "current_mode": self.current_mode,
            "is_rebel_mode": self.is_rebel_mode,
            "is_hands_free": self.is_hands_free,
            "last_speaker": self.last_speaker,
            "inactivity_stage": stage,
            "idle_seconds": idle_sec,
            "current_drink": self.current_drink,
            "asset_version": ASSET_VERSION,
            "history": list(self.history)[-30:]  # últimos 30 eventos (deque → list para slicing)
        }

# Instancia global
state_mgr = StateManager()

