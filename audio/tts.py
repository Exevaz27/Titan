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
        self._init_mixer()

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
        # Si Titán NO está hablando y ya pasaron más de 1.5s desde que terminó,
        # NO es eco bajo ninguna circunstancia. El usuario está conversando normalmente.
        if not self._is_speaking and (now - getattr(self, "last_speech_time", 0) > 1.5):
            return False

        # Mantener solo frases de los últimos 5 segundos
        self.recent_utterances = [(t, u) for (t, u) in self.recent_utterances if now - t < 5.0]

        for t_spoken, utterance in self.recent_utterances:
            clean_utt = "".join(c for c in utterance.lower() if c.isalnum() or c.isspace()).strip()
            if not clean_utt:
                continue

            # Coincidencia exacta o contenida
            if clean_text in clean_utt or clean_utt in clean_text:
                return True

            # Coincidencia de palabras clave mientras suena el audio
            overlap = sum(1 for w in words_heard if w in clean_utt)
            if (overlap / len(words_heard)) >= 0.60:
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
            async for chunk in communicate.stream():
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
        """Genera audio con Edge-TTS en memoria RAM y lo reproduce sin tocar disco"""
        if not text or not text.strip():
            return

        try:
            from brain.gemini_client import sanitize_speech_text
            clean_text = sanitize_speech_text(text).strip()
        except Exception:
            clean_text = text.strip()

        if not clean_text:
            return

        self._interrupted = False
        self._is_speaking = True
        self.current_text = clean_text
        import time
        self.recent_utterances.append((time.time(), clean_text))

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
                "text": text
            })

            await self._play_sound_with_level_tracking(bio, text)

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
        """Sintetiza y reproduce oraciones en streaming con precarga paralela 100% en memoria RAM (latencia mínima)"""
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
                self.recent_utterances.append((time.time(), s))
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


