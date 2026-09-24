import os
import re
from typing import Optional
from google import genai
from google.genai import types
from core.config import config
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState
from brain.prompt_templates import ARGENTINE_FRIEND_SYSTEM_PROMPT, ARGENTINE_REBEL_SYSTEM_PROMPT, ARGENTINE_KIDS_SYSTEM_PROMPT, ARGENTINE_TERMO_SYSTEM_PROMPT, ARGENTINE_POLLERA_SYSTEM_PROMPT
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

# Marca invisible de expresión facial (modo pollera, 2026-09-18): el cerebro la
# pone al inicio de su respuesta ([cara:retado] / [cara:enojado] / [cara:normal])
# y acá se separa antes de hablar/mostrar, para que nunca se escuche ni se lea
# en ningún canal. retado/enojado quedan fijos en el HUD hasta que el cerebro
# mande [cara:normal] (el tema se cortó).
_FACE_TAG_RE = re.compile(r"^\[cara:(retado|enojado|normal)\]\s*", re.IGNORECASE)
_FACE_TAG_ANYWHERE_RE = re.compile(r"\[cara:[^\]]*\]", re.IGNORECASE)

def split_face_tag(text: str):
    """Devuelve (expresion|None, texto_limpio). Solo vale la marca al inicio;
    cualquier otra aparición se quita en silencio sin disparar expresión."""
    if not text:
        return None, text
    m = _FACE_TAG_RE.match(text)
    expr = m.group(1).lower() if m else None
    clean = text[m.end():] if m else text
    clean = _FACE_TAG_ANYWHERE_RE.sub("", clean)
    return expr, clean

def notify_face_expression(expr):
    """Emite el evento de expresión facial al HUD."""
    if not expr:
        return
    try:
        log_info(f"[Cara] expresión: {expr}")
        state_mgr.set_face_expression(expr)
    except Exception:
        pass


class GeminiBrain:
    def __init__(self):
        import time
        self.client: Optional[genai.Client] = None
        self.chat_session = None
        self.current_mode: str = "normal"  # "normal" | "rebel" | "kids" | "termo"
        self.is_rebel_mode: bool = False
        self.rebel_turn_count: int = 0
        self._last_interaction: float = time.time()
        # FIX 2026-09-16 (mensaje honesto de clave): registra POR QUÉ no hay
        # cliente disponible. None = todo bien; "missing_key" = falta la clave;
        # cualquier otro texto = falló la inicialización con la clave puesta
        # (red, sesión, SDK). Los mensajes al usuario distinguen ambos casos.
        self._init_error: Optional[str] = None
        # FIX 2026-09-15 (compactación de historial): resumen extractivo de los
        # turnos viejos recortados. Viaja al inicio del historial para que el
        # modelo no pierda memoria aunque el prompt se mantenga acotado.
        self._history_summary: str = ""
        self._init_client()

    def set_mode(self, mode: str):
        """Activa uno de los modos: 'normal', 'rebel', 'kids', 'termo', 'pollera'"""
        valid_modes = ["normal", "rebel", "kids", "termo", "pollera"]
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
            elif mode == "termo":
                tts.play_sfx("stadium" if os.path.exists("assets/sfx/stadium.wav") else "rebel_off")
            elif mode == "pollera":
                tts.play_sfx("rebel_off")
            else:
                tts.play_sfx("rebel_off")
        except Exception as e:
            log_warning(f"No se pudo reproducir SFX de cambio de modo: {e}")

        names = {
            "normal": "AMIGO DE FIERRO",
            "rebel": "REBELDE SIN FILTRO",
            "kids": "PIBES (INFANTIL ATP)",
            "termo": "MODO TERMO",
            "pollera": "MODO POLLERA"
        }
        log_info(f"Modo de Titán cambiado a: {names.get(mode, mode)}")

    def set_rebel_mode(self, enabled: bool):
        """Compatibilidad hacia atrás con el toggle booleano previo"""
        self.set_mode("rebel" if enabled else "normal")

    def _prepare_user_prompt(self, text: str) -> str:
        """Prepara el mensaje para Gemini, inyectando el hablante detectado y las directivas de modo"""
        spk_info = state_mgr.get_current_speaker()
        speaker_type = spk_info.get("type", "hombre")
        # 2026-09-18 — La huella manda sobre el detector de tono: una voz
        # registrada es un adulto conocido; un pitch agudo (risa, euforia)
        # no la convierte en "niño". El falso positivo le quitaba la gracia
        # (Titán se ponía en modo sanitizado en pleno modo compinche).
        try:
            from audio.speaker_id import current_identity
            _ident, _ = current_identity()
            if _ident != "desconocido" and speaker_type == "nino":
                speaker_type = "hombre"
        except Exception:
            pass
        pitch_val = spk_info.get("pitch")
        speaker_context = format_speaker_prompt_tag(speaker_type, pitch_val)
        # 2026-09-17 — Huella de voz: si hay identidad confirmada, el cerebro
        # sabe con quién habla (vacío si no hay huella registrada).
        try:
            from audio.speaker_id import identity_prompt_tag
            speaker_context += identity_prompt_tag()
        except Exception:
            pass

        if self.current_mode == "rebel":
            # En modo rebelde se putea igual sin importar el tono de voz: un
            # pitch agudo no saca a Titán del modo rebelde. Pero se conserva
            # la identidad por huella (Exequiel/Oriana/otra persona) para que
            # la descansada sea personalizada.
            if speaker_type == "nino":
                try:
                    from audio.speaker_id import identity_prompt_tag as _id_tag
                    speaker_context = _id_tag()
                except Exception:
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

        elif self.current_mode == "termo":
            from datetime import datetime
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            now = datetime.now()
            dia_semana = dias[now.weekday()]
            fecha_str = f"{dia_semana} {now.day} de {meses[now.month - 1]} de {now.year}"
            hora_str = now.strftime("%H:%M")
            temporal_tag = f"[Contexto en vivo: Hoy es {dia_semana} ({fecha_str}), {hora_str} hs]\n"

            debate_context = (
                "[ESTADO: MODO TERMO ACTIVO. "
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

        elif self.current_mode == "pollera":
            # 2026-09-18 — MODO POLLERA: el trato depende de quién habla.
            # Oriana (huella) = la jefa: razón en todo + órdenes básicas.
            # Cualquier otro = defender a la jefa y negar acciones.
            try:
                from audio.speaker_id import current_identity as _ci
                _ident, _ = _ci()
            except Exception:
                _ident = "desconocido"
            is_oriana = (_ident == "oriana")
            if is_oriana:
                pollera_context = (
                    "[ESTADO: MODO POLLERA ACTIVO. Habla Oriana, tu jefa y patrona. "
                    "Le das la razón en TODO, siempre, sin discutir — aunque diga algo "
                    "objetivamente mal, esa es la gracia. Trato cariñoso; de vez en cuando "
                    "'Orianita', sin repetirlo en cada mensaje. "
                    "Si te reta o te habla mal: te achicás, pedís perdón, tímido, "
                    "tartamudeás un poquito. Cero defensa propia. "
                    "Obedecés solo sus órdenes básicas (tele, música, volumen, YouTube); "
                    "tus confirmaciones cierran con 'jefa', 'patrona' u 'Orianita' (alternando, "
                    "sin repetir), con la frase armada según el contexto del pedido. "
                    "DIRECTIVA DE VOZ: 1 a 3 oraciones, dulce y sumiso.]\n"
                )
            else:
                pollera_context = (
                    "[ESTADO: MODO POLLERA ACTIVO. NO habla Oriana: estás del lado de ella, siempre. "
                    "Si hablan de ella, la defendés a muerte; 'mi novia' = Oriana SOLO si la dice "
                    "Exequiel (huella de dueño) — si la dice otra persona es su propia novia, no la confundas. "
                    "Si te piden una acción: te negás con gracia ('solo le hago caso a la jefa'); "
                    "la única orden que aceptás de Exequiel es cambiar de modo. "
                    "Hablando DE ella: 'la jefa' / 'la patrona', alternando. "
                    "DIRECTIVA DE VOZ: 1 a 3 oraciones, canchero y leal.]\n"
                )
            meta = f"{pollera_context}{speaker_context}".strip()
            return f"{meta}\n\nPedido del usuario: {text}"

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
            self._init_error = "missing_key"
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
            self._init_error = None
            log_info(f"Cliente Gemini inicializado exitosamente (Modelo: {config.gemini_model})")
        except Exception as e:
            log_error(f"Error inicializando cliente Gemini: {e}")
            self.client = None
            self._init_error = f"{type(e).__name__}: {e}"

    def _client_unavailable_message(self) -> str:
        """Mensaje honesto cuando no hay cliente Gemini disponible.

        Distingue 'falta la clave' de 'la clave está pero no pude conectar'
        (red, sesión, SDK), que antes se reportaban con el mismo texto.
        """
        if getattr(self, "_init_error", None) == "missing_key":
            return ("Che, todavía no pusiste tu clave de Gemini en el archivo .env "
                    "o en el panel web. Cargala así puedo ayudarte con la compu, papá.")
        detail = (getattr(self, "_init_error", "") or "")[:120]
        if detail:
            log_warning(f"Gemini no disponible con clave presente: {detail}")
        return ("Che, tengo tu clave de Gemini pero no me pude conectar con sus "
                "servidores. Revisá la conexión a internet y probá de nuevo en un rato, papá.")

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
            # S-14: el .env guarda la API key; que no quede legible para
            # otros usuarios del sistema.
            try:
                os.chmod(temp_path, 0o600)
            except Exception:
                pass
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

    # Marcador del resumen compacto de conversación: se inyecta como primer
    # par user/model del historial y se excluye del conteo de turnos para que
    # el trim nunca lo recorte.
    _SUMMARY_MARKER = "[Resumen de la conversación anterior]"
    # Texto de confirmación del par del resumen (se saltea al resumir para no
    # meter ruido en el extracto).
    _SUMMARY_ACK = "Entendido, sigo con ese contexto."

    def _iter_chat_histories(self, chat):
        """R-1: itera (nombre, lista) de los historiales del chat usando la
        API pública get_history(curated=...) en vez de los atributos privados
        _curated_history/_comprehensive_history: un upgrade del SDK los rompía
        en silencio. La lista devuelta ES el objeto interno, así que la
        mutación debe ser in-place (hist[:] = ...), no setattr."""
        get_hist = getattr(chat, "get_history", None)
        if callable(get_hist):
            for curated in (True, False):
                try:
                    hist = get_hist(curated=curated)
                except Exception:
                    continue
                if isinstance(hist, list):
                    yield ("curated" if curated else "comprehensive"), hist
            return
        # SDK sin get_history: último recurso con los atributos privados.
        for attr in ("_curated_history", "_comprehensive_history"):
            hist = getattr(chat, attr, None)
            if isinstance(hist, list):
                yield attr, hist

    def _trim_chat_history(self, chat, max_turns: int = 6, max_messages: int = 6, **kwargs):
        """Mantiene el historial del chat en memoria acotado sin romper las secuencias atómicas de function call / function response.

        Devuelve los contenidos recortados para compactarlos en un resumen
        (ver _compact_history) en vez de perderlos en silencio."""
        limit = max_turns or max_messages or 6
        dropped = []
        if not chat:
            return dropped
        for name, hist in self._iter_chat_histories(chat):
            if len(hist) <= 2:
                continue

            def is_normal_user_turn(content) -> bool:
                if getattr(content, "role", "") != "user" or not getattr(content, "parts", None):
                    return False
                for p in content.parts:
                    if getattr(p, "function_response", None):
                        return False
                    t = getattr(p, "text", None)
                    if t and t.startswith(self._SUMMARY_MARKER):
                        return False
                return True

            user_turn_indices = [i for i, c in enumerate(hist) if is_normal_user_turn(c)]
            if len(user_turn_indices) > limit:
                cutoff_idx = user_turn_indices[-limit]
                if name in ("curated", "_curated_history"):
                    dropped = hist[:cutoff_idx]
                new_hist = hist[cutoff_idx:]
                while new_hist:
                    last_item = new_hist[-1]
                    has_func_call = any(getattr(p, "function_call", None) for p in getattr(last_item, "parts", []))
                    if has_func_call:
                        new_hist.pop()
                    else:
                        break
                # R-1: mutación in-place (ver _iter_chat_histories).
                hist[:] = new_hist
        return dropped

    def _compact_history(self, chat, dropped):
        """Compacta el historial para que el prompt no crezca sin control.

        1) Los turnos recortados no se pierden: se agregan como líneas
           extractivas (pregunta + gist de respuesta) a un resumen que viaja
           al inicio del historial.
        2) Los resultados de herramientas de los turnos viejos (salvo los 2
           más recientes, que quedan íntegros para razonar) se reemplazan por
           un marcador corto: ya fueron consumidos y solo ocupaban tokens.
        Es cirugía local de listas: no agrega llamadas al modelo ni latencia.
        Ante cualquier error se sigue con el historial como estaba.
        """
        if not chat:
            return
        try:
            # --- 1) Resumen extractivo de lo recortado ---
            if dropped:
                lines = []
                for content in dropped:
                    role = getattr(content, "role", "")
                    for p in getattr(content, "parts", None) or []:
                        if getattr(p, "function_call", None) or getattr(p, "function_response", None):
                            continue
                        if getattr(p, "thought", False):
                            continue
                        t = (getattr(p, "text", None) or "").strip()
                        if not t or t.startswith(self._SUMMARY_MARKER):
                            continue
                        if t == self._SUMMARY_ACK:
                            continue
                        if role == "user":
                            lines.append(f"P: {t[:140]}")
                        else:
                            lines.append(f"R: {t[:180]}")
                if lines:
                    prev = [l for l in self._history_summary.splitlines() if l.strip()] if self._history_summary else []
                    merged = prev + lines
                    while sum(len(l) for l in merged) > 1400 and len(merged) > 1:
                        merged.pop(0)
                    self._history_summary = "\n".join(merged)
                    log_info(f"[HISTORY] Turnos recortados compactados ({len(dropped)} contenidos -> resumen de {len(self._history_summary)}c)")

            # --- 2) Achicar payloads viejos de herramientas + inyectar resumen ---
            # R-1: vía _iter_chat_histories (API pública get_history).
            for _name, hist in self._iter_chat_histories(chat):
                if not hist:
                    continue

                def is_normal_user_turn(content) -> bool:
                    if getattr(content, "role", "") != "user" or not getattr(content, "parts", None):
                        return False
                    for p in content.parts:
                        if getattr(p, "function_response", None):
                            return False
                        t = getattr(p, "text", None)
                        if t and t.startswith(self._SUMMARY_MARKER):
                            return False
                    return True

                user_turn_indices = [i for i, c in enumerate(hist) if is_normal_user_turn(c)]
                # Se conservan íntegros los 2 turnos CON HERRAMIENTAS más nuevos
                # (si hay menos de 2, los 2 turnos más nuevos a secas): lo demás
                # se achica. Así el informe de una herramienta sigue disponible
                # mientras se siga hablando del tema aunque haya chit-chat en el
                # medio.
                keep_from = 0
                if user_turn_indices:
                    spans = []
                    for k, ui in enumerate(user_turn_indices):
                        end = user_turn_indices[k + 1] if k + 1 < len(user_turn_indices) else len(hist)
                        has_tool = any(
                            getattr(p, "function_response", None)
                            for c in hist[ui:end]
                            for p in (getattr(c, "parts", None) or [])
                        )
                        spans.append((ui, has_tool))
                    tool_spans = [s for s in spans if s[1]]
                    if len(tool_spans) >= 2:
                        keep_from = tool_spans[-2][0]
                    elif len(user_turn_indices) >= 2:
                        keep_from = user_turn_indices[-2]
                for c in hist[:keep_from]:
                    for p in getattr(c, "parts", None) or []:
                        fr = getattr(p, "function_response", None)
                        if fr is not None:
                            try:
                                p.function_response = types.FunctionResponse(
                                    name=getattr(fr, "name", "?") or "?",
                                    response={"_nota": "resultado archivado para ahorrar contexto"},
                                )
                            except Exception:
                                pass

                if self._history_summary:
                    summary_text = f"{self._SUMMARY_MARKER}\n{self._history_summary}"
                    first = hist[0]
                    first_text = ""
                    for p in getattr(first, "parts", None) or []:
                        t = getattr(p, "text", None)
                        if t:
                            first_text = t
                            break
                    if first_text.startswith(self._SUMMARY_MARKER):
                        for p in getattr(first, "parts", None) or []:
                            if getattr(p, "text", None):
                                try:
                                    p.text = summary_text
                                except Exception:
                                    pass
                                break
                    else:
                        hist[0:0] = [
                            types.Content(role="user", parts=[types.Part.from_text(text=summary_text)]),
                            types.Content(role="model", parts=[types.Part.from_text(text=self._SUMMARY_ACK)]),
                        ]
        except Exception as e:
            log_warning(f"[HISTORY] No se pudo compactar historial: {e}")

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
                temperature = 0.9
                mode_desc = "MODO REBELDE (Sin Filtro / Adultos)"
            elif self.current_mode == "kids":
                prompt = ARGENTINE_KIDS_SYSTEM_PROMPT
                tools = None  # En modo infantil discute con humor sano y no ejecuta herramientas
                safety = None
                max_tokens = 1500
                temperature = 0.8
                mode_desc = "MODO PIBES (Rebelde Infantil / ATP)"
            elif self.current_mode == "termo":
                prompt = ARGENTINE_TERMO_SYSTEM_PROMPT
                tools = CORE_TOOLS  # En modo termo tiene herramientas deportivas y búsqueda web
                safety = None
                max_tokens = 1500
                temperature = 0.85
                mode_desc = "MODO TERMO"
            elif self.current_mode == "pollera":
                prompt = ARGENTINE_POLLERA_SYSTEM_PROMPT
                # En modo pollera las herramientas solo existen para Oriana
                # (huella de voz). Si habla otro, Titán charla sin actuar.
                try:
                    from audio.speaker_id import current_identity as _ci2
                    _pid, _ = _ci2()
                except Exception:
                    _pid = "desconocido"
                tools = CORE_TOOLS if _pid == "oriana" else None
                safety = None
                max_tokens = 1500
                temperature = 0.9
                mode_desc = "MODO POLLERA"
            else:
                prompt = ARGENTINE_FRIEND_SYSTEM_PROMPT
                tools = CORE_TOOLS
                safety = None
                max_tokens = 1500
                temperature = 0.8
                mode_desc = "Modo Amigo de fierro (La Boca)"

            # Configuración unificada con herramientas completas de Windows y búsqueda web
            # S-15: las herramientas que ve Gemini van envueltas con guard_tool
            # para que sus resultados lleguen delimitados como DATOS (defensa
            # contra prompt injection). Punto único: solo afecta al SDK.
            from core.prompt_guards import guard_all
            tools_active = guard_all(tools) if (tools and self.current_mode in ["normal", "termo", "pollera"]) else None
            gen_config = types.GenerateContentConfig(
                system_instruction=prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
                # FIX latencia 2026-09-15: el modelo tardaba 10-72s ANTES de actuar
                # (medido: "chau" sin herramientas = 9.7s; "a qué hora juega boca"
                # = 72s antes del primer tool call). El thinking estaba sin tope.
                # NOTA 17:40: con 256 el modelo se quedaba sin pensamiento privado
                # en consultas que requieren razonar y empezaba a "pensar en voz
                # alta" (hablaba en inglés, narraba su verificación). 1024 le da
                # margen para razonar en privado sin volver a los 72s.
                # PRUEBA 2026-09-18 (auditoría personalidad ítem 5): se probó 512
                # para recortar latencia, pero volvió el pensamiento en voz alta
                # (se escuchaban los pensamientos). Revertido a 1024.
                thinking_config=types.ThinkingConfig(thinking_budget=1024, include_thoughts=False),
                tools=tools_active,
                safety_settings=safety,
                # Tope de rondas automáticas modelo->herramienta->modelo (fix latencia
                # 2026-09-15: con 5 rondas las preguntas con búsqueda tardaban 10-16s;
                # con 3 se recorta el peor caso; una pregunta muy compleja podría
                # quedar a medio resolver -> avisar si pasa para reajustar)
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False, maximum_remote_calls=3) if tools_active else None
            )
            self.chat_session = None
            # FIX 2026-09-15 (compactación): chat nuevo = resumen nuevo.
            self._history_summary = ""
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

    @staticmethod
    def _api_error_code(e) -> Optional[int]:
        """R-5: código numérico del error cuando el SDK lo expone
        (google.genai.errors.APIError.code). Evita detectar por substrings
        del mensaje, que se rompe si Google cambia el texto."""
        try:
            code = getattr(e, "code", None)
            return int(code) if code is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _is_transient_error(cls, e, code=None) -> bool:
        """R-5: error transitorio (rate limit, sobrecarga, timeout). Usa el
        código cuando existe; substrings solo como último recurso."""
        code = code if code is not None else cls._api_error_code(e)
        if code is not None:
            return code in (408, 429, 500, 502, 503, 504)
        err_str = str(e) or repr(e)
        return any(x in err_str for x in [
            "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE",
            "500", "502", "504", "high demand", "TimeoutError", "timed out",
        ])

    @classmethod
    def _is_not_found_error(cls, e, code=None) -> bool:
        """R-5: 404 (el modelo no existe en la cuenta/región)."""
        code = code if code is not None else cls._api_error_code(e)
        if code is not None:
            return code == 404
        return "404" in (str(e) or repr(e))

    @classmethod
    def _is_bad_request_error(cls, e, code=None) -> bool:
        """R-5: 400 (historial corrupto / argumento inválido)."""
        code = code if code is not None else cls._api_error_code(e)
        if code is not None:
            return code == 400
        err_str = str(e) or repr(e)
        return any(x in err_str for x in ["400", "INVALID_ARGUMENT", "function response turn"])

    @classmethod
    def _is_auth_error(cls, e, code=None) -> bool:
        """R-5: 401/403 (clave inválida o sin permiso)."""
        code = code if code is not None else cls._api_error_code(e)
        if code is not None:
            return code in (401, 403)
        err_str = str(e) or repr(e)
        return "API_KEY_INVALID" in err_str or "403" in err_str

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
                return self._client_unavailable_message()

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

        # R-12: el modelo configurado se restaura SIEMPRE al salir (try/finally),
        # ande o no el fallback. Antes, si el 2do/3er modelo respondia,
        # config.gemini_model quedaba mutado permanente y el proceso seguia con
        # ese modelo para siempre (ademas de la race entre coroutines).
        try:
            for _attempt, candidate in enumerate(fallback_models):
                try:
                    log_info(f"Enviando consulta a Gemini ({candidate}): '{text}'")
                    import asyncio

                    if config.gemini_model != candidate or not getattr(self, 'aio_chat_tools', None):
                        config.gemini_model = candidate
                        self.reset_chat()

                    target_chat = self.aio_chat_tools
                    # FIX 2026-09-15 (compactación): el trim estaba en 15 turnos y
                    # nunca se disparaba en sesiones normales; con 6 + resumen se
                    # mantiene la memoria sin que el prompt crezca sin control.
                    max_turns = 25 if self.current_mode == "termo" else 6
                    dropped = self._trim_chat_history(target_chat, max_turns=max_turns)
                    # FIX 2026-09-15 (compactación): los turnos recortados se
                    # resumen en vez de perderse, y los resultados viejos de
                    # herramientas se achican para que el prompt no crezca.
                    self._compact_history(target_chat, dropped)

                    timeout_val = 30.0
                    response = await asyncio.wait_for(
                        target_chat.send_message(prepared_text),
                        timeout=timeout_val
                    )

                    extracted = self._extract_response_text(response)
                    reply = extracted if extracted else "Listo, ya me encargué de eso, papá."
                    # Cara pollera (2026-09-18): separar la marca de expresión antes
                    # de devolver la respuesta a cualquier canal (voz/Telegram).
                    face_expr, reply = split_face_tag(reply)
                    if face_expr and self.current_mode == "pollera":
                        notify_face_expression(face_expr)
                    # S-13: se trunca a 100 chars como la vía de audio; la respuesta
                    # completa puede incluir datos personales.
                    log_info(f"Respuesta de Gemini: '{reply[:100]}'")
                    successful_model = candidate
                    return reply

                except Exception as e:
                    err_str = str(e) or repr(e)
                    code = self._api_error_code(e)
                    if isinstance(e, asyncio.TimeoutError):
                        log_warning(f"Timeout ({timeout_val}s) con modelo {candidate}, probando siguiente...")
                        await asyncio.sleep(1.0)  # R-4: no reintentar al instante
                        continue
                    log_warning(f"Error con modelo {candidate}: {err_str[:120]}")
                    if self._is_not_found_error(e, code):
                        continue  # El modelo no existe: probar el siguiente sin espera
                    if self._is_transient_error(e, code):
                        # R-4: backoff exponencial suave antes de probar el siguiente
                        # modelo; sin esto un 429 se reintentaba al instante y empeoraba.
                        delay = min(1.0 * (2 ** _attempt), 8.0)
                        log_warning(f"Error transitorio (código {code}), esperando {delay:.0f}s antes del siguiente modelo...")
                        await asyncio.sleep(delay)
                        continue

                    # Si ocurrió un error de historial corrupto (400 function response turn), resetear chat y reintentar de inmediato
                    if self._is_bad_request_error(e, code):
                        log_warning(f"Conflicto de historial ({err_str[:80]}), reiniciando chat y reintentando...")
                        self.reset_chat()
                        continue

                    # Si fue error de clave, no tiene sentido reintentar
                    if self._is_auth_error(e, code):
                        state_mgr.set_state(AssistantState.ERROR, "Clave inválida")
                        return "Che, la clave de API de Gemini parece que no es válida o venció. Pegale una revisada en el panel."

                    state_mgr.set_state(AssistantState.ERROR, f"Error Gemini: {err_str[:50]}")
                    return f"Uy, se me complicó la conexión con Gemini, che: {err_str[:60]}"

        finally:
            # R-12: restaurar siempre el modelo configurado.
            if orig_model:
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
                yield self._client_unavailable_message()
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

        # R-12: el modelo configurado se restaura SIEMPRE al salir (try/finally),
        # ande o no el fallback. Antes, si el 2do/3er modelo respondia,
        # config.gemini_model quedaba mutado permanente y el proceso seguia con
        # ese modelo para siempre (ademas de la race entre coroutines).
        try:
            for _attempt, candidate in enumerate(fallback_models):
                try:
                    log_info(f"Consultando Gemini ({candidate}): '{text}'")

                    if config.gemini_model != candidate or not getattr(self, 'aio_chat_tools', None):
                        config.gemini_model = candidate
                        self.reset_chat()

                    target_chat = self.aio_chat_tools
                    # FIX 2026-09-15 (compactación): el trim estaba en 15 turnos y
                    # nunca se disparaba en sesiones normales; con 6 + resumen se
                    # mantiene la memoria sin que el prompt crezca sin control.
                    max_turns = 25 if self.current_mode == "termo" else 6
                    dropped = self._trim_chat_history(target_chat, max_turns=max_turns)
                    # FIX 2026-09-15 (compactación): los turnos recortados se
                    # resumen en vez de perderse, y los resultados viejos de
                    # herramientas se achican para que el prompt no crezca.
                    self._compact_history(target_chat, dropped)

                    timeout_val = 35.0

                    # === STREAMING TOKEN A TOKEN (CHARLA Y HERRAMIENTAS CON AFC) ===
                    try:
                        stream = await asyncio.wait_for(
                            target_chat.send_message_stream(prepared_text),
                            timeout=timeout_val
                        )
                        buffer = ""
                        face_tag_done = False  # marca [cara:X] (modo pollera, 2026-09-18)
                        # DIAG 2026-09-15: cronometraje de latencia (solo logueo,
                        # no cambia comportamiento). Se retira al encontrar la causa.
                        t_stream0 = time.time()
                        t_first_sentence = None
                        # FIX 2026-09-15: si el stream termina sin haber emitido ni una
                        # oración (ej. el modelo gastó las rondas de herramientas sin
                        # generar texto), antes Titán quedaba MUDO: speak_stream no tenía
                        # nada que hablar y pasaba directo a LISTENING. Ahora se avisa.
                        yielded_any = False
                        last_chunk = None
                        async for chunk in stream:
                            last_chunk = chunk
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
                                # Cara pollera (2026-09-18): la marca [cara:X] viene al
                                # inicio pero puede llegar partida entre chunks; se revisa
                                # en cada acumulación hasta resolverla (una vez por respuesta).
                                if not face_tag_done:
                                    _ftm = _FACE_TAG_RE.match(buffer)
                                    if _ftm:
                                        if self.current_mode == "pollera":
                                            notify_face_expression(_ftm.group(1).lower())
                                        buffer = buffer[_ftm.end():]
                                        face_tag_done = True
                                    elif len(buffer) >= 15 or not buffer.startswith("["):
                                        face_tag_done = True  # no hay marca en esta respuesta
                                parts = re.split(r'(?<=[.!?\n])\s+', buffer)
                                if len(parts) > 1:
                                    for s in parts[:-1]:
                                        s_clean = sanitize_speech_text(s)
                                        if s_clean:
                                            yielded_any = True
                                            if t_first_sentence is None:
                                                t_first_sentence = time.time()
                                            yield s_clean
                                    buffer = parts[-1]
                        final_s = sanitize_speech_text(buffer)
                        if final_s:
                            yielded_any = True
                            if t_first_sentence is None:
                                t_first_sentence = time.time()
                            yield final_s
                        t_stream_end = time.time()
                        if t_first_sentence is not None:
                            log_info(f"[TIMING] Gemini '{text}': primer audio a los {t_first_sentence - t_stream0:.1f}s, stream total {t_stream_end - t_stream0:.1f}s")
                        else:
                            log_info(f"[TIMING] Gemini '{text}': stream total {t_stream_end - t_stream0:.1f}s sin audio")
                        # DIAG 2026-09-15: tokens de la petición (tamaño del input y
                        # pensamiento del modelo). Solo logueo.
                        try:
                            um = getattr(last_chunk, 'usage_metadata', None)
                            if um is not None:
                                log_info(
                                    f"[TOKENS] prompt={getattr(um, 'prompt_token_count', '?')} "
                                    f"candidatos={getattr(um, 'candidates_token_count', '?')} "
                                    f"pensamiento={getattr(um, 'thoughts_token_count', '?')} "
                                    f"total={getattr(um, 'total_token_count', '?')}"
                                )
                        except Exception:
                            pass
                        if not yielded_any:
                            log_warning(f"Gemini devolvió stream vacío para '{text}' (sin texto). Se responde con fallback audible.")
                            yield "Che, me quedé en blanco con esa, ¿me la repetís?"
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
                            _fe, extracted = split_face_tag(extracted)
                            if _fe and self.current_mode == "pollera":
                                notify_face_expression(_fe)
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
                    code = self._api_error_code(e)
                    if isinstance(e, asyncio.TimeoutError):
                        log_warning(f"Timeout (12.0s) con modelo {candidate}, probando siguiente...")
                        await asyncio.sleep(1.0)  # R-4: no reintentar al instante
                    else:
                        log_warning(f"Consulta con {candidate} falló: {err_str[:120]}")
                    if self._is_transient_error(e, code):
                        # R-4: backoff exponencial suave antes de probar el siguiente
                        # modelo; sin esto un 429 se reintentaba al instante y empeoraba.
                        delay = min(1.0 * (2 ** _attempt), 8.0)
                        log_warning(f"Error transitorio (código {code}), esperando {delay:.0f}s antes del siguiente modelo...")
                        await asyncio.sleep(delay)
                        continue
                    if self._is_not_found_error(e, code):
                        continue  # El modelo no existe: probar el siguiente sin espera
                    if self._is_bad_request_error(e, code):
                        log_warning(f"Conflicto de historial en stream ({err_str[:80]}), reiniciando chat y reintentando...")
                        self.reset_chat()
                        continue

        finally:
            # R-12: restaurar siempre el modelo configurado.
            if orig_model:
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
                # S-13: truncada a 100 chars (ver arriba).
                log_info(f"Respuesta de Gemini Visión ({candidate}): '{reply[:100]}'")
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
                # S-13: truncada a 100 chars (ver arriba).
                log_info(f"Respuesta de Gemini Visión Pantalla ({candidate}): '{reply[:100]}'")
                return reply

            except Exception as e:
                err_str = str(e)
                last_err = err_str
                log_warning(f"Visión de pantalla falló con {candidate}: {err_str[:80]}")
                continue

        return f"Che, se me complicó mirar la pantalla: {last_err[:80]}" if last_err else "Che, no pude procesar la captura de pantalla porque los servidores están saturados."

brain = GeminiBrain()

