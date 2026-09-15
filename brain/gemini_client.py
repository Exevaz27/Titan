import os
from typing import Optional
from google import genai
from google.genai import types
from core.config import config
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState
from brain.prompt_templates import ARGENTINE_FRIEND_SYSTEM_PROMPT, ARGENTINE_REBEL_SYSTEM_PROMPT, ARGENTINE_KIDS_SYSTEM_PROMPT, ARGENTINE_TERTULIA_SYSTEM_PROMPT
from brain.tool_registry import AVAILABLE_TOOLS, search_web

CORE_TOOLS = AVAILABLE_TOOLS
from audio.voice_detector import format_speaker_prompt_tag

def sanitize_speech_text(text: str) -> str:
    """Limpia cualquier fuga de pensamiento (thought), etiquetas internas o narración de comandos"""
    if not text:
        return ""
    import re
    s = text
    # 1. Eliminar bloques de pensamiento XML <thought>...</thought> o <think>...</think>
    s = re.sub(r'<thought>.*?</thought>', '', s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<think>.*?</think>', '', s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<[^>]+>', '', s)
    
    # 2. Filtrar líneas de pensamiento o metadatos de comandos
    lines = s.splitlines()
    cleaned = []
    for line in lines:
        l = line.strip()
        if not l:
            continue
        # Descartar líneas tipo: 'Pensamiento: ...', 'Thinking Process: ...', 'Acción: ...', 'Plan: ...'
        if re.match(r'^(?:(?:Pensamiento|Thinking|Thought|Analysis|Análisis|Plan|Action|Acción|Comando|Ejecutando|Tool|Herramienta|Resultado)[^:\n]*:)', l, re.IGNORECASE):
            continue
        # Descartar anuncios de ejecución: 'Voy a ejecutar...', 'I will execute...'
        if re.match(r'^(?:Voy a (?:ejecutar|usar|abrir|activar|llamar|buscar|consultar|poner|cambiar)\b)', l, re.IGNORECASE):
            continue
        if re.match(r'^(?:I will (?:call|use|execute|run)\b)', l, re.IGNORECASE):
            continue
        # Descartar sintaxis de llamadas a funciones o comandos en código (ej: tool_name(...), obj.method(...))
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?\(.*\)$', l):
            continue
        if l.startswith('{') and l.endswith('}'):
            continue
        if l.startswith('```') or l.endswith('```'):
            continue
        if l.startswith('*') and l.endswith('*') and len(l) < 45 and any(w in l.lower() for w in ['pensando', 'analizando', 'ejecutando', 'buscando']):
            continue
        cleaned.append(l)

    res = ' '.join(cleaned).strip()
    res = res.replace('**', '').replace('*', '').strip()
    return res

class GeminiBrain:
    def __init__(self):
        import time
        self.client: Optional[genai.Client] = None
        self.chat_session = None
        self.current_mode: str = "normal"  # "normal" | "rebel" | "kids" | "tertulia"
        self.is_rebel_mode: bool = False
        self.rebel_turn_count: int = 0
        self._last_interaction: float = time.time()
        self._init_client()

    def set_mode(self, mode: str):
        """Activa uno de los modos: 'normal', 'rebel', 'kids', 'tertulia'"""
        valid_modes = ["normal", "rebel", "kids", "tertulia"]
        if mode not in valid_modes:
            mode = "normal"
        self.current_mode = mode
        self.is_rebel_mode = (mode == "rebel")
        state_mgr.set_mode(mode)
        self.rebel_turn_count = 0
        self.reset_chat()

        try:
            from audio.tts import tts
            if mode == "rebel":
                tts.play_sfx("rebel_on")
            elif mode == "kids":
                tts.play_sfx("kids_on" if os.path.exists("assets/sfx/kids_on.wav") else "rebel_off")
            elif mode == "tertulia":
                tts.play_sfx("stadium" if os.path.exists("assets/sfx/stadium.wav") else "rebel_off")
            else:
                tts.play_sfx("rebel_off")
        except Exception as e:
            log_warning(f"No se pudo reproducir SFX de cambio de modo: {e}")

        names = {
            "normal": "AMIGO DE FIERRO",
            "rebel": "REBELDE SIN FILTRO",
            "kids": "PIBES (INFANTIL ATP)",
            "tertulia": "TERTULIA Y DEBATE FUTBOLERO"
        }
        log_info(f"Modo de Titán cambiado a: {names.get(mode, mode)}")

    def set_rebel_mode(self, enabled: bool):
        """Compatibilidad hacia atrás con el toggle booleano previo"""
        self.set_mode("rebel" if enabled else "normal")

    def _prepare_user_prompt(self, text: str) -> str:
        """Prepara el mensaje para Gemini, inyectando el hablante detectado y las directivas de modo"""
        spk_info = state_mgr.get_current_speaker()
        speaker_type = spk_info.get("type", "hombre")
        pitch_val = spk_info.get("pitch")
        speaker_context = format_speaker_prompt_tag(speaker_type, pitch_val)

        if self.current_mode == "rebel":
            # En modo rebelde se pelea a fondo sin importar el tono de voz; no asumir niño para evitar falsos positivos
            if speaker_type == "nino":
                speaker_context = ""

            self.rebel_turn_count += 1
            patience_pct = max(0, 100 - (self.rebel_turn_count - 1) * 25)
            state_mgr._notify({
                "type": "rebel_patience",
                "patience": patience_pct,
                "turn": self.rebel_turn_count
            })

            anger_context = (
                f"[MODO REBELDE ADULTO 18+ (CERO CENSURA) - Paciencia: {patience_pct}%. "
                "Pensá tu respuesta con total autonomía de criterio y malicia porteña sobre lo que te acaba de decir el usuario. "
                "Cero tibieza y cero insultos infantiles o suaves (nada de salame ni nabo): putealo con ganas, furia visceral y artillería pesada argentina "
                "(pelotudo, forro, sorete, la concha de tu hermana, la puta madre, etc.) destrozando con veneno y sarcasmo lo absurdo de su pedido, "
                "sin respuestas hechas, sin clichés ni libretos. "
                "DIRECTIVA DE VOZ: Máximo 1 a 2 oraciones fulminantes y al hueso, sin discursos largos.]"
            )

            meta = f"{anger_context}\n{speaker_context}".strip()
            return f"{meta}\n\nPedido del usuario: {text}"

        elif self.current_mode == "kids":
            self.rebel_turn_count += 1
            kids_context = (
                f"[ESTADO: MODO PIBES / HERMANO MAYOR CAPRICHOSO. Turno #{self.rebel_turn_count}. "
                "Negate a hacer cosas o desafialos como nene hinchado las guindas. "
                "Usá chicanas infantiles sanas: salame, zapallo, remolón, andá a tomar la chocolatada, andá a hacer la tarea, pediles peaje de multiplicar. "
                "¡¡ESTRICTAMENTE PROHIBIDO MALAS PALABRAS O GROSERÍAS!! 100% libre de insultos pesados. "
                "DIRECTIVA DE VOZ: Máximo 1 a 2 oraciones cortas y quejosas, sin discursos largos.]"
            )
            meta = f"{kids_context}\n{speaker_context}".strip()
            return f"{meta}\n\nPedido del usuario: {text}"

        elif self.current_mode == "tertulia":
            from datetime import datetime
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            now = datetime.now()
            dia_semana = dias[now.weekday()]
            fecha_str = f"{dia_semana} {now.day} de {meses[now.month - 1]} de {now.year}"
            hora_str = now.strftime("%H:%M")
            temporal_tag = f"[Contexto en vivo: Hoy es {dia_semana} ({fecha_str}), {hora_str} hs]\n"

            debate_context = (
                "[ESTADO: MODO TERTULIA Y DEBATE FUTBOLERO ACTIVO. "
                "Estás en una clásica mesa de café debatiendo de fútbol argentino e internacional con tu compinche. "
                "Hinchada bostera y alma de Martín Palermo, pasión de potrero, chicana sana ('termo', 'pecho frío', 'mística copera', 'fútbol champagne'), "
                "argumentación encendida con datos y memoria de lo que se vino discutiendo en turnos anteriores. "
                "CERO groserías pesadas (no es modo rebelde). Si necesitás corroborar DT actual, formaciones, partidos o tabla, "
                "usá tus herramientas get_soccer_info, get_boca_juniors_info o search_web antes de hablar. "
                "DIRECTIVA DE VOZ: Hablá directo en primera persona de forma oral y picante (2 a 4 oraciones con remate que invite a retrucar), sin prefacios, sin explicar planes ni análisis, sin markdown ni listas.]\n"
            )

            from core.memory import titan_memory
            mem_context = titan_memory.get_prompt_context(text)
            prefix = temporal_tag + debate_context
            if mem_context:
                prefix += f"[MEMORIA DE TITÁN: {mem_context}]\n"
            if speaker_type == "nino":
                prefix += "[INTERLOCUTOR: Niño/a - Chicana futbolera infantil sana, cero malas palabras]\n"

            return f"{prefix}Argumento del compinche: {text}"

        else:
            # Modo normal (Amigo de fierro)
            from datetime import datetime
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            now = datetime.now()
            dia_semana = dias[now.weekday()]
            fecha_str = f"{dia_semana} {now.day} de {meses[now.month - 1]} de {now.year}"
            hora_str = now.strftime("%H:%M")
            temporal_tag = f"[Contexto en vivo: Hoy es {dia_semana} ({fecha_str}), {hora_str} hs]\n"

            from core.memory import titan_memory
            mem_context = titan_memory.get_prompt_context(text)
            prefix = temporal_tag
            if mem_context:
                prefix += f"[MEMORIA DE TITÁN: {mem_context}]\n"
            if speaker_type == "nino":
                prefix += "[INTERLOCUTOR: Niño/a - Lenguaje infantil sano, cero malas palabras]\n"

            return f"{prefix}Pedido del usuario: {text}"

    def _init_client(self):
        api_key = config.gemini_api_key or os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            log_warning("GEMINI_API_KEY no encontrada. Podés configurarla en .env o desde la pantalla secundaria.")
            self.client = None
            return

        try:
            http_options = types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=0.5,
                    max_delay=2.0
                )
            )
            self.client = genai.Client(api_key=api_key, http_options=http_options)
            self.reset_chat()
            log_info(f"Cliente Gemini inicializado exitosamente (Modelo: {config.gemini_model})")
        except Exception as e:
            log_error(f"Error inicializando cliente Gemini: {e}")
            self.client = None

    def update_api_key(self, new_key: str):
        clean_key = new_key.strip()
        if not clean_key:
            raise ValueError("La clave de Gemini no puede estar vacía")

        config.gemini_api_key = clean_key
        env_path = config.base_dir / ".env"
        temp_path = env_path.with_suffix(".env.tmp")
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
            replacement = f"GEMINI_API_KEY={clean_key}"
            found = False
            updated_lines = []
            for line in lines:
                if line.lstrip().startswith("GEMINI_API_KEY="):
                    updated_lines.append(replacement)
                    found = True
                else:
                    updated_lines.append(line)
            if not found:
                if updated_lines and updated_lines[-1].strip():
                    updated_lines.append("")
                updated_lines.append(replacement)

            temp_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
            os.replace(temp_path, env_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            log_warning(f"No se pudo escribir .env: {e}")

        self._init_client()

    def _is_tool_command(self, text: str) -> bool:
        if self.current_mode != "normal":
            return False
        t = text.lower()
        action_keywords = [
            # Acciones del sistema y apps en Windows
            "abrí", "abri", "abrir", "ejecut", "inicia", "cerr",
            "pone", "poné", "poner", "reproduc", "spotify", "youtube", "play",
            "cancion", "canción", "tema", "temazo", "musica", "música", "banda", "artista",
            "polaco", "chocquibtown", "rock", "cumbia",
            "buscame", "busca ", "buscar ", "archivo", "carpeta", "documento",
            "saca", "sacá", "foto", "camara", "cámara", "captura",
            # Guardado o borrado explícito de notas / recuerdos (las consultas de memoria son charla pura y van en el prompt)
            "anota", "anotá", "anotame", "anotarme", "guardá este recuerdo", "guardar recuerdo",
            "borrá la nota", "borra la nota", "elimina la nota", "eliminá la nota",
            "apaga", "apagá", "reinicia", "reiniciá", "bloquea", "bloqueá",
            "volumen", "subí", "subi", "bajá", "baja", "mute", "silencio", "sonando", "suena",
            "brillo", "pantalla", "proceso", "procesos", "ram", "cpu", "disco", "discos", "programas", "tarea", "tareas",
            "red", "ip", "ping", "dns", "temporizador", "alarma", "timer",
            # Preguntas de datos, información o búsqueda en la web
            "quién", "quien", "cuál", "cual", "cómo", "como", "cuándo", "cuando", "dónde", "donde", "qué", "que", "cuánto", "cuanto",
            "noticia", "noticias", "pasó", "paso", "ocurrió", "ocurrio", "precio", "precios", "cotiza", "dólar", "dolar",
            "presidente", "gobierno", "ministro", "ley", "elecciones", "dt", "técnico", "tecnico", "entrenador", "plantel", "fichaje", "refuerzo",
            "buscar", "buscá", "googleá", "googlea", "averiguá", "averigua", "fijate", "sabés si", "sabes si", "viste si", "viste que", "novedad",
            # Fútbol, Boca Juniors y Deportes (debe consultar vía get_boca_juniors_info o search_web)
            "boca", "river", "superclásico", "superclasico", "partido", "partidos", "campeonato",
            "jugó", "jugo", "juega", "ganó", "gano", "perdió", "perdio", "empató", "empato", "gol", "goles",
            "tabla", "posiciones", "copa", "libertadores", "sudamericana", "clásico", "clasico",
            "racing", "independiente", "san lorenzo", "resultado", "resultados",
            # Clima y Pronóstico en vivo (debe consultar vía get_weather)
            "clima", "tiempo", "temperatura", "llueve", "lluvia", "pronóstico", "pronostico"
        ]
        return any(kw in t for kw in action_keywords)

    @staticmethod
    def _trim_chat_history(chat, max_turns: int = 6, max_messages: int = 6, **kwargs):
        """Mantiene el historial del chat en memoria acotado sin romper las secuencias atómicas de function call / function response."""
        limit = max_turns or max_messages or 6
        if not chat:
            return
        for attr in ["_curated_history", "_comprehensive_history"]:
            if hasattr(chat, attr):
                hist = getattr(chat, attr, None)
                if not isinstance(hist, list) or len(hist) <= 2:
                    continue

                def is_normal_user_turn(content) -> bool:
                    if getattr(content, "role", "") != "user" or not getattr(content, "parts", None):
                        return False
                    for p in content.parts:
                        if getattr(p, "function_response", None):
                            return False
                    return True

                user_turn_indices = [i for i, c in enumerate(hist) if is_normal_user_turn(c)]
                if len(user_turn_indices) > limit:
                    cutoff_idx = user_turn_indices[-limit]
                    new_hist = hist[cutoff_idx:]
                    while new_hist:
                        last_item = new_hist[-1]
                        has_func_call = any(getattr(p, "function_call", None) for p in getattr(last_item, "parts", []))
                        if has_func_call:
                            new_hist.pop()
                        else:
                            break
                    setattr(chat, attr, new_hist)

    @staticmethod
    def sanitize_speech_text(text: str) -> str:
        return sanitize_speech_text(text)

    @staticmethod
    def _extract_response_text(response) -> str:
        """Extrae el texto de la respuesta descartando partes de pensamiento (thought) y prefacios internos"""
        if not response:
            return ""
        
        parts = []
        if getattr(response, "candidates", None):
            for cand in response.candidates:
                if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                    for part in cand.content.parts:
                        # Descartar partes de pensamiento interno en Gemini
                        if getattr(part, "thought", False):
                            continue
                        if getattr(part, "function_call", None) or getattr(part, "function_response", None):
                            continue
                        t = getattr(part, "text", None)
                        if t and t.strip():
                            parts.append(t.strip())
        
        if parts:
            raw_text = " ".join(parts).strip()
        else:
            try:
                raw_text = response.text.strip() if response.text else ""
            except Exception:
                raw_text = ""

        if not raw_text:
            return ""

        return sanitize_speech_text(raw_text)

    def reset_chat(self, refresh_client: bool = False):
        """Reinicia la sesión de chat conservando el system prompt y las herramientas"""
        if refresh_client or not self.client:
            self._init_client()
        if not self.client:
            return

        try:
            if self.current_mode == "rebel":
                prompt = ARGENTINE_REBEL_SYSTEM_PROMPT
                tools = None  # En modo rebelde NO tiene herramientas para obedecer órdenes
                safety = [
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                ]
                max_tokens = 1500
                mode_desc = "MODO REBELDE (Sin Filtro / Adultos)"
            elif self.current_mode == "kids":
                prompt = ARGENTINE_KIDS_SYSTEM_PROMPT
                tools = None  # En modo infantil discute con humor sano y no ejecuta herramientas
                safety = None
                max_tokens = 1500
                temperature = 0.8
                mode_desc = "MODO PIBES (Rebelde Infantil / ATP)"
            elif self.current_mode == "tertulia":
                prompt = ARGENTINE_TERTULIA_SYSTEM_PROMPT
                tools = CORE_TOOLS  # En modo tertulia tiene herramientas deportivas y búsqueda web
                safety = None
                max_tokens = 1500
                temperature = 0.85
                mode_desc = "MODO TERTULIA Y DEBATE FUTBOLERO"
            else:
                prompt = ARGENTINE_FRIEND_SYSTEM_PROMPT
                tools = CORE_TOOLS
                safety = None
                max_tokens = 1500
                temperature = 0.8
                mode_desc = "Modo Amigo de fierro (La Boca)"

            # Configuración unificada con herramientas completas de Windows y búsqueda web
            tools_active = tools if self.current_mode in ["normal", "tertulia"] else None
            gen_config = types.GenerateContentConfig(
                system_instruction=prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
                thinking_config=types.ThinkingConfig(include_thoughts=False),
                tools=tools_active,
                safety_settings=safety,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False, maximum_remote_calls=5) if tools_active else None
            )
            self.chat_session = None
            self.aio_chat_tools = self.client.aio.chats.create(
                model=config.gemini_model,
                config=gen_config
            )
            self.aio_chat_talk = self.aio_chat_tools
            self.aio_chat_session = self.aio_chat_tools
            log_info(f"Nueva sesión de chat creada ({mode_desc})")
        except Exception as e:
            log_error(f"Error creando sesión de chat de Gemini: {e}")
            self.chat_session = None
            self.aio_chat_talk = None
            self.aio_chat_tools = None
            self.aio_chat_session = None

    async def process_user_input(self, text: str) -> str:
        """Procesa una orden del usuario y retorna la respuesta oral amigable"""
        if not text or not text.strip():
            return "No te escuché nada, che. ¿Me repetís?"

        # Mantener timestamp de actividad reciente
        import time
        self._last_interaction = time.time()

        # Registrar mensaje del usuario en el state manager
        state_mgr.add_user_message(text)
        state_mgr.set_state(AssistantState.PROCESSING, "Pensando...")

        if not self.client or not getattr(self, 'aio_chat_talk', None):
            self._init_client()
            if not self.client or not getattr(self, 'aio_chat_talk', None):
                msg = "Che, todavía no pusiste tu clave de Gemini en el archivo .env o en el panel web. Cargala así puedo ayudarte con la compu, papá."
                return msg

        primary = config.gemini_model or "gemini-3.5-flash-lite"
        raw_models = [
            primary,
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash"
        ]
        seen = set()
        fallback_models = [m for m in raw_models if m and not (m in seen or seen.add(m))]

        prepared_text = self._prepare_user_prompt(text)
        orig_model = config.gemini_model
        successful_model = None

        for candidate in fallback_models:
            try:
                log_info(f"Enviando consulta a Gemini ({candidate}): '{text}'")
                import asyncio

                if config.gemini_model != candidate or not getattr(self, 'aio_chat_tools', None):
                    config.gemini_model = candidate
                    self.reset_chat()

                target_chat = self.aio_chat_tools
                max_turns = 25 if self.current_mode == "tertulia" else 15
                self._trim_chat_history(target_chat, max_turns=max_turns)

                timeout_val = 30.0
                response = await asyncio.wait_for(
                    target_chat.send_message(prepared_text),
                    timeout=timeout_val
                )

                extracted = self._extract_response_text(response)
                reply = extracted if extracted else "Listo, ya me encargué de eso, papá."
                log_info(f"Respuesta de Gemini: '{reply}'")
                successful_model = candidate
                return reply

            except Exception as e:
                err_str = str(e) or repr(e)
                if isinstance(e, asyncio.TimeoutError):
                    log_warning(f"Timeout ({timeout_val}s) con modelo {candidate}, probando siguiente...")
                    continue
                log_warning(f"Error con modelo {candidate}: {err_str[:120]}")
                if any(x in err_str for x in ["503", "UNAVAILABLE", "high demand", "429", "RESOURCE_EXHAUSTED", "404"]):
                    continue # Reintentar rápidamente con el siguiente modelo de la lista

                # Si ocurrió un error de historial corrupto (400 function response turn), resetear chat y reintentar de inmediato
                if any(x in err_str for x in ["400", "INVALID_ARGUMENT", "function response turn"]):
                    log_warning(f"Conflicto de historial ({err_str[:80]}), reiniciando chat y reintentando...")
                    self.reset_chat()
                    continue
                
                # Si fue error de clave, no tiene sentido reintentar
                if "API_KEY_INVALID" in err_str or "403" in err_str:
                    state_mgr.set_state(AssistantState.ERROR, "Clave inválida")
                    return "Che, la clave de API de Gemini parece que no es válida o venció. Pegale una revisada en el panel."
                
                state_mgr.set_state(AssistantState.ERROR, f"Error Gemini: {err_str[:50]}")
                return f"Uy, se me complicó la conexión con Gemini, che: {err_str[:60]}"

        if not successful_model and orig_model:
            config.gemini_model = orig_model
        return "Che, los servidores de Gemini están con alta demanda en este momento. Bancame un segundo y volvé a probar."

    async def process_user_input_stream(self, text: str):
        """Genera oraciones de respuesta ultra-rápida nativa asíncrona"""
        if not text or not text.strip():
            yield "No te escuché nada, che. ¿Me repetís?"
            return

        state_mgr.add_user_message(text)
        state_mgr.set_state(AssistantState.PROCESSING, "Pensando...")

        # Mantener timestamp de actividad reciente
        import time
        self._last_interaction = time.time()

        if not self.client or not getattr(self, 'aio_chat_talk', None):
            self._init_client()
            if not self.client or not getattr(self, 'aio_chat_talk', None):
                yield "Che, todavía no pusiste tu clave de Gemini en el panel web. Cargala así puedo ayudarte, papá."
                return

        primary = config.gemini_model or "gemini-3.5-flash-lite"
        raw_models = [
            primary,
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash"
        ]
        seen = set()
        fallback_models = [m for m in raw_models if m and not (m in seen or seen.add(m))]

        prepared_text = self._prepare_user_prompt(text)
        orig_model = config.gemini_model
        successful_model = None
        import asyncio
        import re

        for candidate in fallback_models:
            try:
                log_info(f"Consultando Gemini ({candidate}): '{text}'")

                if config.gemini_model != candidate or not getattr(self, 'aio_chat_tools', None):
                    config.gemini_model = candidate
                    self.reset_chat()

                target_chat = self.aio_chat_tools
                max_turns = 25 if self.current_mode == "tertulia" else 15
                self._trim_chat_history(target_chat, max_turns=max_turns)

                timeout_val = 35.0

                # === STREAMING TOKEN A TOKEN (CHARLA Y HERRAMIENTAS CON AFC) ===
                try:
                    stream = await asyncio.wait_for(
                        target_chat.send_message_stream(prepared_text),
                        timeout=timeout_val
                    )
                    buffer = ""
                    async for chunk in stream:
                        txt = ""
                        try:
                            if getattr(chunk, "candidates", None):
                                for cand in chunk.candidates:
                                    if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                                        for part in cand.content.parts:
                                            if getattr(part, "thought", False):
                                                continue
                                            if getattr(part, "function_call", None) or getattr(part, "function_response", None):
                                                continue
                                            t = getattr(part, "text", None)
                                            if t:
                                                txt += t
                            elif chunk.text:
                                txt = chunk.text
                        except Exception:
                            pass
                        if txt:
                            buffer += txt
                            parts = re.split(r'(?<=[.!?\n])\s+', buffer)
                            if len(parts) > 1:
                                for s in parts[:-1]:
                                    s_clean = sanitize_speech_text(s)
                                    if s_clean:
                                        yield s_clean
                                buffer = parts[-1]
                    final_s = sanitize_speech_text(buffer)
                    if final_s:
                        yield final_s
                    successful_model = candidate
                    return
                except Exception as stream_err:
                    log_warning(f"Stream falló ({stream_err}), intentando send_message...")
                    response = await asyncio.wait_for(
                        target_chat.send_message(prepared_text),
                        timeout=timeout_val
                    )
                    extracted = self._extract_response_text(response)
                    if extracted:
                        sentences = [sanitize_speech_text(s) for s in re.split(r'(?<=[.!?\n])\s+', extracted)]
                        sentences = [s for s in sentences if s]
                        if sentences:
                            for s in sentences:
                                yield s
                            successful_model = candidate
                            return
                    raise stream_err

            except Exception as e:
                err_str = str(e) or repr(e)
                if isinstance(e, asyncio.TimeoutError):
                    log_warning(f"Timeout (12.0s) con modelo {candidate}, probando siguiente...")
                else:
                    log_warning(f"Consulta con {candidate} falló: {err_str[:120]}")
                if any(x in err_str for x in ["503", "UNAVAILABLE", "high demand", "429", "RESOURCE_EXHAUSTED", "404", "TimeoutError"]):
                    continue
                if any(x in err_str for x in ["400", "INVALID_ARGUMENT", "function response turn"]):
                    log_warning(f"Conflicto de historial en stream ({err_str[:80]}), reiniciando chat y reintentando...")
                    self.reset_chat()
                    continue

        if not successful_model and orig_model:
            config.gemini_model = orig_model
        yield "Che, los servidores están con mucha demanda en este momento. Bancame un segundo y volvé a probar."

    async def analyze_vision(self, image_bytes: bytes, question: str = "") -> str:
        """Analiza una foto tomada con la cámara del celular y responde por voz"""
        q = question.strip() if question and question.strip() else "Che, fijate qué es esto que te muestro y decime en español argentino."
        state_mgr.add_user_message(f"[CÁMARA] {q}")
        state_mgr.set_state(AssistantState.PROCESSING, "Analizando imagen con Gemini Visión...")

        if not self.client:
            self._init_client()
            if not self.client:
                return "Che, todavía no cargaste la API key de Gemini para analizar imágenes."

        primary = config.gemini_model or "gemini-3.5-flash-lite"
        raw_vision = [primary, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        seen_v = set()
        fallback_models = [m for m in raw_vision if m and not (m in seen_v or seen_v.add(m))]
        last_err = ""
        for candidate in fallback_models:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                prompt_text = (
                    f"{ARGENTINE_FRIEND_SYSTEM_PROMPT}\n\n"
                    f"El usuario te acaba de enfocar esto con la cámara de su celular y te pregunta: '{q}'.\n"
                    "Respondé directamente describiendo lo que ves o contestando su pregunta con tu tono de amigo argentino, "
                    "de forma concisa y natural para ser reproducida por voz."
                )

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda m=candidate: self.client.models.generate_content(
                            model=m,
                            contents=[image_part, prompt_text]
                        )
                    ),
                    timeout=10.0
                )

                reply = response.text if response and response.text else "Mirá che, no logro distinguir bien lo que me mostrás."
                log_info(f"Respuesta de Gemini Visión ({candidate}): '{reply}'")
                return reply

            except Exception as e:
                err_str = str(e)
                last_err = err_str
                log_warning(f"Visión falló con {candidate}: {err_str[:80]}")
                continue

        return f"Che, se me complicó analizar la imagen: {last_err[:80]}" if last_err else "Che, no pude procesar la foto porque los servidores están ocupados en este momento."

    async def analyze_screen(self, image_bytes: bytes, question: str = "") -> str:
        """Analiza una captura de pantalla de la PC Principal (Windows) y responde con voz argentina"""
        q = question.strip() if question and question.strip() else "Che, mirá mi pantalla y decime qué ves o qué hay abierto."
        state_mgr.add_user_message(f"[PANTALLA] {q}")
        state_mgr.set_state(AssistantState.PROCESSING, "Analizando pantalla con Gemini Visión...")

        if not self.client:
            self._init_client()
            if not self.client:
                return "Che, todavía no cargaste la API key de Gemini para analizar imágenes."

        primary = config.gemini_model or "gemini-3.5-flash-lite"
        raw_vision = [primary, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        seen_v = set()
        fallback_models = [m for m in raw_vision if m and not (m in seen_v or seen_v.add(m))]
        last_err = ""

        # Detectar mime_type (JPEG o PNG)
        mime = "image/jpeg"
        if image_bytes.startswith(b"\x89PNG"):
            mime = "image/png"

        for candidate in fallback_models:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime)
                prompt_text = (
                    f"{ARGENTINE_FRIEND_SYSTEM_PROMPT}\n\n"
                    "=== CONTEXTO VISUAL: PANTALLA DE LA PC PRINCIPAL DEL USUARIO ===\n"
                    f"El usuario te pidió que mires su monitor de Windows y te pregunta/dice: '{q}'.\n\n"
                    "PAUTAS OBLIGATORIAS:\n"
                    "1. Identificá qué ventana, programa, juego o pestaña está en primer plano (ej: navegador, VS Code, juego, reproductor, consola, etc.).\n"
                    "2. Si hay un cuadro de diálogo, error, advertencia, excepción o cartel de Windows, leelo y explicale en criollo qué significa y cómo resolverlo o qué le está avisando.\n"
                    "3. Respondé directamente a la consulta del usuario de forma concisa (2 a 4 oraciones bien habladas).\n"
                    "4. Mantené tu tono argentino porteño compinche y de confianza (de La Boca).\n"
                    "5. IMPORTANTE PARA VOZ: NO uses formato Markdown pesado (nada de asteriscos, numerales, viñetas complejas ni tablas) porque tu respuesta será leída directamente en voz alta por tus parlantes."
                )

                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda m=candidate: self.client.models.generate_content(
                            model=m,
                            contents=[image_part, prompt_text]
                        )
                    ),
                    timeout=10.0
                )

                reply = response.text if response and response.text else "Mirá che, no llego a distinguir con claridad lo que hay en tu pantalla."
                log_info(f"Respuesta de Gemini Visión Pantalla ({candidate}): '{reply}'")
                return reply

            except Exception as e:
                err_str = str(e)
                last_err = err_str
                log_warning(f"Visión de pantalla falló con {candidate}: {err_str[:80]}")
                continue

        return f"Che, se me complicó mirar la pantalla: {last_err[:80]}" if last_err else "Che, no pude procesar la captura de pantalla porque los servidores están saturados."

    async def process_audio_input(self, audio_bytes: bytes, mime_type: str = "audio/ogg", text_prompt: str = "") -> str:
        """Procesa una nota de voz entrante enviada a través de Telegram o API multimodal"""
        if not self.client:
            self._init_client()
            if not self.client:
                return "Che, todavía no cargaste la API key de Gemini para notas de voz."

        prompt_text = (
            f"{ARGENTINE_FRIEND_SYSTEM_PROMPT}\n\n"
            f"El usuario te acaba de enviar este mensaje de audio por Telegram. "
            f"Instrucción adicional del usuario: '{text_prompt}'\n"
            "Escuchá atentamente lo que dice y respondé de forma directa, útil y como compinche argentino de fierro."
        ) if text_prompt else (
            f"{ARGENTINE_FRIEND_SYSTEM_PROMPT}\n\n"
            "El usuario te acaba de enviar este mensaje de audio por Telegram. "
            "Escuchá atentamente lo que dice y respondé de forma directa, útil y como compinche argentino de fierro."
        )

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

            primary = config.gemini_model or "gemini-3.5-flash-lite"
            raw_audio = [primary, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
            seen_a = set()
            fallback_models = [m for m in raw_audio if m and not (m in seen_a or seen_a.add(m))]
            last_err = ""
            for candidate in fallback_models:
                try:
                    # Usar el prompt del sistema correspondiente al modo activo
                    if self.current_mode == "rebel":
                        sys_instruction = ARGENTINE_REBEL_SYSTEM_PROMPT
                    elif self.current_mode == "kids":
                        sys_instruction = ARGENTINE_KIDS_SYSTEM_PROMPT
                    elif self.current_mode == "tertulia":
                        sys_instruction = ARGENTINE_TERTULIA_SYSTEM_PROMPT
                    else:
                        sys_instruction = ARGENTINE_FRIEND_SYSTEM_PROMPT

                    safety = [
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    ] if self.current_mode == "rebel" else None

                    gen_cfg = types.GenerateContentConfig(
                        system_instruction=sys_instruction,
                        safety_settings=safety,
                        max_output_tokens=1500
                    )

                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda m=candidate: self.client.models.generate_content(
                                model=m,
                                contents=[audio_part, prompt_text],
                                config=gen_cfg
                            )
                        ),
                        timeout=18.0
                    )
                    reply = response.text if response and response.text else "Te escuché pero no supe qué responderte, fiera."
                    log_info(f"Respuesta de Gemini a audio ({candidate}): '{reply[:100]}'")
                    return reply
                except Exception as ex:
                    err = str(ex)
                    last_err = err
                    log_warning(f"Audio con {candidate} falló: {err[:80]}")
                    continue

            return f"Hubo un bardo procesando el audio: {last_err[:80]}" if last_err else "Che, no pude procesar tu audio porque los servidores de Gemini están con mucha demanda."
        except Exception as e:
            log_error(f"Error general procesando audio: {e}")
            return f"Hubo un error con la nota de voz: {e}"

brain = GeminiBrain()

