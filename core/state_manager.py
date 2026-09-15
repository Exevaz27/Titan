import asyncio
from collections import deque
from datetime import datetime
from typing import Callable, List, Dict, Any, Optional, Tuple
from core.logger import log_state

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
        self.current_mode: str = "normal"  # "normal" | "rebel" | "kids" | "tertulia"
        self.is_rebel_mode: bool = False
        self.is_hands_free: bool = True  # True: Manos libres (voz continua) | False: Pulsar para hablar (manual)
        import time
        self.last_speaker: Dict[str, Any] = {"type": "desconocido", "pitch": None}
        self.last_speaker_time: float = 0.0
        self.last_activity_time: float = self._load_last_activity()
        self.inactivity_stage: str = "idle"
        self._inactivity_task: Optional[asyncio.Task] = None

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
        if state != AssistantState.IDLE and self.inactivity_stage not in ["mate", "drowsy", "sleeping"]:
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
        if not is_rest_cmd and self.inactivity_stage not in ["mate", "drowsy", "sleeping"]:
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

    def emit_stage(self, stage: str):
        """Notifica cambio de etapa de animación/reposo ('mate', 'drowsy', 'sleeping', 'wake', 'idle') a todas las pantallas"""
        import time
        if stage in ["mate", "drowsy", "sleeping", "idle"]:
            self.inactivity_stage = stage
            if stage == "sleeping":
                self.last_activity_time = time.time() - 2750
                self._save_last_activity(self.last_activity_time)
            elif stage == "drowsy":
                self.last_activity_time = time.time() - 1850
                self._save_last_activity(self.last_activity_time)
            elif stage == "mate":
                self.last_activity_time = time.time() - 950
                self._save_last_activity(self.last_activity_time)
        elif stage == "wake":
            self.inactivity_stage = "idle"
            self.last_activity_time = time.time()
            self._save_last_activity(self.last_activity_time)

        self._notify({
            "type": "set_stage",
            "stage": stage,
            "timestamp": datetime.now().isoformat()
        })

    def set_inactivity_stage(self, stage: str):
        """Alias para forzar o actualizar la etapa de animación/reposo"""
        self.emit_stage(stage)

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
        import time
        idle_sec = max(0, int(time.time() - self.last_activity_time))
        target_stage = "idle"
        if idle_sec >= 2700:
            target_stage = "sleeping"
        elif idle_sec >= 1800:
            target_stage = "drowsy"
        elif idle_sec >= 900:
            target_stage = "mate"

        # Si el usuario o el sistema ya había establecido un reposo explícito (mate/drowsy/sleeping),
        # no degradar a idle a menos que haya habido record_activity explícito
        if self.inactivity_stage in ["mate", "drowsy", "sleeping"]:
            stages_rank = {"idle": 0, "mate": 1, "drowsy": 2, "sleeping": 3}
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
        valid_modes = ["normal", "rebel", "kids", "tertulia"]
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
            "history": list(self.history)[-30:]  # últimos 30 eventos (deque → list para slicing)
        }

# Instancia global
state_mgr = StateManager()

