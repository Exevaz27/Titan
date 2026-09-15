import asyncio
import threading
import time
import numpy as np
import speech_recognition as sr
from typing import Optional, Callable, Any
from core.state_manager import state_mgr, AssistantState
from core.logger import log_info, log_error, log_warning, log_success
from audio.wake_word import wake_detector

class AudioListener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 240
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.3
        self.recognizer.pause_threshold = 1.0
        self.recognizer.non_speaking_duration = 0.5
        self.microphone: Optional[sr.Microphone] = None
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._on_command_callback: Optional[Callable[[str], Any]] = None
        self._force_listen_event = threading.Event()
        self.is_waiting_for_command = False
        self.command_wait_expires = 0.0

    def enter_conversational_turn(self, timeout: float = 10.0):
        """Mantiene la escucha abierta en el micrófono de la PC para responder sin decir 'Titán'"""
        self.is_waiting_for_command = True
        self.command_wait_expires = time.time() + timeout

    def setup_microphone(self, silent: bool = False) -> bool:
        try:
            import ctypes
            try:
                if ctypes.windll.winmm.waveInGetNumDevs() == 0:
                    self.microphone = None
                    return False
            except Exception:
                pass

            mic = sr.Microphone()
            with mic as source:
                log_info("Calibrando ruido ambiental del micrófono de la PC...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
                calib = int(self.recognizer.energy_threshold)
                self.recognizer.energy_threshold = max(140, min(calib, 350))
                self.recognizer.dynamic_energy_threshold = False
                log_info(f"Calibración completada (Umbral de energía: {int(self.recognizer.energy_threshold)})")
            self.microphone = mic
            return True
        except Exception as e:
            self.microphone = None
            if not silent:
                log_error(f"No se pudo acceder al micrófono: {e}")
            return False

    def register_command_handler(self, handler: Callable[[str], Any]):
        self._on_command_callback = handler

    def trigger_manual_listen(self):
        """Disparado por Atajo de Teclado o Botón Web en la pantalla secundaria"""
        log_info("Escucha manual activada (Hotkey o Botón Web)")
        self._force_listen_event.set()
        try:
            from audio.stream_listener import stream_listener
            stream_listener.trigger_manual_listen()
        except Exception:
            pass

    def start(self, loop: asyncio.AbstractEventLoop):
        if self._is_running:
            return
        self._is_running = True

        if not self.microphone:
            if not self.setup_microphone(silent=True):
                log_warning("Iniciando sin micrófono local activo en la PC (se usará micrófono del celular y atajos). Buscando en segundo plano si conectás uno...")

        self._thread = threading.Thread(target=self._listen_loop, args=(loop,), daemon=True)
        self._thread.start()
        log_info("Detector de voz iniciado en segundo plano")

    def stop(self):
        self._is_running = False

    def _listen_loop(self, loop: asyncio.AbstractEventLoop):
        has_logged_no_mic = False
        while self._is_running:
            if not self.microphone:
                # Si el usuario presionó la tecla o botón pero no hay micrófono en la PC:
                if self._force_listen_event.is_set():
                    self._force_listen_event.clear()
                    from server.web_server import has_active_mobile_mic
                    if not has_active_mobile_mic():
                        from audio.tts import tts
                        log_warning("Atajo presionado sin micrófono de PC ni celular conectado")
                        state_mgr.set_state(AssistantState.IDLE, "⚠️ Sin micrófono en PC. Conectalo o usá el cel")
                        asyncio.run_coroutine_threadsafe(tts.speak("Che, no detecto ningún micrófono conectado en la compu. Revisá que el cable rosa o USB esté bien enchufado, o hablame desde la pantalla del celu."), loop)
                    else:
                        log_info("Atajo manual activado: escuchando a través del micrófono del celular")

                if not self.setup_microphone(silent=True):
                    if not has_logged_no_mic:
                        log_warning("[Mic PC] No hay micrófono detectado en la PC. Esperando conexión o audio desde el celular...")
                        has_logged_no_mic = True
                    threading.Event().wait(2.0)
                    continue
                else:
                    has_logged_no_mic = False
                    log_success("¡Micrófono de la PC detectado y activado con éxito en caliente!")
                    state_mgr.set_state(AssistantState.IDLE, "En espera de activación")

            try:
                with self.microphone as source:
                    while self._is_running:
                        from audio.tts import tts
                        is_speaking = state_mgr.current_state == AssistantState.SPEAKING or getattr(tts, "_is_speaking", False)

                        # 1. Comprobar si hubo un trigger manual (botón / atajo)
                        if self._force_listen_event.is_set():
                            self._force_listen_event.clear()
                            self._capture_and_dispatch(source, loop, prompt="Escuchando tu orden...")
                            continue

                        now = time.time()
                        from audio.speaker_monitor import speaker_monitor
                        media_active = speaker_monitor.is_media_active()

                        if media_active:
                            # Si los parlantes o Spotify están sonando, apagar el modo conversacional abierto
                            # para NUNCA confundir letras de canciones o sonidos de juegos con órdenes del usuario
                            self.is_waiting_for_command = False
                            was_conversing = False
                        else:
                            was_conversing = self.is_waiting_for_command and (now < self.command_wait_expires)

                        # Si NO está en modo manos libres (Pulsar para hablar) y NO hay conversación abierta:
                        if not getattr(state_mgr, "is_hands_free", True) and not was_conversing:
                            # Dormir y esperar únicamente a que el usuario presione Ctrl+Espacio o el botón
                            self._force_listen_event.wait(timeout=0.5)
                            if self._force_listen_event.is_set():
                                self._force_listen_event.clear()
                                speaker_monitor.duck(0.15)
                                self._capture_and_dispatch(source, loop, prompt="Escuchando tu orden...")
                            continue

                        # 2. Configurar tiempo de escucha:
                        # Si está hablando: ventanas cortas (2.0s) para detectar interrupciones inmediatas ("pará", "callate", "basta")
                        # Si no está hablando: tiempo normal (5.0s o 8.0s si conversa)
                        time_limit = 2.0 if is_speaking else (9.0 if was_conversing else 6.0)
                        listen_timeout = 0.8 if is_speaking else 2.0

                        try:
                            audio = self.recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=time_limit)
                        except sr.WaitTimeoutError:
                            if self.is_waiting_for_command and time.time() >= self.command_wait_expires:
                                self.is_waiting_for_command = False
                            continue

                        if not self._is_running:
                            break

                        # Extraer nivel de audio para el visualizador
                        self._emit_volume(audio)

                        # Intentar transcribir
                        try:
                            text = self.recognizer.recognize_google(audio, language="es-AR")
                            if not text or not text.strip():
                                continue

                            log_info(f"[Mic PC] Texto reconocido: '{text}'")
                            clean_lower = text.lower().strip()

                            # A0. DETECTOR DE VOZ E INTERLOCUTOR (Hombre / Mujer / Niño):
                            try:
                                from audio.voice_detector import detect_speaker
                                spk_type, spk_pitch = detect_speaker(audio.get_raw_data(), audio.sample_rate)
                                if spk_type != "desconocido":
                                    state_mgr.set_speaker(spk_type, spk_pitch)
                                    log_info(f"[Detector de Voz PC] Interlocutor detectado: {spk_type} ({spk_pitch} Hz)")
                            except Exception:
                                pass

                            # A. FILTRO ANTI-ECO: Si coincide con lo que Titán acaba de decir por los parlantes, descartar
                            if tts.is_self_echo(clean_lower):
                                continue

                            # B. MODO INTERRUPCIÓN RÁPIDA (Barge-In) mientras Titán está hablando:
                            if is_speaking or getattr(tts, "_is_speaking", False):
                                from audio.wake_word import check_barge_in_phrase
                                is_barge, matched_phrase = check_barge_in_phrase(clean_lower)
                                if is_barge:
                                    log_info(f"[Barge-In PC] ¡Interrupción detectada por frase compuesta! '{text}' (frase: '{matched_phrase}') -> Frenando a Titán.")
                                    tts.stop()
                                    self.is_waiting_for_command = True
                                    self.command_wait_expires = time.time() + 10.0
                                    state_mgr.set_state(AssistantState.LISTENING, "Te escucho...")
                                    continue
                                else:
                                    # Mientras habla, si no fue una frase compuesta de interrupción, descartar para evitar auto-interrupciones o falsos positivos
                                    continue

                            # C. MODO NORMAL (Titán NO está hablando):
                            # Si recién terminó de hablar (menos de 0.4s), chequear margen de eco residual
                            if time.time() - getattr(tts, "last_speech_time", 0) < 0.4:
                                continue

                            detected, remainder = wake_detector.check(text)
                            log_info(f"[Mic PC] Wake check: detectado={detected} para '{text}'")
                            if detected:
                                self.is_waiting_for_command = False
                                log_info(f"Palabra clave detectada en PC: '{text}' (restante: '{remainder}')")
                                cmd_to_send = remainder if remainder else text

                                # Detección de frase incompleta por pausa natural (ej: "prende la tele y", "pone")
                                rem_clean = cmd_to_send.lower().strip()
                                if rem_clean.endswith((" y", " e", " o", " y pone", " y poné", " y sintoniza", " para", " con", " pero")):
                                    log_info(f"[Mic PC] Frase incompleta detectada ('{cmd_to_send}'). Escuchando continuación...")
                                    try:
                                        cont_audio = self.recognizer.listen(source, timeout=2.5, phrase_time_limit=5.0)
                                        cont_text = self.recognizer.recognize_google(cont_audio, language="es-AR")
                                        if cont_text and cont_text.strip():
                                            log_info(f"[Mic PC] Continuación recibida: '{cont_text}'")
                                            cmd_to_send = f"{cmd_to_send} {cont_text.strip()}"
                                    except Exception:
                                        pass

                                speaker_monitor.duck(0.15)
                                if self._on_command_callback:
                                    asyncio.run_coroutine_threadsafe(self._on_command_callback(cmd_to_send), loop)
                            elif was_conversing and not media_active:
                                self.is_waiting_for_command = False
                                log_info(f"[Mic PC] Conversación continua: '{text}'")
                                if self._on_command_callback:
                                    asyncio.run_coroutine_threadsafe(self._on_command_callback(text), loop)
                        except sr.UnknownValueError:
                            pass
                        except sr.RequestError as e:
                            log_warning(f"Error de conexión STT: {e}")

            except Exception as e:
                log_warning(f"Aviso en micrófono de la PC: {e}. Reintentando...")
                try:
                    if self.microphone and hasattr(self.microphone, "stream") and self.microphone.stream:
                        self.microphone.stream.close()
                except Exception:
                    pass
                self.microphone = None
                state_mgr.set_state(AssistantState.IDLE, "⚠️ Micrófono desconectado")
                threading.Event().wait(2.0)

    def _capture_and_dispatch(self, source, loop: asyncio.AbstractEventLoop, prompt: str = "Escuchando orden..."):
        """Captura síncronamente el audio en el hilo del micrófono para evitar colisiones PortAudio"""
        from audio.tts import tts
        from audio.speaker_monitor import speaker_monitor
        speaker_monitor.duck(0.15)
        state_mgr.set_state(AssistantState.LISTENING, prompt)
        try:
            audio = self.recognizer.listen(source, timeout=6.0, phrase_time_limit=10.0)
            # Si mientras escuchaba el asistente habló, descartar
            if state_mgr.current_state == AssistantState.SPEAKING or getattr(tts, "_is_speaking", False) or (time.time() - getattr(tts, "last_speech_time", 0) < 0.5):
                state_mgr.set_state(AssistantState.IDLE, "En espera")
                speaker_monitor.unduck()
                return

            state_mgr.set_state(AssistantState.PROCESSING, "Transcribiendo audio...")
            text = self.recognizer.recognize_google(audio, language="es-AR")
            if text and text.strip():
                try:
                    from audio.voice_detector import detect_speaker
                    spk_type, spk_pitch = detect_speaker(audio.get_raw_data(), audio.sample_rate)
                    if spk_type != "desconocido":
                        state_mgr.set_speaker(spk_type, spk_pitch)
                        log_info(f"[Detector de Voz PC Activo] Interlocutor detectado: {spk_type} ({spk_pitch} Hz)")
                except Exception:
                    pass

                if tts.is_self_echo(text):
                    log_info(f"[Mic PC Anti-Eco] Orden descartada por ser eco de Titán: '{text}'")
                    state_mgr.set_state(AssistantState.IDLE, "En espera")
                    speaker_monitor.unduck()
                    return
                log_info(f"Orden reconocida (PC): '{text}'")
                if self._on_command_callback:
                    asyncio.run_coroutine_threadsafe(self._on_command_callback(text), loop)
            else:
                state_mgr.set_state(AssistantState.IDLE, "No se detectó ninguna orden")
                speaker_monitor.unduck()
        except sr.WaitTimeoutError:
            log_info("Tiempo de espera agotado sin detectar voz")
            state_mgr.set_state(AssistantState.IDLE, "En espera")
            speaker_monitor.unduck()
        except sr.UnknownValueError:
            state_mgr.set_state(AssistantState.IDLE, "No te entendí bien, che")
            speaker_monitor.unduck()
        except Exception as e:
            log_error(f"Error capturando orden activa: {e}")
            state_mgr.set_state(AssistantState.IDLE, "Error de escucha")
            speaker_monitor.unduck()

    def _emit_volume(self, audio):
        try:
            raw_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
            rms = np.sqrt(np.mean(raw_data.astype(np.float64)**2))
            level = min(1.0, float(rms) / 5000.0)
            state_mgr.emit_audio_level(level)
        except Exception:
            pass

listener = AudioListener()
