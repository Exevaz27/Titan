import asyncio
import threading
import time
from typing import Dict, Any, List
from core.logger import log_info, log_warning, log_error

class TitanScheduler:
    def __init__(self):
        self.timers: Dict[str, Any] = {}
        self._cancel_flags: Dict[str, bool] = {}

    def set_timer(self, minutes: float, label: str = "Temporizador") -> str:
        """Programa un temporizador que sonará en la PC y enviará alerta por Telegram al cumplirse el tiempo"""
        if minutes <= 0:
            return "El tiempo tiene que ser mayor a 0 minutos, che."
        
        timer_id = f"{label}_{int(time.time())}"
        self._cancel_flags[timer_id] = False

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._timer_worker(minutes, label, timer_id))
            self.timers[timer_id] = task
        except RuntimeError:
            def run_timer():
                asyncio.run(self._timer_worker(minutes, label, timer_id))
            t = threading.Thread(target=run_timer, daemon=True)
            t.start()
            self.timers[timer_id] = t

        log_info(f"[Scheduler] Temporizador creado: '{label}' para dentro de {minutes} min")
        return f"¡Listo, máquina! Te puse el temporizador de {minutes} minutos para '{label}'. Te pego el grito cuando esté."

    async def _timer_worker(self, minutes: float, label: str, timer_id: str):
        try:
            total_seconds = minutes * 60.0
            # Dormir en bloques de 1s para chequear cancelación rápida
            elapsed = 0.0
            while elapsed < total_seconds:
                if self._cancel_flags.get(timer_id, False):
                    log_info(f"[Scheduler] Temporizador '{label}' cancelado por bandera")
                    return
                await asyncio.sleep(min(1.0, total_seconds - elapsed))
                elapsed += 1.0

            if self._cancel_flags.get(timer_id, False):
                return
            
            # 1. Alerta por voz en los parlantes de la PC
            msg = f"¡Atención, papá! Se cumplieron los {minutes} minutos de: {label}."
            try:
                from audio.tts import tts
                await tts.speak(msg)
            except Exception as ex:
                log_warning(f"Fallo voz local en timer: {ex}")

            # 2. Alerta urgente en Telegram (Voz y Texto)
            try:
                from integrations.telegram_bot import telegram_service
                if telegram_service.allowed_user_id and telegram_service.client:
                    chat_id = int(telegram_service.allowed_user_id)
                    tg_txt = f"⏰ *¡ALARMA DE TITÁN!*\n\n¡Che fiera, pasaron los *{minutes} minutos* de: *{label}*!"
                    await telegram_service._send_text(chat_id, tg_txt)
                    from audio.tts import tts
                    voice_bytes = await tts.synthesize_to_bytes(msg)
                    if voice_bytes:
                        await telegram_service._send_voice(chat_id, voice_bytes)
            except Exception as ex:
                log_warning(f"Fallo aviso Telegram en timer: {ex}")

        except asyncio.CancelledError:
            log_info(f"[Scheduler] Temporizador '{label}' cancelado")
        finally:
            if timer_id in self.timers:
                del self.timers[timer_id]
            if timer_id in self._cancel_flags:
                del self._cancel_flags[timer_id]

    def cancel_timer(self, label: str) -> str:
        """Cancela un temporizador activo por su nombre"""
        cancelled = False
        for tid in list(self.timers.keys()):
            if label.lower() in tid.lower():
                self._cancel_flags[tid] = True
                task_or_thread = self.timers.get(tid)
                if isinstance(task_or_thread, asyncio.Task):
                    task_or_thread.cancel()
                if tid in self.timers:
                    del self.timers[tid]
                cancelled = True
        if cancelled:
            return f"Cancelé el temporizador para '{label}', che."
        return f"No encontré ningún temporizador activo con el nombre '{label}'."

    def list_timers(self) -> str:
        """Lista los temporizadores que están corriendo actualmente"""
        if not self.timers:
            return "No tenés ningún temporizador corriendo ahora mismo."
        lines = ["⏰ Temporizadores activos:"]
        for tid in self.timers:
            lbl = tid.split("_")[0]
            lines.append(f"• {lbl}")
        return "\n".join(lines)

titan_scheduler = TitanScheduler()
