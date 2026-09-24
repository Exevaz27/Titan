import asyncio
import io
import os
import re
import tempfile
import time
from typing import Optional
from pathlib import Path
import edge_tts
import pygame
import numpy as np
from core.config import config
from core.state_manager import state_mgr, AssistantState
from core.logger import log_info, log_error, log_warning

class TTSEngine:
    # B-8: si Edge-TTS se queda más de N segundos sin entregar audio se lo
    # considera colgado y se aborta la síntesis (antes quedaba esperando
    # para siempre y Titán quedaba mudo).
    _TTS_CHUNK_TIMEOUT_S = 25.0
    # B-17: cota real para recent_utterances. Antes solo se podaba dentro de
    # is_self_echo (que solo corre cuando el mic reconoce algo); en uso puro
    # por Telegram/HUD la lista crecía sin límite.
    _RECENT_UTTERANCE_WINDOW_S = 10.0
    _MAX_RECENT_UTTERANCES = 50

    def __init__(self):
        self.voice: str = config.tts_voice
        self._is_speaking: bool = False
        self._interrupted: bool = False
        self._current_sound = None
        self._current_channel = None
        self.current_text: str = ""
        self.recent_utterances: list = []  # Lista de tuplas (timestamp, texto)
        self.last_speech_time: float = 0.0
        self.on_speech_finished = None
        # B-8: dos speak() concurrentes se pisaban (_is_speaking, mixer,
        # avisos al HUD). Con el lock se serializan: el segundo espera.
        self._speak_lock = asyncio.Lock()
        self._init_mixer()

    def _remember_utterance(self, text: str):
        """B-17: guarda una frase en recent_utterances podando por tiempo
        (ventana de 10s) y por cantidad (tope de 50). Así la lista no crece
        sin límite cuando is_self_echo nunca corre (uso puro Telegram/HUD)."""
        import time
        now = time.time()
        self.recent_utterances.append((now, text))
        self.recent_utterances = [
            (t, u) for (t, u) in self.recent_utterances
            if now - t < self._RECENT_UTTERANCE_WINDOW_S
        ][-self._MAX_RECENT_UTTERANCES:]

    def is_self_echo(self, text: str) -> bool:
        """Verifica con alta precisión si un texto reconocido proviene del eco de los altavoces de Titán"""
        if not text:
            return False

        import time
        clean_text = "".join(c for c in text.lower() if c.isalnum() or c.isspace()).strip()
        if not clean_text:
            return False

        words_heard = [w for w in clean_text.split() if len(w) > 2]
        if not words_heard:
            return False

        now = time.time()
        # FIX 2026-09-15 (eco tardío): antes, si pasaban más de 1.5s desde que
        # Titán terminó de hablar, NADA se consideraba eco aunque el texto
        # coincidiera con algo que dijo. Pero Google STT tarda 1-3s en devolver
        # la transcripción: el eco de los parlantes llegaba tarde, pasaba el
        # filtro y se procesaba como orden del usuario (Titán hablándose a sí
        # mismo en loop, porque la ventana conversacional de 10s está abierta
        # justo después de cada TTS). Ahora hay dos niveles:
        #  - Coincidencia FUERTE (texto idéntico, o >=85% de las palabras
        #    escuchadas con >=3 palabras): vale durante toda la ventana de
        #    frases recientes (10s). Una transcripción tardía del propio Titán
        #    casi siempre cae acá.
        #  - Coincidencia difusa (>=60%): solo dentro de 1.5s de gracia, como
        #    antes. Más allá, el riesgo de confundir una pregunta real del
        #    usuario (que repite palabras del tema) es mayor que el beneficio.
        # Mantener frases de los últimos 10 segundos (las entradas guardan el
        # inicio de la frase y una frase larga puede durar varios segundos).
        self.recent_utterances = [(t, u) for (t, u) in self.recent_utterances if now - t < self._RECENT_UTTERANCE_WINDOW_S]

        in_grace = self._is_speaking or (now - getattr(self, "last_speech_time", 0) <= 1.5)

        for t_spoken, utterance in self.recent_utterances:
            clean_utt = "".join(c for c in utterance.lower() if c.isalnum() or c.isspace()).strip()
            if not clean_utt:
                continue

            overlap = sum(1 for w in words_heard if w in clean_utt)
            ratio = overlap / len(words_heard)

            # Fuerte: idéntico o casi todas las palabras escuchadas están en la frase
            if clean_text == clean_utt or (len(words_heard) >= 3 and ratio >= 0.85):
                return True

            # Difusa: como antes, solo en ventana de gracia
            if in_grace and ratio >= 0.60:
                return True

        return False

    def _init_mixer(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
        except Exception as e:
            log_warning(f"No se pudo inicializar pygame.mixer con audio por defecto: {e}")
            try:
                if os.environ.get("PULSE_SERVER") or os.path.exists("/run/user/1000/pulse/native"):
                    os.environ["SDL_AUDIODRIVER"] = "pulseaudio"
                else:
                    os.environ["SDL_AUDIODRIVER"] = "dummy"
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
                log_info(f"pygame.mixer inicializado con controlador {os.environ.get('SDL_AUDIODRIVER')}")
            except Exception as e2:
                try:
                    os.environ["SDL_AUDIODRIVER"] = "dummy"
                    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
                    log_info("pygame.mixer inicializado con controlador dummy")
                except Exception as e3:
                    log_error(f"No se pudo inicializar mixer dummy: {e3}")

    def stop(self):
        """Interrumpe la reproducción actual si está hablando"""
        self._interrupted = True
        self.current_text = ""
        try:
            if hasattr(self, "_current_channel") and self._current_channel:
                self._current_channel.stop()
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except Exception as e:
            log_error(f"Error deteniendo audio: {e}")
        self._is_speaking = False
        state_mgr.emit_speech_level(0.0)
        # Notificar al frontend que la boca debe detenerse
        state_mgr._notify({"type": "speech_stopped"})

    def _emit_speech_playing(self, text: str):
        """Emite señal de que el audio ACABA DE EMPEZAR a reproducirse (lip-sync trigger)"""
        state_mgr._notify({"type": "speech_playing", "text": text})

    def _emit_speech_stopped(self):
        """Emite señal de que el audio TERMINÓ (detener animación de boca)"""
        state_mgr.emit_speech_level(0.0)
        state_mgr._notify({"type": "speech_stopped"})

    @staticmethod
    def format_rebel_text(text: str) -> str:
        """Optimiza el texto rebelde para que suene coloquial y fluido manteniendo entonación argentina natural sin gritos metálicos en mayúsculas."""
        if not text:
            return text

        clean = re.sub(r'[*_#`~]', '', text).strip()
        clean = re.sub(r'!{2,}', '!', clean)
        clean = re.sub(r'\?{2,}', '?', clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean

    @staticmethod
    def format_normal_text(text: str) -> str:
        """Optimiza la entonación para modo normal: elimina markdown y normaliza puntuación manteniendo cadencia natural."""
        if not text:
            return text

        clean = re.sub(r'[*_#`~]', '', text).strip()
        clean = re.sub(r'!{2,}', '!', clean)
        clean = re.sub(r'\?{2,}', '?', clean)
        clean = re.sub(r'\s+', ' ', clean)
        return clean

    def _get_voice_params(self):
        """Devuelve configuración de prosodia según si está en modo normal o rebelde manteniendo tono humano y natural sin distorsiones."""
        if getattr(state_mgr, "is_rebel_mode", False):
            try:
                from brain.gemini_client import brain
                turn = getattr(brain, "rebel_turn_count", 0)
            except Exception:
                turn = 0

            # Mantiene pitch +0Hz para preservar los formantes humanos naturales de la voz argentina (evita sonido robótico/ardilla)
            if turn <= 0:
                return {
                    "voice": config.tts_voice,
                    "rate": "+8%",
                    "pitch": "+0Hz",
                    "volume": "+10%"
                }
            elif turn == 1:
                return {
                    "voice": config.tts_voice,
                    "rate": "+10%",
                    "pitch": "+0Hz",
                    "volume": "+15%"
                }
            elif turn == 2:
                return {
                    "voice": config.tts_voice,
                    "rate": "+12%",
                    "pitch": "+0Hz",
                    "volume": "+20%"
                }
            else:
                return {
                    "voice": config.tts_voice,
                    "rate": "+14%",
                    "pitch": "+0Hz",
                    "volume": "+20%"
                }

        return {
            "voice": config.tts_voice,
            "rate": config.tts_rate,
            "pitch": config.tts_pitch,
            "volume": config.tts_volume
        }

    def play_sfx(self, sfx_name: str):
        """Reproduce un efecto de sonido (rebel_on, rebel_off, slap) por parlantes"""
        sfx_path = config.base_dir / "audio" / "sfx" / f"{sfx_name}.wav"
        if sfx_path.exists():
            try:
                self._init_mixer()
                sound = pygame.mixer.Sound(str(sfx_path))
                sound.play()
            except Exception as e:
                log_warning(f"No se pudo reproducir SFX {sfx_name}: {e}")

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """Sintetiza texto a audio MP3 en memoria usando Edge-TTS (para Telegram o streaming)"""
        if not text or not text.strip():
            return b""
        try:
            from brain.gemini_client import sanitize_speech_text
            spoken_text = sanitize_speech_text(text).strip()
        except Exception:
            spoken_text = text.strip()
        if not spoken_text:
            return b""

        if getattr(state_mgr, "is_rebel_mode", False):
            spoken_text = self.format_rebel_text(spoken_text)
        else:
            spoken_text = self.format_normal_text(spoken_text)
        if not any(c.isalnum() for c in spoken_text):
            return b""
        v_params = self._get_voice_params()
        try:
            communicate = edge_tts.Communicate(
                text=spoken_text,
                voice=v_params["voice"],
                rate=v_params["rate"],
                pitch=v_params["pitch"],
                volume=v_params["volume"]
            )
            chunks = []
            # B-8: timeout por chunk en vez de `async for` pelado — si el
            # stream se cuelga (red trabada) se aborta en vez de esperar
            # para siempre.
            stream_iter = communicate.stream().__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        stream_iter.__anext__(), timeout=self._TTS_CHUNK_TIMEOUT_S
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    log_warning(
                        f"Edge-TTS colgado ({self._TTS_CHUNK_TIMEOUT_S}s sin audio) "
                        f"para '{spoken_text[:40]}...' — síntesis abortada"
                    )
                    return b""
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)
        except Exception as e:
            log_error(f"Error sintetizando audio en memoria: {e}")
            return b""

    async def _play_sound_with_level_tracking(self, bio: io.BytesIO, text: str):
        """Reproduce un Sound en memoria calculando y emitiendo RMS exacto cada ~30ms para lip-sync con detección de pausas."""
        if not pygame.mixer.get_init():
            self._emit_speech_playing(text)
            words = len(text.split())
            simulated_duration = max(1.2, words * 0.32)
            steps = int(simulated_duration / 0.04)
            for _ in range(steps):
                if self._interrupted:
                    break
                state_mgr.emit_speech_level(0.6)
                await asyncio.sleep(0.04)
            self._emit_speech_stopped()
            return

        try:
            snd = pygame.mixer.Sound(bio)
            samples = pygame.sndarray.samples(snd)
            duration = snd.get_length()
            if duration > 0 and len(samples) > 0:
                sr = len(samples) / duration
            else:
                sr = 44100.0

            self._current_sound = snd
            self._current_channel = snd.play()
            self._emit_speech_playing(text)

            chunk_size = max(1, int(sr * 0.035))  # ~35ms slice
            start_time = time.time()
            total_samples = len(samples)

            while self._current_channel and self._current_channel.get_busy() and not self._interrupted:
                elapsed = time.time() - start_time
                pos = int(elapsed * sr)
                if pos < total_samples:
                    chunk = samples[pos : pos + chunk_size]
                    if len(chunk) > 0:
                        if chunk.ndim > 1:
                            chunk = chunk[:, 0]
                        rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
                        level = min(1.0, float(rms) / 8000.0)
                        # Umbral de silencio para pausas naturales (comas, puntos, respiraciones)
                        if level < 0.04:
                            level = 0.0
                        state_mgr.emit_speech_level(level)
                await asyncio.sleep(0.03)

            if self._interrupted and self._current_channel:
                self._current_channel.stop()

        except Exception as e:
            log_error(f"Error reproduciendo audio con lip-sync: {e}")
        finally:
            state_mgr.emit_speech_level(0.0)
            self._current_sound = None
            self._current_channel = None

    async def speak(self, text: str, auto_listen: bool = True):
        """Genera audio con Edge-TTS en memoria RAM y lo reproduce sin tocar disco.

        B-8: serializado con _speak_lock — dos speak() concurrentes se pisaban
        (_is_speaking, mixer, avisos al HUD). El que llega segundo espera su turno.
        """
        if not text or not text.strip():
            return

        try:
            from brain.gemini_client import sanitize_speech_text
            clean_text = sanitize_speech_text(text).strip()
        except Exception:
            clean_text = text.strip()

        if not clean_text:
            return

        async with self._speak_lock:
            await self._speak_impl(clean_text, text, auto_listen)

    async def _speak_impl(self, clean_text: str, original_text: str, auto_listen: bool = True):
        self._interrupted = False
        self._is_speaking = True
        self.current_text = clean_text
        import time
        self._remember_utterance(clean_text)

        raw_bytes = await self.synthesize_to_bytes(clean_text)
        if not raw_bytes or self._interrupted:
            self._is_speaking = False
            return

        try:
            self._init_mixer()
            bio = io.BytesIO(raw_bytes)
            state_mgr.set_state(AssistantState.SPEAKING, "Hablando...")
            state_mgr.add_assistant_message(clean_text)

            import base64
            b64_audio = base64.b64encode(raw_bytes).decode("ascii")
            state_mgr._notify({
                "type": "play_audio",
                "audio_base64": b64_audio,
                "text": original_text
            })

            await self._play_sound_with_level_tracking(bio, original_text)

        except Exception as e:
            log_error(f"Error en síntesis/reproducción TTS en memoria: {e}")
            state_mgr.set_state(AssistantState.ERROR, f"Fallo TTS: {e}")
        finally:
            self._is_speaking = False
            self.last_speech_time = time.time()
            self.current_text = ""
            self._emit_speech_stopped()

            if not self._interrupted and auto_listen and self.on_speech_finished:
                self.on_speech_finished()
            elif state_mgr.current_state == AssistantState.SPEAKING:
                state_mgr.set_state(AssistantState.IDLE, "En espera de activación")

    def play_instant_filler(self, filler_name: Optional[str] = None):
        """Conectores instantáneos desactivados a pedido del usuario (Opción B: 100% voz directa contextual)"""
        return
        import random
        if not filler_name:
            fillers = ["de_una", "a_ver", "joya", "ahi_va", "mira"]
            filler_name = random.choice(fillers)

        filler_path = config.base_dir / "audio" / "fillers" / f"{filler_name}.mp3"
        if filler_path.exists():
            try:
                self._init_mixer()
                sound = pygame.mixer.Sound(str(filler_path))
                sound.set_volume(0.85)
                sound.play()
                self._emit_speech_playing(filler_name.replace("_", " "))
            except Exception as e:
                log_warning(f"No se pudo reproducir filler: {e}")
            try:
                with open(filler_path, "rb") as f:
                    filler_bytes = f.read()
                import base64
                b64_audio = base64.b64encode(filler_bytes).decode("ascii")
                state_mgr._notify({
                    "type": "play_audio",
                    "audio_base64": b64_audio,
                    "text": filler_name.replace("_", " ")
                })
            except Exception:
                pass

    async def speak_stream(self, sentence_gen, auto_listen: bool = True):
        """Sintetiza y reproduce oraciones en streaming con precarga paralela 100% en memoria RAM (latencia mínima)

        B-8: serializado con _speak_lock, igual que speak().
        """
        async with self._speak_lock:
            await self._speak_stream_impl(sentence_gen, auto_listen)

    async def _speak_stream_impl(self, sentence_gen, auto_listen: bool = True):
        self._interrupted = False
        self._is_speaking = True

        # Cola con slots de prefetch en memoria RAM
        queue = asyncio.Queue(maxsize=3)
        synth_done = asyncio.Event()

        async def synthesizer():
            try:
                from brain.gemini_client import sanitize_speech_text
            except Exception:
                sanitize_speech_text = lambda x: x.strip()

            try:
                async for sentence in sentence_gen:
                    if self._interrupted:
                        break
                    s = sanitize_speech_text(sentence).strip()
                    if not s:
                        continue
                    try:
                        raw_bytes = await self.synthesize_to_bytes(s)
                        if raw_bytes and not self._interrupted:
                            bio = io.BytesIO(raw_bytes)
                            await queue.put((s, bio, raw_bytes))
                    except Exception as ex:
                        log_warning(f"Error sintetizando oración '{s}': {ex}")
            finally:
                synth_done.set()

        synth_task = asyncio.create_task(synthesizer())

        try:
            self._init_mixer()

            while not self._interrupted:
                if queue.empty() and synth_done.is_set():
                    break
                try:
                    s, bio, raw_bytes = await asyncio.wait_for(queue.get(), timeout=0.15)
                except asyncio.TimeoutError:
                    if synth_done.is_set() and queue.empty():
                        break
                    continue

                if self._interrupted:
                    break

                self.current_text = s
                self._remember_utterance(s)
                state_mgr.add_assistant_message(s)

                try:
                    state_mgr.set_state(AssistantState.SPEAKING, "Hablando...")
                    import base64
                    b64_audio = base64.b64encode(raw_bytes).decode("ascii")
                    state_mgr._notify({
                        "type": "play_audio",
                        "audio_base64": b64_audio,
                        "text": s
                    })
                    await self._play_sound_with_level_tracking(bio, s)
                except Exception as p_err:
                    log_warning(f"Error reproduciendo audio en memoria: {p_err}")
                finally:
                    if not self._interrupted and queue.empty() and synth_done.is_set():
                        self._emit_speech_stopped()
                    queue.task_done()

        finally:
            synth_task.cancel()
            self._is_speaking = False
            self.last_speech_time = time.time()
            self.current_text = ""
            self._emit_speech_stopped()
            if not self._interrupted and auto_listen and self.on_speech_finished:
                self.on_speech_finished()
            elif state_mgr.current_state == AssistantState.SPEAKING:
                state_mgr.set_state(AssistantState.IDLE, "En espera de activación")

# Instancia global
tts = TTSEngine()


