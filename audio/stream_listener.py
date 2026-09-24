import asyncio
import time
import numpy as np
import speech_recognition as sr
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from core.logger import log_info, log_warning, log_error
from core.state_manager import state_mgr, AssistantState
from audio.wake_word import wake_detector

# Huella de voz (2026-09-17): pool chico para pedir el embedding al satélite
# EN PARALELO con el reconocimiento de voz, sin frenar la respuesta.
_HUELLAPOOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="huella")

class StreamAudioListener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.sample_width = 2
        self.is_listening = True
        
        # Umbrales de sensibilidad de voz
        self.energy_threshold = 45.0   # Ultra sensible para captar susurros y voz tranquila desde cualquier rincón
        self.barge_in_threshold = 720.0  # Calibrado alto para evitar auto-corte con los parlantes de la PC
        self.barge_in_needed = 4         # Requiere 4 bloques (~360ms) de voz intencional
        self.barge_in_hits = 0
        
        self.silence_chunks_needed = 6   # ~0.55 seg de silencio tras hablar (pausa natural entre palabras)
        self.min_speech_chunks = 3       # minimo ~0.28 seg de audio
        
        self.buffer = []
        self.silence_counter = 0
        self.speech_detected = False
        self._on_command_callback: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_processing = False
        self._barge_in_buffer = []
        self._barge_in_silence = 0
        self._is_barge_in_processing = False
        
        # Estado de espera de orden tras decir palabra clave o post-respuesta
        self.is_waiting_for_command = False
        self.command_wait_expires = 0.0

    def set_command_callback(self, cb: Callable, loop: asyncio.AbstractEventLoop):
        self._on_command_callback = cb
        self._loop = loop

    def enter_conversational_turn(self, timeout: float = 9.0):
        """Mantiene la escucha abierta para continuar la charla sin decir la palabra clave"""
        self.is_waiting_for_command = True
        self.command_wait_expires = time.time() + timeout
        state_mgr.set_state(AssistantState.LISTENING, "Te escucho... (seguí hablando o decí 'chau')")
        state_mgr._notify({"type": "conversational_active", "timeout": timeout})
        
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._watch_conversational_expiry(self.command_wait_expires), self._loop)

    async def _watch_conversational_expiry(self, target_expiry: float):
        sleep_dur = max(0.5, target_expiry - time.time() + 0.2)
        await asyncio.sleep(sleep_dur)
        if self.is_waiting_for_command and time.time() >= self.command_wait_expires:
            if state_mgr.current_state == AssistantState.LISTENING:
                self.is_waiting_for_command = False
                from audio.listener import listener
                listener.is_waiting_for_command = False
                state_mgr.set_state(AssistantState.IDLE, "En espera de activación")
                state_mgr._notify({"type": "conversational_ended"})

    def trigger_manual_listen(self):
        """Activa la escucha de orden inmediatamente (botón hablar o atajo)"""
        self.is_waiting_for_command = True
        self.command_wait_expires = time.time() + 12.0
        state_mgr.set_state(AssistantState.LISTENING, "Escuchando tu orden...")

    def interrupt_speech(self):
        """Interrupción inmediata (táctil o comando)"""
        from audio.tts import tts
        tts.stop()
        self.buffer.clear()
        self._barge_in_buffer.clear()
        self.speech_detected = False
        self.barge_in_hits = 0
        self.is_waiting_for_command = True
        self.command_wait_expires = time.time() + 10.0
        state_mgr.set_state(AssistantState.LISTENING, "Te escucho...")
        state_mgr._notify({"type": "wake_pulse"})

    def process_pcm_chunk(self, chunk: bytes):
        if not self.is_listening or len(chunk) < 100:
            return

        # Si NO está en manos libres (Pulsar para hablar) y NO hay orden activa, ignorar audio ambiental
        if not getattr(state_mgr, "is_hands_free", True) and not self.is_waiting_for_command:
            return

        # Si el asistente está hablando: evaluar interrupción semántica por voz
        if state_mgr.current_state == AssistantState.SPEAKING:
            try:
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(samples**2)))
            except Exception:
                return

            if rms > self.energy_threshold:
                self._barge_in_buffer.append(chunk)
                self._barge_in_silence = 0
                if len(self._barge_in_buffer) > 60:
                    self._barge_in_buffer.pop(0)
            elif len(self._barge_in_buffer) > 0:
                self._barge_in_buffer.append(chunk)
                self._barge_in_silence += 1
                if self._barge_in_silence >= 3 and len(self._barge_in_buffer) >= 4 and not self._is_barge_in_processing:
                    audio_data = b"".join(self._barge_in_buffer)
                    self._barge_in_buffer.clear()
                    self._barge_in_silence = 0
                    if self._loop:
                        self._is_barge_in_processing = True
                        self._loop.run_in_executor(None, self._recognize_barge_in, audio_data)
            return

        self.barge_in_hits = 0

        try:
            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
            rms = float(np.sqrt(np.mean(samples**2)))
        except Exception:
            return

        # Si el volumen supera el umbral, consideramos que hay alguien hablando
        if rms > self.energy_threshold:
            self.speech_detected = True
            self.silence_counter = 0
            self.buffer.append(chunk)
            if len(self.buffer) > 140:
                self.buffer.pop(0)
        elif self.speech_detected:
            self.buffer.append(chunk)
            self.silence_counter += 1

            # Detectó silencio después de hablar: procesar fragmento
            if self.silence_counter >= self.silence_chunks_needed:
                if len(self.buffer) >= self.min_speech_chunks and not self._is_processing:
                    audio_data = b"".join(self.buffer)
                    if self._loop:
                        self._is_processing = True
                        self._loop.run_in_executor(None, self._recognize_and_dispatch, audio_data)
                
                self.buffer.clear()
                self.speech_detected = False
                self.silence_counter = 0

    def _recognize_and_dispatch(self, audio_bytes: bytes):
        # 2026-09-17 — Huella de voz: si hay un registro en curso ("registrá
        # mi voz"), el audio va al enroller: no se transcribe ni se procesa
        # como orden.
        try:
            from audio.speaker_id import enrollment_active, handle_enrollment_audio
            if enrollment_active():
                try:
                    prompt = handle_enrollment_audio(audio_bytes, self.sample_rate, self._loop)
                    if prompt and self._loop:
                        from audio.tts import tts
                        asyncio.run_coroutine_threadsafe(tts.speak(prompt, auto_listen=True), self._loop)
                finally:
                    self._is_processing = False
                return
        except Exception as ex:
            log_warning(f"[Huella] error en registro: {ex}")
            self._is_processing = False
            return

        # 2026-09-17 — Huella de voz: pedir el embedding al satélite EN
        # PARALELO con el STT (no suma latencia: el satélite tarda menos
        # que Google en devolver el texto). Solo si hay huella registrada.
        huella_future = None
        try:
            from audio import speaker_id as huella
            if huella.list_voiceprints() and self._loop is not None:
                huella_future = _HUELLAPOOL.submit(
                    huella.fetch_embedding, audio_bytes, self.sample_rate, self._loop, 5.0)
        except Exception:
            huella_future = None

        try:
            audio = sr.AudioData(audio_bytes, self.sample_rate, self.sample_width)
            text = self.recognizer.recognize_google(audio, language="es-AR")
            if not text or not text.strip():
                return

            # Análisis de tono acústico del interlocutor (Hombre / Mujer / Niño):
            try:
                from audio.voice_detector import detect_speaker
                spk_type, spk_pitch = detect_speaker(audio_bytes, self.sample_rate)
                if spk_type != "desconocido":
                    state_mgr.set_speaker(spk_type, spk_pitch)
                    log_info(f"[Detector de Voz Móvil] Interlocutor detectado: {spk_type} ({spk_pitch} Hz)")
            except Exception:
                pass

            from audio.tts import tts
            if tts.is_self_echo(text):
                log_info(f"[Mic Celular Anti-Eco] Audio descartado por ser eco de Titán: '{text}'")
                return

            # 2026-09-17 — Huella de voz: el embedding ya debería estar listo
            # (corrió en paralelo); comparar acá para que el cerebro sepa
            # QUIÉN habla antes de responder.
            if huella_future is not None:
                try:
                    from audio import speaker_id as huella
                    emb = huella_future.result(timeout=4.0)
                    if emb:
                        identity, score = huella.match_embedding(emb)
                        state_mgr.set_speaker_identity(identity, score)
                except Exception:
                    pass

            now = time.time()
            from audio.speaker_monitor import speaker_monitor
            media_active = speaker_monitor.is_media_active()

            if media_active:
                # Si los parlantes o Spotify están sonando, apagar charla continua
                self.is_waiting_for_command = False

            # Caso 1: Charla continua o esperando orden (sin repetir palabra clave, SOLO si no hay música de fondo)
            if not media_active and self.is_waiting_for_command and (now < self.command_wait_expires):
                self.is_waiting_for_command = False
                log_info(f"[Mic Celular] Conversación continua: '{text}'")
                if self._loop and self._on_command_callback:
                    asyncio.run_coroutine_threadsafe(self._on_command_callback(text), self._loop)
                return

            # Caso 2: Esperando palabra de activación ("Titán")
            detected, remainder = wake_detector.check(text)
            if detected:
                log_info(f"[Mic Celular] Palabra clave detectada: '{text}' (restante: '{remainder}')")
                speaker_monitor.duck(0.15)
                state_mgr._notify({"type": "wake_pulse"})
                if remainder:
                    self.is_waiting_for_command = False
                    if self._loop and self._on_command_callback:
                        fut = asyncio.run_coroutine_threadsafe(self._on_command_callback(remainder), self._loop)
                        # B-14: igual que en listener.py — restaurar el volumen
                        # cuando la orden termina de procesarse (este archivo
                        # ni siquiera tenía un unduck en el camino de éxito).
                        def _restore_volume(f):
                            try:
                                f.result()  # consume la excepción si la hubo
                            except Exception:
                                pass
                            try:
                                speaker_monitor.unduck()
                            except Exception:
                                pass
                        fut.add_done_callback(_restore_volume)
                else:
                    self.is_waiting_for_command = True
                    self.command_wait_expires = time.time() + 12.0
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(self._wake_prompt(), self._loop)
            else:
                log_info(f"[Mic Celular] Escuchó: '{text}' (no contiene palabra clave)")
        except sr.UnknownValueError:
            pass
        except Exception as ex:
            log_warning(f"[Mic Celular] Error en reconocimiento: {ex}")
        finally:
            self._is_processing = False

    def _recognize_barge_in(self, audio_bytes: bytes):
        """Verifica si el usuario dijo una palabra de corte o invocó a Titán mientras habla"""
        try:
            audio = sr.AudioData(audio_bytes, self.sample_rate, self.sample_width)
            text = self.recognizer.recognize_google(audio, language="es-AR").lower().strip()
            if not text:
                return

            from audio.tts import tts
            current_spoken = getattr(tts, "current_text", "").lower()

            # Filtro Anti-Eco avanzado: si el texto o sus palabras coinciden con lo que Titán dice, es eco propio
            cleaned_text = "".join(c for c in text if c.isalnum() or c.isspace()).strip()
            cleaned_spoken = "".join(c for c in current_spoken if c.isalnum() or c.isspace()).strip()
            if cleaned_spoken and cleaned_text:
                if cleaned_text in cleaned_spoken or cleaned_spoken.startswith(cleaned_text):
                    log_info(f"[Anti-Eco] Sonido ignorado porque es el propio eco de Titán: '{text}'")
                    return
                words_heard = [w for w in cleaned_text.split() if len(w) > 2]
                if words_heard:
                    overlap = sum(1 for w in words_heard if w in cleaned_spoken)
                    if (overlap / len(words_heard)) >= 0.4:
                        log_info(f"[Anti-Eco] Eco acústico filtrado por coincidencia de palabras ({overlap}/{len(words_heard)}): '{text}'")
                        return

            # Interrupción por voz (Barge-In) SOLO con frases compuestas completas (NUNCA palabras sueltas)
            from audio.wake_word import check_barge_in_phrase
            is_barge, matched_phrase = check_barge_in_phrase(text)

            if is_barge:
                log_info(f"[Barge-In por Voz Móvil] Interrupción detectada por frase compuesta: '{text}' (frase: '{matched_phrase}')")
                tts.stop()

                # Comandos directos de corte / parada / silencio
                stop_phrase_patterns = ["pará", "para", "callate", "cállate", "silencio", "basta", "frená", "frena"]
                if any(p in matched_phrase for p in stop_phrase_patterns):
                    state_mgr.set_state(AssistantState.IDLE, "En espera")
                    self.buffer.clear()
                    self._barge_in_buffer.clear()
                    self.is_waiting_for_command = False
                    return

                # Si llamó para dar una orden nueva (ej: "ehu titán abrí chrome" o "ehu titán")
                self.interrupt_speech()
                detected, remainder = wake_detector.check(text)
                if remainder and self._loop and self._on_command_callback:
                    asyncio.run_coroutine_threadsafe(self._on_command_callback(remainder), self._loop)
                else:
                    self.is_waiting_for_command = True
                    self.command_wait_expires = time.time() + 10.0
                    state_mgr.set_state(AssistantState.LISTENING, "Te escucho...")
        except Exception:
            pass
        finally:
            self._is_barge_in_processing = False

    async def _wake_prompt(self):
        from audio.tts import tts
        state_mgr.set_state(AssistantState.LISTENING, "Decime che, te escucho...")
        await tts.speak("Decime che, te escucho.", auto_listen=True)

stream_listener = StreamAudioListener()
