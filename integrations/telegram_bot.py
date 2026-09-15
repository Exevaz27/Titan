import asyncio
import io
import os
import httpx
from typing import Optional, Dict, Any
from core.config import config
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState

class TelegramBotService:
    def __init__(self):
        self.token: str = config.telegram_bot_token
        self.api_url: str = f"https://api.telegram.org/bot{self.token}"
        self.file_url: str = f"https://api.telegram.org/file/bot{self.token}"
        self.allowed_user_id: Optional[str] = config.telegram_allowed_user_id or None
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._queue: Optional[asyncio.Queue] = None
        self.client: Optional[httpx.AsyncClient] = None
        self.voice_responses: bool = True

    def reload_config(self):
        self.token = config.telegram_bot_token
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.file_url = f"https://api.telegram.org/file/bot{self.token}"
        self.allowed_user_id = config.telegram_allowed_user_id or None

    async def start(self):
        """Inicia el bot de Telegram en segundo plano con cola secuencial FIFO"""
        self.reload_config()
        if not self.token:
            log_warning("Telegram Bot no iniciado: falta TELEGRAM_BOT_TOKEN en .env")
            return

        self._running = True
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10, keepalive_expiry=10.0)
        self.client = httpx.AsyncClient(timeout=15.0, limits=limits)

        # Verificar bot
        try:
            r = await self.client.get(f"{self.api_url}/getMe")
            data = r.json()
            if data.get("ok"):
                bot_info = data["result"]
                log_info(f"[Telegram] Bot conectado con éxito: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            else:
                log_error(f"[Telegram] Error validando token: {data}")
                return
        except Exception as e:
            log_error(f"[Telegram] Error de conexión inicial: {e}")
            return

        self._queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._queue_worker())
        self._task = asyncio.create_task(self._polling_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._worker_task:
            self._worker_task.cancel()
        if self.client:
            await self.client.aclose()
        log_info("[Telegram] Servicio detenido")

    def _get_main_keyboard(self) -> Dict[str, Any]:
        try:
            from tools.j2_camera import j2_camera
            cam_text = "📷 Cam: " + ("Frontal" if j2_camera.current_facing == "user" else "Trasera")
        except Exception:
            cam_text = "📷 Cam J2"

        voice_lbl = "🎙️ Voz: Activada" if getattr(self, "voice_responses", True) else "🔇 Voz: Silenciada"

        return {
            "inline_keyboard": [
                [
                    {"text": "🟢 Compinche", "callback_data": "mode:normal"},
                    {"text": "🟡 Pibes", "callback_data": "mode:kids"},
                    {"text": "🔴 Rebelde", "callback_data": "mode:rebel"},
                    {"text": "⚽ Modo Termo", "callback_data": "mode:tertulia"}
                ],
                [
                    {"text": voice_lbl, "callback_data": "cmd:toggle_voice"},
                    {"text": "📱 Foto J2", "callback_data": "cmd:j2_photo"},
                    {"text": "🛡️ Vigilancia", "callback_data": "cmd:vigilance_menu"}
                ],
                [
                    {"text": f"🔄 {cam_text}", "callback_data": "cmd:j2_toggle_cam"},
                    {"text": "⚡ Telemetría", "callback_data": "cmd:status"},
                    {"text": "🖥️ Captura PC", "callback_data": "cmd:screenshot"}
                ],
                [
                    {"text": "📋 Portapapeles", "callback_data": "cmd:clipboard"},
                    {"text": "🔒 Bloquear PC", "callback_data": "cmd:lock"},
                    {"text": "🛑 Energía", "callback_data": "cmd:power_menu"}
                ],
                [
                    {"text": "📺 Control Remoto TV BGH", "callback_data": "cmd:tv_menu"}
                ]
            ]
        }

    def _get_surveillance_keyboard(self) -> Dict[str, Any]:
        try:
            from tools.surveillance_service import surveillance_service
            sentry_active = surveillance_service.sentry_mode
        except Exception:
            sentry_active = False

        sentry_btn = "🚨 Centinela: ACTIVADO" if sentry_active else "🛡️ Centinela: APAGADO"

        return {
            "inline_keyboard": [
                [
                    {"text": "🛡️ Reporte Completo (J2 + PC)", "callback_data": "vigilance:full"}
                ],
                [
                    {"text": "📱 Habitación J2", "callback_data": "vigilance:j2"},
                    {"text": "🖥️ Pantalla PC", "callback_data": "vigilance:pc"}
                ],
                [
                    {"text": sentry_btn, "callback_data": "vigilance:sentry_toggle"},
                    {"text": "🔒 Bloquear PC", "callback_data": "cmd:lock"}
                ],
                [
                    {"text": "⬅️ Volver al Menú Principal", "callback_data": "cmd:back_menu"}
                ]
            ]
        }

    def _get_power_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "🌙 Suspender PC", "callback_data": "power:sleep"},
                    {"text": "🔄 Reiniciar", "callback_data": "power:restart_confirm"}
                ],
                [
                    {"text": "🛑 Apagar PC", "callback_data": "power:shutdown_confirm"}
                ],
                [
                    {"text": "⬅️ Volver al Menú", "callback_data": "cmd:back_menu"}
                ]
            ]
        }

    async def _send_text(self, chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
        if not self.client or not text:
            return
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = await self.client.post(f"{self.api_url}/sendMessage", json=payload)
            if r.status_code != 200:
                # Si falló con Markdown (error clásico de parseo de entidades en Telegram), reintentar sin parse_mode
                payload.pop("parse_mode", None)
                r2 = await self.client.post(f"{self.api_url}/sendMessage", json=payload)
                if r2.status_code != 200:
                    log_error(f"[Telegram] Error enviando texto (código {r2.status_code}): {r2.text[:100]}")
        except Exception as e:
            try:
                payload.pop("parse_mode", None)
                await self.client.post(f"{self.api_url}/sendMessage", json=payload)
            except Exception as ex:
                log_error(f"[Telegram] Error crítico enviando texto: {ex}")

    @staticmethod
    def prepare_text_for_voice_note(text: str) -> str:
        """Optimiza y adapta el texto para ser reproducido fluidamente como nota de voz en Telegram."""
        if not text:
            return ""
        import re
        # Reemplazar bloques de código ``` por mención breve
        t = re.sub(r'```[\s\S]*?```', ' (te dejé el código acá en el mensaje de texto para que lo copies) ', text)
        # Reemplazar enlaces Markdown [nombre](url) -> nombre
        t = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', t)
        # Eliminar caracteres markdown redundantes
        t = re.sub(r'[*_#`~]', '', t)
        # Si el texto supera los 600 caracteres, acotar amistosamente en el último punto
        if len(t) > 600:
            idx = t[:600].rfind('.')
            if idx > 200:
                t = t[:idx+1] + " Te dejé el resto de los detalles escritos en el mensaje, fiera."
            else:
                t = t[:550] + "... Te dejé todo el detalle completo por escrito acá en el mensaje."
        return t.strip()

    @staticmethod
    async def _convert_mp3_to_ogg_opus(mp3_bytes: bytes) -> Optional[bytes]:
        """Convierte un flujo de audio MP3 en OGG Opus nativo de Telegram usando ffmpeg en memoria."""
        if not mp3_bytes:
            return None
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-c:a", "libopus",
                "-b:a", "32k",
                "-f", "ogg",
                "pipe:1"
            ]
            from core.process_utils import popen_silent
            loop = asyncio.get_running_loop()
            def _run_ffmpeg():
                proc = popen_silent(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = proc.communicate(input=mp3_bytes, timeout=12)
                if proc.returncode == 0 and out:
                    return out
                return None
            return await loop.run_in_executor(None, _run_ffmpeg)
        except Exception as e:
            log_warning(f"[Telegram] Error en conversión a OGG Opus: {e}")
            return None

    async def _send_voice(self, chat_id: int, audio_bytes: bytes, caption: Optional[str] = None):
        """Envía una nota de voz nativa de Telegram (con onda de audio)."""
        if not self.client or not audio_bytes:
            return
        try:
            # Convertir MP3 a OGG Opus nativo para que Telegram lo muestre como nota de voz con forma de onda
            ogg_bytes = await self._convert_mp3_to_ogg_opus(audio_bytes)
            if ogg_bytes:
                files = {
                    "voice": ("voice.ogg", io.BytesIO(ogg_bytes), "audio/ogg")
                }
            else:
                files = {
                    "voice": ("voice.mp3", io.BytesIO(audio_bytes), "audio/mpeg")
                }

            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption[:1024]
            r = await self.client.post(f"{self.api_url}/sendVoice", data=data, files=files)
            if r.status_code != 200:
                log_warning(f"[Telegram] sendVoice retornó {r.status_code}, reintentando vía sendAudio...")
                files_audio = {
                    "audio": ("titan_voice.mp3", io.BytesIO(audio_bytes), "audio/mpeg")
                }
                data_audio = {"chat_id": chat_id, "title": "Titán", "performer": "Titán"}
                if caption:
                    data_audio["caption"] = caption[:1024]
                r_audio = await self.client.post(f"{self.api_url}/sendAudio", data=data_audio, files=files_audio)
                if r_audio.status_code != 200:
                    log_error(f"[Telegram] sendAudio también falló ({r_audio.status_code}): {r_audio.text[:100]}")
                    if caption:
                        await self._send_text(chat_id, caption)
        except Exception as e:
            log_error(f"[Telegram] Error enviando nota de voz: {e}")
            if caption:
                await self._send_text(chat_id, caption)

    async def _send_photo(self, chat_id: int, photo_bytes: bytes, caption: Optional[str] = None):
        if not self.client or not photo_bytes:
            return
        try:
            files = {
                "photo": ("screenshot.png", io.BytesIO(photo_bytes), "image/png")
            }
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption[:1024]
            r = await self.client.post(f"{self.api_url}/sendPhoto", data=data, files=files)
            if r.status_code != 200:
                log_error(f"[Telegram] Error enviando foto ({r.status_code}): {r.text[:100]}")
                if caption:
                    await self._send_text(chat_id, f"⚠️ No se pudo enviar la imagen: {caption}")
        except Exception as e:
            log_error(f"[Telegram] Error enviando foto: {e}")
            if caption:
                await self._send_text(chat_id, f"⚠️ Error enviando foto: {caption}")

    async def broadcast_photo(self, photo_bytes: bytes, caption: Optional[str] = None):
        target = getattr(self, "last_chat_id", None) or self.allowed_user_id
        if target and photo_bytes:
            await self._send_photo(target, photo_bytes, caption=caption)

    async def broadcast_text(self, text: str):
        target = getattr(self, "last_chat_id", None) or self.allowed_user_id
        if target and text:
            await self._send_text(target, text)

    async def _send_document(self, chat_id: int, file_path: str, caption: Optional[str] = None) -> bool:
        if not self.client or not os.path.exists(file_path):
            return False
        try:
            filename = os.path.basename(file_path)
            with open(file_path, "rb") as f:
                doc_bytes = f.read()
            files = {
                "document": (filename, io.BytesIO(doc_bytes), "application/octet-stream")
            }
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption[:1024]
            r = await self.client.post(f"{self.api_url}/sendDocument", data=data, files=files)
            return r.status_code == 200
        except Exception as e:
            log_error(f"[Telegram] Error enviando documento {file_path}: {e}")
            return False

    async def _send_chat_action(self, chat_id: int, action: str = "typing"):
        if not self.client:
            return
        try:
            await self.client.post(f"{self.api_url}/sendChatAction", json={"chat_id": chat_id, "action": action})
        except Exception:
            pass

    async def _answer_callback(self, callback_id: str, text: Optional[str] = None):
        if not self.client:
            return
        try:
            payload = {"callback_query_id": callback_id}
            if text:
                payload["text"] = text
            await self.client.post(f"{self.api_url}/answerCallbackQuery", json=payload)
        except Exception:
            pass

    async def _check_authorization(self, user_id: int, chat_id: int) -> bool:
        user_str = str(user_id)
        if not self.allowed_user_id:
            # Primer usuario que interactúa: se auto-vincula como dueño exclusivo
            self.allowed_user_id = user_str
            config.set_telegram_allowed_user_id(user_str)
            log_info(f"[Telegram] Bot vinculado exitosamente al usuario dueño: ID {user_str}")
            await self._send_text(
                chat_id,
                f"🔒 *¡Cuenta vinculada con éxito!*\nTu usuario de Telegram (`{user_str}`) ahora es el único autorizado para dar órdenes a Titán en esta compu."
            )
            return True

        if user_str != self.allowed_user_id:
            log_warning(f"[Telegram] Intento de acceso no autorizado de usuario ID: {user_str}")
            await self._send_text(
                chat_id,
                "⛔ *Acceso Denegado*\nEste asistente es personal y privado. Solo responde a su dueño."
            )
            return False

        return True

    async def _queue_worker(self):
        """Procesa los mensajes de Telegram de forma secuencial y estricta (FIFO) para evitar respuestas desordenadas"""
        while self._running:
            try:
                if not self._queue:
                    await asyncio.sleep(0.1)
                    continue
                update = await self._queue.get()
                try:
                    await self._process_update(update)
                except Exception as ex:
                    log_error(f"[Telegram] Error procesando update en worker: {ex}")
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"[Telegram] Error inesperado en cola de mensajes: {e}")
                await asyncio.sleep(0.5)

    async def _chat_action_pulse(self, chat_id: int, action: str = "record_voice"):
        """Mantiene activo el estado 'grabando audio...' o 'escribiendo...' mientras Titán piensa"""
        try:
            while True:
                await self._send_chat_action(chat_id, action)
                await asyncio.sleep(3.5)
        except asyncio.CancelledError:
            pass

    async def _polling_loop(self):
        offset = 0
        log_info("[Telegram] Bucle de escucha rápida (long-polling) iniciado")
        while self._running:
            try:
                # Timeout de 6s en Telegram y 12s en HTTP para refresco ultrarrápido y evitar conexiones congeladas
                params = {"timeout": 6}
                if offset:
                    params["offset"] = offset

                r = await self.client.get(f"{self.api_url}/getUpdates", params=params, timeout=12.0)
                if r.status_code != 200:
                    if r.status_code == 409:
                        log_warning("[Telegram] 409 Conflicto: otra instancia está haciendo getUpdates. Esperando 3s...")
                        await asyncio.sleep(3.0)
                    else:
                        log_warning(f"[Telegram] getUpdates retornó HTTP {r.status_code}: {r.text[:100]}")
                        await asyncio.sleep(1.5)
                    continue

                res = r.json()
                if not res.get("ok"):
                    log_warning(f"[Telegram] getUpdates error en payload: {res}")
                    await asyncio.sleep(1.5)
                    continue

                updates = res.get("result", [])
                for u in updates:
                    offset = u["update_id"] + 1
                    if self._queue:
                        await self._queue.put(u)

            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                # Timeout normal de long-polling, reiniciar de inmediato la petición
                continue
            except Exception as e:
                log_warning(f"[Telegram] Reintentando conexión de polling: {e}")
                await asyncio.sleep(1.5)

    async def _process_update(self, update: Dict[str, Any]):
        try:
            # 1. Callback query de botones inline
            if "callback_query" in update:
                cb = update["callback_query"]
                user = cb.get("from", {})
                chat_id = cb.get("message", {}).get("chat", {}).get("id")
                data = cb.get("data", "")
                cb_id = cb.get("id")

                if not await self._check_authorization(user.get("id", 0), chat_id):
                    await self._answer_callback(cb_id, "No autorizado")
                    return

                if chat_id:
                    self.last_chat_id = chat_id

                await self._handle_callback(cb_id, chat_id, data)
                return

            # 2. Mensajes normales (texto o notas de voz)
            if "message" in update:
                msg = update["message"]
                chat_id = msg.get("chat", {}).get("id")
                user = msg.get("from", {})

                if not await self._check_authorization(user.get("id", 0), chat_id):
                    return

                if chat_id:
                    self.last_chat_id = chat_id

                # A. Comando /start o /menu
                text = msg.get("text", "").strip()
                if text in ["/start", "/menu", "/ayuda"]:
                    welcome = (
                        "🇦🇷 *¡Qué hacés, papá! Acá está Titán en Telegram.*\n\n"
                        "Podés mandarme **mensajes de texto** o **notas de voz** directamente desde acá, "
                        "y te respondo con mi voz de barrio al toque.\n\n"
                        "Elegí un modo o probá los accesos rápidos:"
                    )
                    await self._send_text(chat_id, welcome, reply_markup=self._get_main_keyboard())
                    return

                # B. Comando /voz o /audio (Conmutar respuestas en notas de voz)
                if text in ["/voz", "/audio", "/audio_on", "/audio_off"]:
                    if text == "/audio_on":
                        self.voice_responses = True
                    elif text == "/audio_off":
                        self.voice_responses = False
                    else:
                        self.voice_responses = not getattr(self, "voice_responses", True)
                    estado = "activadas 🎙️" if self.voice_responses else "silenciadas 🔇"
                    await self._send_text(
                        chat_id,
                        f"🎙️ *Notas de voz de Titán:*\nAhora las respuestas en audio están *{estado}*.\n"
                        f"Titán te mandará notas de voz cuando converses con él.",
                        reply_markup=self._get_main_keyboard()
                    )
                    return

                # C. Comando /termo, /tertulia o /debate
                if text in ["/termo", "/tertulia", "/debate"]:
                    from brain.gemini_client import brain
                    brain.set_mode("tertulia")
                    reply = "¡¡Se armó el Modo Termo, papá!! Poné la pava o destapá algo, que acá nos plantamos a hablar de fútbol en serio. ¿De qué tema tirás a la cancha?"
                    await self._send_text(chat_id, f"*⚽ Modo Termo*\n{reply}", reply_markup=self._get_main_keyboard())
                    from audio.tts import tts
                    voice_bytes = await tts.synthesize_to_bytes(reply)
                    if voice_bytes:
                        await self._send_voice(chat_id, voice_bytes)
                    return

                # D. Comando /mate o /mates
                if text in ["/mate", "/mates", "/amargo", "/amargos"]:
                    from tools.system_control import system_control
                    system_control.switch_screen_view("face")
                    system_control.set_inactivity_stage("mate")
                    reply = "¡De una, fiera! Pongo la pava al fuego y me clavo unos buenos mates amargos en la pantalla."
                    await self._send_text(chat_id, f"🧉 *Modo Mate Activado*\n{reply}", reply_markup=self._get_main_keyboard())
                    from audio.tts import tts
                    voice_bytes = await tts.synthesize_to_bytes(reply)
                    if voice_bytes:
                        await self._send_voice(chat_id, voice_bytes)
                    return

                # E. Comando /dormir o /siesta
                if text in ["/dormir", "/siesta", "/mimir"]:
                    from tools.system_control import system_control
                    system_control.switch_screen_view("face")
                    system_control.set_inactivity_stage("sleeping")
                    reply = "Buenas noches, hermano. Descanso un poco los circuitos, cualquier cosa chiflame."
                    await self._send_text(chat_id, f"🌙 *Modo Siesta Activado*\n{reply}", reply_markup=self._get_main_keyboard())
                    from audio.tts import tts
                    voice_bytes = await tts.synthesize_to_bytes(reply)
                    if voice_bytes:
                        await self._send_voice(chat_id, voice_bytes)
                    return

                # F. Comando /tv o /tele (Control Remoto BGH Android TV)
                if text and (text.lower().startswith("/tv") or text.lower().startswith("/tele")):
                    await self._handle_tv_command(chat_id, text)
                    return

                # B. Nota de voz / Audio entrante
                if "voice" in msg or "audio" in msg:
                    voice_obj = msg.get("voice") or msg.get("audio")
                    await self._handle_voice_message(chat_id, voice_obj)
                    return

                # C. Mensaje de texto estándar
                if text:
                    await self._handle_text_message(chat_id, text)
                    return

        except Exception as e:
            log_error(f"[Telegram] Error procesando update: {e}")

    async def _handle_callback(self, cb_id: str, chat_id: int, data: str):
        from brain.gemini_client import brain

        if data.startswith("mode:"):
            mode = data.split(":")[1]
            brain.set_mode(mode)
            names = {
                "normal": "🟢 Compinche",
                "kids": "🟡 Pibes",
                "rebel": "🔴 Rebelde",
                "tertulia": "⚽ Modo Termo"
            }
            await self._answer_callback(cb_id, f"Modo {names.get(mode, mode)} activado")
            
            if mode == "kids":
                reply = "¡Ufa, che! ¡Modo Pibes activado! A partir de ahora no le pienso hacer caso a ningún remolón. ¡Cero malas palabras!"
            elif mode == "rebel":
                reply = "¡¿Modo rebelde querés?! ¡¡Listo, a partir de ahora me chupa un huevo todo, no te pienso hacer un carajo!!"
            elif mode == "tertulia":
                reply = "¡¡Se armó el Modo Termo, papá!! Poné la pava o destapá algo, que acá nos plantamos a hablar de fútbol en serio. ¿De qué tema tirás a la cancha?"
            else:
                reply = "¡De una, papá! Volví al modo compinche de fierro de La Boca. ¿En qué te doy una mano?"

            await self._send_text(chat_id, f"*{names.get(mode, mode)}*\n{reply}", reply_markup=self._get_main_keyboard())

            # Generar audio de voz también para la confirmación
            from audio.tts import tts
            voice_bytes = await tts.synthesize_to_bytes(reply)
            if voice_bytes:
                await self._send_voice(chat_id, voice_bytes)

        elif data.startswith("tv:"):
            from tools.tv_control import tv_control
            action = data.split(":")[1]
            if action == "power":
                res = tv_control.power_toggle()
                await self._answer_callback(cb_id, "Encendido/Apagado")
            elif action == "volup":
                res = tv_control.volume_up(4)
                await self._answer_callback(cb_id, "+4 Vol")
            elif action == "voldown":
                res = tv_control.volume_down(4)
                await self._answer_callback(cb_id, "-4 Vol")
            elif action == "mute":
                res = tv_control.mute()
                await self._answer_callback(cb_id, "Mute")
            elif action == "playpause":
                res = tv_control.play_pause()
                await self._answer_callback(cb_id, "Play/Pausa")
            elif action == "onplay":
                res = tv_control.open_onplay_live()
                await self._answer_callback(cb_id, "Abriendo OnPlay")
                await self._send_text(chat_id, res.get("message", "OnPlay abierto."), reply_markup=self._get_tv_keyboard())
            elif action == "youtube":
                res = tv_control.open_app("smarttube")
                await self._answer_callback(cb_id, "Abriendo YouTube")
                await self._send_text(chat_id, res.get("message", "YouTube abierto."), reply_markup=self._get_tv_keyboard())
            elif action == "netflix":
                res = tv_control.open_app("netflix")
                await self._answer_callback(cb_id, "Abriendo Netflix")
                await self._send_text(chat_id, res.get("message", "Netflix abierto."), reply_markup=self._get_tv_keyboard())
            elif action == "home":
                res = tv_control.send_key("home")
                await self._answer_callback(cb_id, "Inicio")
            elif action == "back":
                res = tv_control.send_key("back")
                await self._answer_callback(cb_id, "Atrás")
            elif data.startswith("tv:ch:"):
                target_ch = data.split(":")[2]
                res = tv_control.tune_channel(target_ch)
                await self._answer_callback(cb_id, f"Canal {target_ch}")
                await self._send_text(chat_id, res.get("message", "Canal sintonizado."), reply_markup=self._get_tv_keyboard())

        elif data == "cmd:tv_menu":
            await self._answer_callback(cb_id, "Abriendo Control TV...")
            from tools.tv_control import tv_control
            st = tv_control.get_status()
            pwr = st.get("power", "desconocido")
            msg = (
                f"📺 *Control Remoto BGH Android TV*\n"
                f"• Estado: *{pwr.upper()}*\n"
                f"• IP: `{st.get('ip')}`\n"
                f"• Canales OnPlay: *97 disponibles*\n\n"
                f"Tocá un botón, pedime cualquier canal por voz/texto (ej: `/tv espn premium` o `/tv 17`) o usá los controles:"
            )
            await self._send_text(chat_id, msg, reply_markup=self._get_tv_keyboard())

        elif data == "cmd:toggle_voice":
            self.voice_responses = not getattr(self, "voice_responses", True)
            estado = "activadas 🎙️" if self.voice_responses else "silenciadas 🔇"
            await self._answer_callback(cb_id, f"Notas de voz {estado}")
            await self._send_text(
                chat_id,
                f"🎙️ *Notas de voz de Titán:*\nAhora las respuestas en audio están *{estado}*.\n"
                f"Titán te mandará notas de voz cuando converses con él.",
                reply_markup=self._get_main_keyboard()
            )

        elif data == "cmd:status":
            await self._answer_callback(cb_id, "Consultando estado...")
            await self._send_chat_action(chat_id, "typing")
            from tools.system_control import system_control
            loop = asyncio.get_running_loop()
            metrics = await loop.run_in_executor(None, system_control.get_system_metrics)
            txt = (
                f"⚡ *Telemetría de la Compu:*\n\n"
                f"• **CPU:** {metrics.get('cpu_percent', 0)}% ({metrics.get('cpu_count', 0)} núcleos)\n"
                f"• **RAM:** {metrics.get('ram_used_gb', 0)} GB / {metrics.get('ram_total_gb', 0)} GB ({metrics.get('ram_percent', 0)}%)\n\n"
                f"💽 *Almacenamiento:*\n"
            )
            disks = metrics.get("disks", {})
            if isinstance(disks, dict) and disks:
                for letter, d in disks.items():
                    free_gb = d.get('free_gb', 0)
                    total_gb = d.get('total_gb', 0)
                    pct = round(100 - d.get('percent_used', 0))
                    txt += f"• Disco {letter}: {free_gb} GB libres de {total_gb} GB ({pct}% libre)\n"
            elif isinstance(disks, list) and disks:
                for d in disks:
                    txt += f"• Disco {d.get('letter', '-')}: {d.get('free_gb', 0)} GB libres de {d.get('total_gb', 0)} GB ({round(100 - d.get('percent_used', 0))}% libre)\n"
            else:
                txt += "• Sin información de discos disponible.\n"

            await self._send_text(chat_id, txt, reply_markup=self._get_main_keyboard())

        elif data == "cmd:j2_photo":
            await self._answer_callback(cb_id, "Capturando foto con el J2...")
            await self._send_chat_action(chat_id, "upload_photo")
            from tools.j2_camera import j2_camera
            photo_bytes = await j2_camera.capture_photo(timeout=8.0)
            if photo_bytes:
                caption = f"📸 Foto en vivo desde el Samsung J2 ({j2_camera.get_facing_label()})"
                await self._send_photo(chat_id, photo_bytes, caption=caption)
            else:
                await self._send_text(
                    chat_id,
                    "⚠️ *No se pudo conectar a la cámara del J2.*\n"
                    "Verificá que el Samsung J2 tenga la pantalla encendida y conectada al HUD.",
                    reply_markup=self._get_main_keyboard()
                )

        elif data == "cmd:j2_toggle_cam":
            from tools.j2_camera import j2_camera
            from server.websocket_hub import ws_hub
            new_label = j2_camera.toggle_facing()
            await ws_hub.broadcast_event({"type": "flip_camera", "mode": j2_camera.current_facing})
            await self._answer_callback(cb_id, f"Cámara: {new_label}")
            await self._send_text(
                chat_id,
                f"🔄 *Cámara del J2 configurada:*\nAhora está activa la cámara: *{new_label}*.",
                reply_markup=self._get_main_keyboard()
            )

        elif data in ("cmd:vigilance_menu", "vigilance:menu"):
            await self._answer_callback(cb_id)
            from tools.surveillance_service import surveillance_service
            st = surveillance_service.get_status()
            sentry_str = "🟢 ACTIVADO" if st.get("sentry_mode") else "🔴 DESACTIVADO"
            msg = (
                "🛡️ *CENTRO DE VIGILANCIA Y SEGURIDAD DE TITÁN* 🇦🇷\n\n"
                "Monitoreo en tiempo real de tu habitación y tu computadora mientras estás afuera:\n\n"
                f"• Modo Centinela (Alertas automáticas): *{sentry_str}*\n"
                f"• Samsung J2 conectado: *{'Sí' if st.get('j2_connected') else 'No'}*\n"
                f"• Satélite Windows conectado: *{'Sí' if st.get('windows_satellite_connected') else 'No'}*\n\n"
                "Seleccioná una acción:"
            )
            await self._send_text(chat_id, msg, reply_markup=self._get_surveillance_keyboard())

        elif data == "vigilance:full":
            await self._answer_callback(cb_id, "Iniciando inspección completa (J2 + PC)...")
            await self._send_chat_action(chat_id, "upload_photo")
            from tools.surveillance_service import surveillance_service
            from audio.tts import tts

            rep = await surveillance_service.get_full_security_report()

            # 1. Foto del J2
            if rep.get("j2_photo"):
                caption_j2 = f"📱 *Habitación (Samsung J2):*\n{rep.get('j2_report', '')}"
                await self._send_photo(chat_id, rep["j2_photo"], caption=caption_j2)

            # 2. Captura de PC
            if rep.get("pc_photo"):
                pc_info = rep.get("pc_info", {})
                lock_text = "🔒 Bloqueada" if pc_info.get("is_locked") else "🔓 Desbloqueada"
                caption_pc = (
                    f"🖥️ *Monitor Windows:*\n"
                    f"• Sesión: *{lock_text}*\n"
                    f"• Ventana activa: *{pc_info.get('active_window', 'Desconocida')}*\n"
                    f"• Inactividad: *{pc_info.get('idle_minutes', 0)} min* ({int(pc_info.get('idle_seconds', 0))}s)"
                )
                await self._send_photo(chat_id, rep["pc_photo"], caption=caption_pc)

            # 3. Audio de voz con conclusión de Titán
            summary = rep.get("summary_spoken", "")
            if summary and getattr(self, "voice_responses", True):
                try:
                    spoken = self.prepare_text_for_voice_note(summary)
                    v_bytes = await tts.synthesize_to_bytes(spoken)
                    if v_bytes:
                        await self._send_voice(chat_id, v_bytes, caption="🎙️ Parte de seguridad de Titán")
                except Exception as ex_v:
                    log_warning(f"[Vigilancia] Error generando voz: {ex_v}")

            # 4. Texto de confirmación
            await self._send_text(chat_id, "✅ *Inspección completada.* Todos los sensores reportados.", reply_markup=self._get_surveillance_keyboard())

        elif data in ("vigilance:j2", "cmd:j2_security"):
            await self._answer_callback(cb_id, "Vigilando habitación con J2 e IA...")
            await self._send_chat_action(chat_id, "upload_photo")
            from tools.surveillance_service import surveillance_service
            from audio.tts import tts

            photo_bytes, report = await surveillance_service.get_j2_visual_report()
            if photo_bytes:
                await self._send_photo(chat_id, photo_bytes, caption=f"👁️ *Vigilancia J2:*\n{report}")
                if getattr(self, "voice_responses", True):
                    try:
                        spoken = self.prepare_text_for_voice_note(report)
                        v_bytes = await tts.synthesize_to_bytes(spoken)
                        if v_bytes:
                            await self._send_voice(chat_id, v_bytes, caption="🎙️ Reporte J2")
                    except Exception:
                        pass
            else:
                await self._send_text(
                    chat_id,
                    f"⚠️ *Fallo al acceder a la cámara del J2:*\n{report}",
                    reply_markup=self._get_surveillance_keyboard()
                )

        elif data == "vigilance:pc":
            await self._answer_callback(cb_id, "Chequeando computadora Windows...")
            await self._send_chat_action(chat_id, "upload_photo")
            from tools.surveillance_service import surveillance_service

            photo_bytes, sec_info = await surveillance_service.get_pc_surveillance()
            lock_text = "🔒 Bloqueada" if sec_info.get("is_locked") else "🔓 Desbloqueada"
            txt = (
                f"🖥️ *Seguridad de la Computadora:*\n\n"
                f"• Estado: *{lock_text}*\n"
                f"• Ventana en primer plano: *{sec_info.get('active_window', 'Desconocida')}*\n"
                f"• Inactividad de mouse/teclado: *{sec_info.get('idle_minutes', 0)} min* ({int(sec_info.get('idle_seconds', 0))}s)\n"
            )
            if photo_bytes:
                await self._send_photo(chat_id, photo_bytes, caption=txt)
            else:
                await self._send_text(chat_id, txt, reply_markup=self._get_surveillance_keyboard())

        elif data == "vigilance:sentry_toggle":
            from tools.surveillance_service import surveillance_service
            if surveillance_service.sentry_mode:
                res_msg = surveillance_service.disable_sentry()
            else:
                res_msg = surveillance_service.enable_sentry()
            await self._answer_callback(cb_id, "Modo Centinela actualizado")
            await self._send_text(chat_id, res_msg, reply_markup=self._get_surveillance_keyboard())

        elif data == "cmd:screenshot":
            await self._answer_callback(cb_id, "Sacando captura de pantalla...")
            await self._send_chat_action(chat_id, "upload_photo")
            from tools.system_control import system_control
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, system_control.take_screenshot)
            if res.get("status") == "success":
                photo_bytes = None
                if res.get("photo_base64"):
                    import base64
                    try:
                        photo_bytes = base64.b64decode(res["photo_base64"])
                    except Exception as e_b64:
                        log_warning(f"[Telegram] Error decodificando captura: {e_b64}")
                elif res.get("path") and os.path.exists(res["path"]):
                    with open(res["path"], "rb") as f:
                        photo_bytes = f.read()

                if photo_bytes:
                    await self._send_photo(chat_id, photo_bytes, caption="📸 Captura actual de tu monitor")
                    return
            await self._send_text(chat_id, res.get("message", "No se pudo tomar la captura en este momento."))

        elif data == "cmd:look_screen":
            await self._answer_callback(cb_id, "Analizando pantalla con Gemini Visión...")
            await self._send_chat_action(chat_id, "record_voice")
            from brain.tool_registry import analyze_screen
            from audio.tts import tts
            loop = asyncio.get_running_loop()
            vision_reply = await loop.run_in_executor(None, analyze_screen, "Describí qué hay abierto en la pantalla de la computadora y qué se ve")
            await self._send_text(chat_id, f"👁️ *Visión de Pantalla:*\n{vision_reply}")
            try:
                voice_bytes = await tts.synthesize_to_bytes(vision_reply)
                if voice_bytes:
                    await self._send_voice(chat_id, voice_bytes)
            except Exception as e_v:
                log_warning(f"[Telegram] Error generando voz para look_screen: {e_v}")

        elif data == "cmd:clipboard":
            await self._answer_callback(cb_id, "Leyendo portapapeles...")
            from tools.system_control import system_control
            loop = asyncio.get_running_loop()
            clip = await loop.run_in_executor(None, system_control.get_clipboard)
            txt = clip.get("text", "")
            if txt:
                await self._send_text(chat_id, f"📋 *Portapapeles de tu PC:*\n```\n{txt[:2000]}\n```", reply_markup=self._get_main_keyboard())
            else:
                await self._send_text(chat_id, "📋 El portapapeles de la compu está vacío o tiene un formato no compatible.", reply_markup=self._get_main_keyboard())

        elif data == "cmd:lock":
            await self._answer_callback(cb_id, "Bloqueando Windows...")
            from tools.system_control import system_control
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, system_control.lock_workstation)
            await self._send_text(chat_id, "🔒 *Sesión de Windows bloqueada con éxito.*", reply_markup=self._get_main_keyboard())

        elif data == "cmd:power_menu":
            await self._answer_callback(cb_id)
            await self._send_text(chat_id, "🛑 *Menú de Control de Energía:*\nSeleccioná una acción:", reply_markup=self._get_power_keyboard())

        elif data == "cmd:back_menu":
            await self._answer_callback(cb_id)
            await self._send_text(chat_id, "🇦🇷 *Panel Principal de Titán:*", reply_markup=self._get_main_keyboard())

        elif data == "power:sleep":
            await self._answer_callback(cb_id, "Suspendiendo PC...")
            from tools.system_control import system_control
            await self._send_text(chat_id, "🌙 Poniendo la computadora en modo suspensión...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, system_control.sleep_pc)

        elif data == "power:shutdown_confirm":
            await self._answer_callback(cb_id)
            confirm_kb = {
                "inline_keyboard": [
                    [{"text": "⚠️ SÍ, APAGAR AHORA", "callback_data": "power:shutdown_exec"}],
                    [{"text": "❌ Cancelar", "callback_data": "cmd:power_menu"}]
                ]
            }
            await self._send_text(chat_id, "⚠️ *¿Estás seguro de que querés apagar la PC por completo?*", reply_markup=confirm_kb)

        elif data == "power:shutdown_exec":
            await self._answer_callback(cb_id, "Apagando PC...")
            from tools.system_control import system_control
            await self._send_text(chat_id, "🛑 Apagando la computadora en 10 segundos. ¡Chau papá!")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, system_control.shutdown_pc)

        elif data == "power:restart_confirm":
            await self._answer_callback(cb_id)
            confirm_kb = {
                "inline_keyboard": [
                    [{"text": "⚠️ SÍ, REINICIAR", "callback_data": "power:restart_exec"}],
                    [{"text": "❌ Cancelar", "callback_data": "cmd:power_menu"}]
                ]
            }
            await self._send_text(chat_id, "⚠️ *¿Estás seguro de que querés reiniciar la PC?*", reply_markup=confirm_kb)

        elif data == "power:restart_exec":
            await self._answer_callback(cb_id, "Reiniciando PC...")
            from tools.system_control import system_control
            await self._send_text(chat_id, "🔄 Reiniciando la computadora en 10 segundos...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, system_control.restart_pc)

    def _transcribe_audio_bytes(self, audio_bytes: bytes) -> str:
        """Convierte audio entrante (OGG Opus de Telegram) a PCM y usa Google Speech Recognition (es-AR)"""
        import subprocess
        import speech_recognition as sr

        try:
            from core.process_utils import popen_silent
            cmd = [
                "ffmpeg", "-y", "-i", "pipe:0",
                "-f", "s16le", "-ar", "16000", "-ac", "1",
                "pipe:1"
            ]
            proc = popen_silent(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            raw_pcm, err = proc.communicate(input=audio_bytes, timeout=12)
            if proc.returncode != 0 or not raw_pcm:
                log_warning(f"[Telegram STT] ffmpeg falló al decodificar audio: {err[:80]}")
                return ""

            r = sr.Recognizer()
            audio_data = sr.AudioData(raw_pcm, 16000, 2)
            text = r.recognize_google(audio_data, language="es-AR")
            return text.strip() if text else ""
        except sr.UnknownValueError:
            log_info("[Telegram STT] No se detectaron palabras comprensibles en el audio.")
            return ""
        except Exception as e:
            log_warning(f"[Telegram STT] Error en transcripción de audio: {e}")
            return ""

    async def _handle_text_message(self, chat_id: int, text: str, from_voice: bool = False):
        from brain.local_intents import local_intents
        from brain.gemini_client import brain
        from audio.tts import tts

        pulse_task = asyncio.create_task(self._chat_action_pulse(chat_id, "record_voice"))

        try:
            # Registrar actividad del usuario en el sensor de presencia
            try:
                from tools.presence_detector import presence_detector
                presence_detector.record_user_activity()
            except Exception:
                pass

            clean_t = text.strip().lower()

            # Comandos de creación o edición de imágenes con IA en Telegram
            image_triggers = [
                "/imagen", "/dibujar", "/crear_imagen",
                "creame una imagen de", "creá una imagen de", "crea una imagen de",
                "creame una imagen", "creá una imagen", "crea una imagen",
                "haceme una imagen de", "hacé una imagen de", "hace una imagen de",
                "haceme una imagen", "hacé una imagen", "hace una imagen",
                "generame una imagen de", "generá una imagen de", "genera una imagen de",
                "generame una imagen", "generá una imagen", "genera una imagen",
                "dibujame una imagen de", "dibujá una imagen de", "dibuja una imagen de",
                "dibujame un", "dibujame una", "dibujame el", "dibujame la", "dibujame",
                "dibujá un", "dibujá una", "dibujá el", "dibujá la", "dibujá",
                "dibuja un", "dibuja una", "dibuja el", "dibuja la", "dibuja"
            ]
            is_tg_img = any(clean_t.startswith(pfx) or f" {pfx} " in f" {clean_t} " for pfx in image_triggers)
            if is_tg_img:
                img_prompt = ""
                for pfx in image_triggers:
                    if pfx in clean_t:
                        idx = clean_t.find(pfx)
                        img_prompt = text[idx + len(pfx):].strip()
                        break

                if not img_prompt:
                    await self._send_text(
                        chat_id,
                        "🎨 *Generador de Imágenes de Titán*\n\n"
                        "Decime qué querés que te dibuje. Por ejemplo:\n"
                        "• `/imagen un asado bien argentino en la luna`\n"
                        "• `dibujame un mate espacial estilo cyberpunk`"
                    )
                    return

                await self._send_chat_action(chat_id, "upload_photo")
                await self._send_text(chat_id, f"🎨 *¡De una, fiera!* Ya te la empiezo a dibujar:\n_\"{img_prompt}\"_")

                from tools.image_generator import image_generator
                res = await image_generator.generate(img_prompt)

                if res.get("status") == "success" and res.get("image_bytes"):
                    caption = f"🎨 *Titán Art:* {img_prompt}\n⚡ _Generado en {res.get('elapsed', 0)}s con FLUX.1 (Black Forest Labs)_"
                    # Entregar EXCLUSIVAMENTE a Telegram (no al HUD)
                    await self._send_photo(chat_id, res["image_bytes"], caption=caption)

                    should_send_voice = getattr(self, "voice_responses", True) or from_voice
                    if should_send_voice:
                        try:
                            v_bytes = await tts.synthesize_to_bytes("¡Listo, papá! Acá tenés la imagen que me pediste.")
                            if v_bytes:
                                await self._send_voice(chat_id, v_bytes)
                        except Exception as ex_v:
                            log_warning(f"[Telegram] Error enviando voz de confirmación imagen: {ex_v}")
                else:
                    await self._send_text(chat_id, f"⚠️ Uh, che, se me complicó generar la imagen: {res.get('message', 'Error desconocido')}")
                return

            # Comandos directos de Sensor de Presencia Frontal (Samsung J2)
            if clean_t in ["/presencia", "/sensor_presencia"]:
                from tools.presence_detector import presence_detector
                st = presence_detector.get_status()
                status_str = "🟢 ACTIVO" if st.get("enabled") else "🔴 DESACTIVADO"
                inact = st.get("inactivity_seconds", 0) // 60
                msg = (
                    f"👁️ *Sensor de Presencia Frontal (Samsung J2):*\n\n"
                    f"• Estado: *{status_str}*\n"
                    f"• Inactividad: *{inact} min*\n"
                    f"• Ausencia detectada: *{'Sí (ausente)' if st.get('is_absent') else 'No (presente)'}*\n"
                    f"• Cooldown anti-spam: *{'Activo (' + str(st.get('cooldown_remaining_seconds', 0)//60) + ' min restantes)' if st.get('in_cooldown') else 'Listo para saludar'}*\n"
                    f"• J2 conectado: *{'Sí' if st.get('active_hud_clients', 0) > 0 else 'No'}*\n\n"
                    f"Comandos rápidos: /presencia_on | /presencia_off"
                )
                await self._send_text(chat_id, msg)
                return

            if clean_t in ["/presencia_on", "/activar_presencia"]:
                from tools.presence_detector import presence_detector
                res = presence_detector.enable()
                await self._send_text(chat_id, f"✅ *Sensor de Presencia Activado:*\n{res}")
                return

            if clean_t in ["/presencia_off", "/desactivar_presencia"]:
                from tools.presence_detector import presence_detector
                res = presence_detector.disable()
                await self._send_text(chat_id, f"⏸️ *Sensor de Presencia Desactivado:*\n{res}")
                return

            # Comandos directos de Centro de Vigilancia y Seguridad
            if clean_t in ["/vigilar", "/seguridad", "/vigilancia", "modo vigilancia", "vigilancia", "centro de vigilancia"]:
                from tools.surveillance_service import surveillance_service
                st = surveillance_service.get_status()
                sentry_str = "🟢 ACTIVADO" if st.get("sentry_mode") else "🔴 DESACTIVADO"
                msg = (
                    "🛡️ *CENTRO DE VIGILANCIA Y SEGURIDAD DE TITÁN* 🇦🇷\n\n"
                    "Monitoreo en tiempo real de tu habitación y tu computadora mientras estás afuera:\n\n"
                    f"• Modo Centinela (Alertas automáticas): *{sentry_str}*\n"
                    f"• Samsung J2 conectado: *{'Sí' if st.get('j2_connected') else 'No'}*\n"
                    f"• Satélite Windows conectado: *{'Sí' if st.get('windows_satellite_connected') else 'No'}*\n\n"
                    "Elegí una opción o usá /vigilar_todo para un reporte instantáneo:"
                )
                await self._send_text(chat_id, msg, reply_markup=self._get_surveillance_keyboard())
                return

            if clean_t in ["/vigilar_todo", "/reporte_seguridad", "vigila todo", "vigilá todo", "vigilar todo", "vigilame la casa", "vigila la casa"]:
                await self._handle_callback("cmd_text", chat_id, "vigilance:full")
                return

            if clean_t in ["/vigilar_pc", "revisa la pc", "revisá la pc", "revisa la compu", "revisá la compu", "alguien toco la compu", "alguien tocó la compu", "tocaron la pc"]:
                await self._handle_callback("cmd_text", chat_id, "vigilance:pc")
                return

            if clean_t in ["/centinela", "/modo_centinela"]:
                from tools.surveillance_service import surveillance_service
                st = "🟢 ACTIVADO" if surveillance_service.sentry_mode else "🔴 DESACTIVADO"
                await self._send_text(chat_id, f"🚨 *Modo Centinela:* {st}\n\nComandos rápidos: /centinela_on | /centinela_off", reply_markup=self._get_surveillance_keyboard())
                return

            if clean_t in ["/centinela_on", "/activar_centinela", "activar centinela", "activa el centinela", "activá el centinela"]:
                from tools.surveillance_service import surveillance_service
                res = surveillance_service.enable_sentry()
                await self._send_text(chat_id, res, reply_markup=self._get_surveillance_keyboard())
                return

            if clean_t in ["/centinela_off", "/desactivar_centinela", "desactivar centinela", "apaga el centinela", "apagá el centinela"]:
                from tools.surveillance_service import surveillance_service
                res = surveillance_service.disable_sentry()
                await self._send_text(chat_id, res, reply_markup=self._get_surveillance_keyboard())
                return

            if clean_t.startswith("/pantalla") or clean_t.startswith("/mirar_pantalla") or any(kw in clean_t for kw in ["mira la pantalla", "mirá la pantalla", "que hay en la pantalla", "qué hay en la pantalla", "que ves en la pantalla", "qué ves en la pantalla"]):
                user_q = text
                for pfx in ["/pantalla", "/mirar_pantalla", "mirá la pantalla", "mira la pantalla"]:
                    if user_q.lower().startswith(pfx):
                        user_q = user_q[len(pfx):].strip()
                        break
                if not user_q:
                    user_q = "Describí qué hay abierto en la pantalla de la computadora y qué se ve"

                await self._send_chat_action(chat_id, "upload_photo")
                from tools.system_control import system_control
                from brain.gemini_client import brain
                from audio.tts import tts
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, system_control.take_screenshot)
                if res.get("status") == "success":
                    photo_bytes = None
                    if res.get("photo_base64"):
                        import base64
                        try:
                            photo_bytes = base64.b64decode(res["photo_base64"])
                        except Exception:
                            pass
                    elif res.get("path") and os.path.exists(res["path"]):
                        with open(res["path"], "rb") as f:
                            photo_bytes = f.read()

                    if photo_bytes:
                        await self._send_chat_action(chat_id, "record_voice")
                        vision_reply = await brain.analyze_screen(photo_bytes, question=user_q)
                        cap = f"👁️ *Visión de Pantalla:*\n{vision_reply}"
                        if len(cap) <= 1024:
                            await self._send_photo(chat_id, photo_bytes, caption=cap)
                        else:
                            await self._send_photo(chat_id, photo_bytes, caption="📸 Captura de pantalla de la PC")
                            await self._send_text(chat_id, cap)

                        should_send_voice = getattr(self, "voice_responses", True) or from_voice
                        if should_send_voice:
                            try:
                                voice_bytes = await tts.synthesize_to_bytes(vision_reply)
                                if voice_bytes:
                                    await self._send_voice(chat_id, voice_bytes)
                            except Exception as ex_v:
                                log_warning(f"[Telegram] Error generando voz para pantalla: {ex_v}")
                        return

                await self._send_text(chat_id, res.get("message", "No se pudo tomar la captura de pantalla en este momento (¿PC desconectada?)."))
                return

            # Intención rápida: Foto con J2
            if any(kw in clean_t for kw in ["foto j2", "foto del j2", "foto con el j2", "foto de la pieza", "sacá foto con el j2", "saca foto con el j2", "sacá una foto con el j2", "saca una foto con el j2", "sacame una foto con el j2"]):
                from tools.j2_camera import j2_camera
                await self._send_chat_action(chat_id, "upload_photo")
                photo_bytes = await j2_camera.capture_photo(timeout=8.0)
                if photo_bytes:
                    caption = f"📸 Foto en vivo desde el Samsung J2 ({j2_camera.get_facing_label()})"
                    if from_voice:
                        caption = f"🎙️ *Escuché:* \"_{text}_\"\n\n{caption}"
                    await self._send_photo(chat_id, photo_bytes, caption=caption)
                    return

            # Intención rápida: Vigilancia de habitación con IA
            if any(kw in clean_t for kw in ["vigilá la pieza", "vigila la pieza", "vigilar pieza", "hay alguien en mi pieza", "hay alguien en la pieza", "revisá la pieza", "revisa la pieza", "que pasa en mi pieza", "qué pasa en mi pieza", "que pasa en la pieza"]):
                from tools.j2_camera import j2_camera
                from brain.gemini_client import brain
                from audio.tts import tts
                await self._send_chat_action(chat_id, "upload_photo")
                photo_bytes = await j2_camera.capture_photo(timeout=8.0)
                if photo_bytes:
                    caption = f"👁️ *Vigilancia J2 ({j2_camera.get_facing_label()}):*\nAnalizando con Gemini Visión..."
                    await self._send_photo(chat_id, photo_bytes, caption=caption)
                    question = (
                        "Actuá como Titán vigilando la habitación a través de la cámara del Samsung J2. "
                        "Decile qué ves exactamente: si hay personas, si hay movimiento, si la luz está prendida o apagada, "
                        "o si está todo en orden. Respondé con tu tonada y personalidad argentina por voz."
                    )
                    analysis = await brain.analyze_vision(photo_bytes, question=question)
                    voice_bytes = await tts.synthesize_to_bytes(analysis)
                    if voice_bytes:
                        await self._send_voice(chat_id, voice_bytes, caption="🎙️ Reporte de seguridad")
                    else:
                        await self._send_text(chat_id, f"🛡️ *Reporte de Titán:*\n{analysis}")
                    return

            # 1. Probar intención local rápida
            handled, local_reply = local_intents.try_handle(text)
            if handled and local_reply:
                state_mgr.add_user_message(f"[Telegram] {text}")
                out_text = f"🎙️ *Escuché:* \"_{text}_\"\n\n{local_reply}" if from_voice else local_reply
                await self._send_text(chat_id, out_text)
                should_send_voice = getattr(self, "voice_responses", True) or from_voice
                if should_send_voice:
                    spoken = self.prepare_text_for_voice_note(local_reply)
                    if spoken:
                        try:
                            voice_bytes = await tts.synthesize_to_bytes(spoken)
                            if voice_bytes:
                                await self._send_voice(chat_id, voice_bytes)
                        except Exception as ex_v:
                            log_warning(f"[Telegram] Error generando voz local: {ex_v}")
                return

            # 2. Consultar a Gemini
            state_mgr.add_user_message(f"[Telegram] {text}")
            reply = await brain.process_user_input(text)

            # Enviar texto de inmediato al usuario para lectura instantánea
            out_msg = f"🎙️ *Escuché:* \"_{text}_\"\n\n{reply}" if from_voice else reply
            await self._send_text(chat_id, out_msg)

            # Sintetizar audio y mandar nota de voz de Titán en segundo plano
            should_send_voice = getattr(self, "voice_responses", True) or from_voice
            if should_send_voice:
                spoken = self.prepare_text_for_voice_note(reply)
                if spoken:
                    try:
                        voice_bytes = await tts.synthesize_to_bytes(spoken)
                        if voice_bytes:
                            await self._send_voice(chat_id, voice_bytes)
                    except Exception as e_voice:
                        log_warning(f"[Telegram] Error generando nota de voz: {e_voice}")

        except Exception as e:
            log_error(f"[Telegram] Error en _handle_text_message: {e}")
            await self._send_text(chat_id, "Che, se me complicó procesar tu mensaje. Bancame un segundo y probá de nuevo.")
        finally:
            pulse_task.cancel()

    async def _handle_voice_message(self, chat_id: int, voice_obj: Dict[str, Any]):
        file_id = voice_obj.get("file_id")
        if not file_id or not self.client:
            return

        pulse_task = asyncio.create_task(self._chat_action_pulse(chat_id, "record_voice"))

        try:
            # Obtener ruta de descarga del archivo en Telegram
            r = await self.client.get(f"{self.api_url}/getFile", params={"file_id": file_id})
            file_data = r.json()
            if not file_data.get("ok"):
                await self._send_text(chat_id, "Che, no pude descargar el audio de Telegram.")
                return

            file_path = file_data["result"]["file_path"]
            dl_url = f"{self.file_url}/{file_path}"
            r_audio = await self.client.get(dl_url)
            audio_bytes = r_audio.content

            # Transcribir con reconocimiento de voz en español argentino
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._transcribe_audio_bytes, audio_bytes)

            if text and text.strip():
                log_info(f"[Telegram Audio] Transcrito exitosamente: '{text}'")
                await self._handle_text_message(chat_id, text, from_voice=True)
            else:
                log_warning("[Telegram Audio] Audio no reconocido o inaudible")
                await self._send_text(
                    chat_id,
                    "Che, no se llegó a entender bien el audio. ¿Me lo repetís un cachito más claro o me lo escribís, papá?"
                )

        except Exception as e:
            log_error(f"[Telegram] Error procesando nota de voz: {e}")
            await self._send_text(chat_id, f"Hubo un bardo al escuchar tu nota de voz: {e}")
        finally:
            pulse_task.cancel()

    def _get_tv_keyboard(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [
                    {"text": "⏻ Prender / Apagar", "callback_data": "tv:power"}
                ],
                [
                    {"text": "🔉 Vol -", "callback_data": "tv:voldown"},
                    {"text": "🔊 Vol +", "callback_data": "tv:volup"},
                    {"text": "🔇 Mute", "callback_data": "tv:mute"}
                ],
                [
                    {"text": "⏯ Play / Pausa", "callback_data": "tv:playpause"},
                    {"text": "🏠 Inicio", "callback_data": "tv:home"},
                    {"text": "🔙 Atrás", "callback_data": "tv:back"}
                ],
                [
                    {"text": "🔴 OnPlay TV", "callback_data": "tv:onplay"},
                    {"text": "▶️ YouTube", "callback_data": "tv:youtube"},
                    {"text": "🎬 Netflix", "callback_data": "tv:netflix"}
                ],
                [
                    {"text": "⚽ ESPN Premium", "callback_data": "tv:ch:15"},
                    {"text": "⚽ TNT Sports", "callback_data": "tv:ch:16"},
                    {"text": "🏊 TyC Sports", "callback_data": "tv:ch:17"}
                ],
                [
                    {"text": "📺 Telefe", "callback_data": "tv:ch:4"},
                    {"text": "📰 TN", "callback_data": "tv:ch:6"},
                    {"text": "🎬 HBO", "callback_data": "tv:ch:45"}
                ]
            ]
        }

    async def _handle_tv_command(self, chat_id: int, text: str):
        from tools.tv_control import tv_control
        parts = text.strip().split()
        if len(parts) == 1:
            st = tv_control.get_status()
            pwr = st.get("power", "desconocido")
            msg = (
                f"📺 *Control Remoto BGH Android TV*\n"
                f"• Estado: *{pwr.upper()}*\n"
                f"• IP: `{st.get('ip')}`\n"
                f"• Canales OnPlay: *97 disponibles*\n\n"
                f"Tocá un botón, pedime cualquier canal por voz/texto (ej: `/tv espn premium` o `/tv 17`) o usá los controles:"
            )
            await self._send_text(chat_id, msg, reply_markup=self._get_tv_keyboard())
            return

        arg = parts[1].lower()
        if arg in ["on", "prender", "prende"]:
            res = tv_control.turn_on()
        elif arg in ["off", "apagar", "apaga"]:
            res = tv_control.turn_off()
        elif arg in ["canales", "lista"]:
            # Enviar listado resumido de canales
            channels = tv_control.list_channels()
            categories = {}
            for c in channels:
                categories.setdefault(c["category"], []).append(f"{c['number']}. {c['name']}")
            lines = ["📺 *Canales de OnPlay:*"]
            for cat, ch_list in categories.items():
                lines.append(f"\n📂 *{cat}:*")
                lines.append(", ".join(ch_list[:6]) + (f" (+{len(ch_list)-6})" if len(ch_list) > 6 else ""))
            lines.append("\n_Pedí cualquiera diciendo: 'pone espn premium' o '/tv <canal>'._")
            await self._send_text(chat_id, "\n".join(lines), reply_markup=self._get_tv_keyboard())
            return
        elif arg in ["onplay"] and len(parts) == 2:
            res = tv_control.open_onplay_live()
        elif arg in ["youtube", "yt"]:
            res = tv_control.open_app("smarttube")
        elif arg in ["netflix"]:
            res = tv_control.open_app("netflix")
        elif arg in ["pausa", "play"]:
            res = tv_control.play_pause()
        elif arg in ["mute", "silencio"]:
            res = tv_control.mute()
        elif arg in ["vol", "volumen"] and len(parts) > 2 and parts[2].isdigit():
            res = tv_control.set_volume(int(parts[2]))
        else:
            # Intentar sintonizar canal por nombre o número (ej: "/tv espn premium", "/tv 17", "/tv telefe")
            query = " ".join(parts[1:])
            res = tv_control.tune_channel(query)

        await self._send_text(chat_id, res.get("message", "Listo, comando ejecutado."), reply_markup=self._get_tv_keyboard())

telegram_service = TelegramBotService()

async def send_file_to_owner(file_path: str, caption: Optional[str] = None) -> bool:
    """Envía un archivo de la PC directamente al dueño en Telegram"""
    if not telegram_service.allowed_user_id or not telegram_service.client:
        return False
    try:
        chat_id = int(telegram_service.allowed_user_id)
        return await telegram_service._send_document(chat_id, file_path, caption)
    except Exception as e:
        log_error(f"[Telegram] Error en send_file_to_owner: {e}")
        return False

async def send_message_to_owner(text: str) -> bool:
    """Envía un mensaje de texto al dueño en Telegram"""
    if not telegram_service.allowed_user_id or not telegram_service.client:
        return False
    try:
        chat_id = int(telegram_service.allowed_user_id)
        await telegram_service._send_text(chat_id, text)
        return True
    except Exception as e:
        log_error(f"[Telegram] Error en send_message_to_owner: {e}")
        return False

async def send_photo_to_owner(photo_bytes: bytes, caption: Optional[str] = None) -> bool:
    """Envía una foto directamente al dueño en Telegram"""
    if not telegram_service.allowed_user_id or not telegram_service.client:
        return False
    try:
        chat_id = int(telegram_service.allowed_user_id)
        await telegram_service._send_photo(chat_id, photo_bytes, caption)
        return True
    except Exception as e:
        log_error(f"[Telegram] Error en send_photo_to_owner: {e}")
        return False

async def send_voice_to_owner(voice_bytes: bytes, caption: Optional[str] = None) -> bool:
    """Envía una nota de voz directamente al dueño en Telegram"""
    if not telegram_service.allowed_user_id or not telegram_service.client:
        return False
    try:
        chat_id = int(telegram_service.allowed_user_id)
        await telegram_service._send_voice(chat_id, voice_bytes, caption)
        return True
    except Exception as e:
        log_error(f"[Telegram] Error en send_voice_to_owner: {e}")
        return False

