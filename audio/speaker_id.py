"""Identificación del hablante por huella de voz (2026-09-17, multi-voz 2026-09-18).

Cómo funciona:
- El micrófono de la DDR3 captura el audio. El embedding (vector de voz)
  se calcula en el satélite Windows (rápido, Ryzen) vía RPC `speaker_embed`.
- Acá se compara contra TODAS las huellas guardadas (similitud coseno) y
  se elige la mejor si supera el umbral.
- Sin huellas o sin satélite, la identidad es "desconocido" y todo sigue
  funcionando como antes.

Cada persona tiene su huella en audio/voiceprints/<nombre>.json
(local, NO se commitea). Ej: exequiel.json, oriana.json.
"""

import asyncio
import base64
import json
import math
import os
import re
import time
import unicodedata

from core.logger import log_info, log_warning

VOICEPRINT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voiceprints")
OWNER_NAME = "exequiel"  # nombre interno del dueño
# Umbral de similitud coseno para identificar. Los d-vectors en
# condiciones parejas (mismo mic/ambiente) suelen dar >0.75 para la misma
# persona y <0.5 para distintas; 0.65 deja margen sin falsos positivos.
SIMILARITY_THRESHOLD = 0.65
MIN_PHRASE_SECONDS = 1.5
IDENTITY_TTL_S = 15.0

# Circuit breaker del satélite (2026-09-19): timestamp del último fallo de
# speaker_embed. Mientras esté dentro de la ventana, fetch_embedding falla
# rápido sin bloquear el comando esperando un satélite que flaphea.
_last_embed_failure: float = 0.0
_EMBED_BREAKER_S = 25.0

ENROLL_PHRASES = [
    "Titán, ¿cómo está el clima hoy en Buenos Aires?",
    "Poné música de rock nacional y subí el volumen.",
    "Che, ¿me leés los mensajes que me llegaron?",
    "Apagá la luz del comedor cuando termines.",
    "Contame un chiste corto para alegrar la noche.",
    "¿A qué hora juega Boca el fin de semana?",
    "Bajá la persiana y prendé el ventilador.",
    "Qué bueno que ya funciona el reconocimiento de voz.",
]

# --- Estado del registro conversacional ("registrá mi voz" / "registrá la voz de X") ---
_enrollment = {"active": False, "idx": 0, "embeddings": [], "name": OWNER_NAME, "display": "Exequiel"}
_last_identity = {"identity": "desconocido", "score": 0.0, "time": 0.0}


def _voiceprint_path(name: str) -> str:
    return os.path.join(VOICEPRINT_DIR, f"{_safe_name(name)}.json")


def _safe_name(name: str) -> str:
    """Nombre interno apto para archivo: minúsculas, sin tildes ni espacios."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-z0-9]", "", n.lower())
    return n or "persona"


def list_voiceprints():
    """Nombres internos con huella guardada, ordenados."""
    try:
        if not os.path.isdir(VOICEPRINT_DIR):
            return []
        return sorted(f[:-5] for f in os.listdir(VOICEPRINT_DIR) if f.endswith(".json"))
    except Exception:
        return []


def _load_data(name: str):
    try:
        with open(_voiceprint_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def display_name(name: str) -> str:
    """Nombre lindo para mostrar ('oriana' -> 'Oriana')."""
    data = _load_data(name)
    if data and data.get("display"):
        return str(data["display"])
    return _safe_name(name).capitalize()


def has_voiceprint(name: str = OWNER_NAME) -> bool:
    return os.path.exists(_voiceprint_path(name))


def load_voiceprint(name: str = OWNER_NAME):
    """Devuelve el vector promedio guardado, o None."""
    data = _load_data(name)
    if not data:
        return None
    try:
        emb = data.get("embedding")
        if emb:
            return [float(x) for x in emb]
    except Exception as e:
        log_warning(f"[Huella] no pude leer la huella de '{name}': {e}")
    return None


def save_voiceprint(embeddings, name: str = OWNER_NAME, display: str = None) -> bool:
    """Promedia los embeddings (ya normalizados) y guarda la huella."""
    name = _safe_name(name)
    vecs = [[float(x) for x in e] for e in embeddings if e]
    if not vecs:
        return False
    dim = len(vecs[0])
    avg = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in avg)) or 1.0
    avg = [x / norm for x in avg]
    os.makedirs(VOICEPRINT_DIR, exist_ok=True)
    payload = {
        "name": name,
        "display": display or name.capitalize(),
        "embedding": avg,
        "samples": len(vecs),
        "dim": dim,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    tmp = _voiceprint_path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, _voiceprint_path(name))
    log_info(f"[Huella] huella de '{name}' guardada ({len(vecs)} muestras).")
    return True


def cosine(a, b) -> float:
    denom = (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))) or 1.0
    return sum(x * y for x, y in zip(a, b)) / denom


def fetch_embedding(audio_bytes: bytes, sample_rate: int, loop, timeout: float = 3.0):
    """Pide el embedding al satélite Windows. Devuelve lista de floats o None.

    Circuit breaker (2026-09-19): si el satélite falló hace poco está
    flappeando (conectado pero sin responder) y no tiene sentido bloquear
    cada comando esperando el timeout: se devuelve None al instante
    ("desconocido", fail-closed) hasta que vuelva a responder bien.
    """
    global _last_embed_failure
    from server.websocket_hub import ws_hub
    if not ws_hub.has_windows_satellite():
        return None
    if time.time() - _last_embed_failure < _EMBED_BREAKER_S:
        return None  # satélite flappeando: fail fast, sin frenar el comando
    payload = base64.b64encode(audio_bytes).decode("ascii")
    fut = asyncio.run_coroutine_threadsafe(
        ws_hub.call_remote(
            "speaker_embed",
            {"audio_b64": payload, "sample_rate": int(sample_rate)},
            timeout=timeout,
        ),
        loop,
    )
    try:
        res = fut.result(timeout=timeout + 1.0)
    except Exception as e:
        _last_embed_failure = time.time()
        log_warning(f"[Huella] el satélite no respondió a tiempo: {e}")
        return None
    if isinstance(res, dict) and res.get("status") == "success" and res.get("embedding"):
        _last_embed_failure = 0.0  # el satélite volvió a responder: se cierra el breaker
        return [float(x) for x in res["embedding"]]
    if isinstance(res, dict) and res.get("status") == "timeout":
        _last_embed_failure = time.time()  # conectado pero sin responder: flapping
    log_warning(f"[Huella] respuesta inesperada del satélite: {res}")
    return None


def match_embedding(emb) -> tuple:
    """Compara contra TODAS las huellas; devuelve (nombre, score).

    nombre es el interno ('exequiel', 'oriana') o 'desconocido'.
    """
    global _last_identity
    best, best_score = "desconocido", 0.0
    if emb:
        for name in list_voiceprints():
            vp = load_voiceprint(name)
            if not vp:
                continue
            s = cosine(emb, vp)
            if s > best_score:
                best, best_score = name, s
    identity = best if best_score >= SIMILARITY_THRESHOLD else "desconocido"
    _last_identity = {"identity": identity, "score": best_score, "time": time.time()}
    log_info(f"[Huella] hablante: {identity} (score {best_score:.2f})")
    return identity, best_score


def identify(audio_bytes: bytes, sample_rate: int, loop):
    """Devuelve (nombre, score): 'exequiel'/'oriana'/... o 'desconocido'."""
    if not list_voiceprints():
        return "desconocido", 0.0
    emb = fetch_embedding(audio_bytes, sample_rate, loop)
    return match_embedding(emb)


def current_identity():
    """Identidad vigente (con TTL); para el prompt del cerebro."""
    if time.time() - _last_identity.get("time", 0) > IDENTITY_TTL_S:
        return "desconocido", 0.0
    return _last_identity["identity"], _last_identity["score"]


def identity_prompt_tag() -> str:
    """Fragmento para el system prompt. Vacío si no hay huellas."""
    if not list_voiceprints():
        return ""
    identity, _ = current_identity()
    if identity == "desconocido":
        return " Quien habla no es ninguna persona registrada por huella de voz."
    if identity == OWNER_NAME:
        return " La persona que habla es Exequiel, el dueño (identificado por su huella de voz)."
    return f" La persona que habla es {display_name(identity)} (identificada por su huella de voz)."


# ---------------------------------------------------------------------------
# Registro conversacional: "Titán, registrá mi voz"
# ---------------------------------------------------------------------------

def enrollment_active() -> bool:
    return bool(_enrollment.get("active"))


def _satellite_present() -> bool:
    try:
        from server.websocket_hub import ws_hub
        return bool(ws_hub.has_windows_satellite())
    except Exception:
        return False


def start_enrollment(name: str = OWNER_NAME, display: str = None) -> str:
    """Inicia el registro de `name`. Devuelve el texto de apertura para hablar."""
    name = _safe_name(name)
    display = display or name.capitalize()
    if not _satellite_present():
        return ("No detecto la PC Windows conectada. Abrí el satélite de Titán "
                "en la PC y probá de nuevo.")
    _enrollment.update({"active": True, "idx": 0, "embeddings": [],
                        "name": name, "display": display})
    n = len(ENROLL_PHRASES)
    quien = "tu voz" if name == OWNER_NAME else f"la voz de {display}"
    return (f"Dale, vamos a registrar {quien}. Buscá un momento de silencio y "
            f"que hable a distancia normal, con tono de todos los días. Te voy a "
            f"pedir {n} frases. La primera: {ENROLL_PHRASES[0]}")


def cancel_enrollment() -> str:
    _enrollment.update({"active": False, "idx": 0, "embeddings": [],
                        "name": OWNER_NAME, "display": "Exequiel"})
    return "Listo, cancelé el registro de voz. Cuando quieras lo retomamos."


def delete_voiceprint(name: str = OWNER_NAME) -> bool:
    """Borra la huella guardada. Devuelve True si existía."""
    name = _safe_name(name)
    path = _voiceprint_path(name)
    if os.path.exists(path):
        os.remove(path)
        log_info(f"[Huella] huella de '{name}' borrada.")
        return True
    return False


def warmup_satellite(loop) -> None:
    """Precalienta el modelo en el satélite con 1s de silencio (fire-and-forget).

    La primera inferencia carga torch + el modelo y puede tardar varios
    segundos; hacerla al arrancar el registro evita que la primera frase
    parezca "colgada".
    """
    try:
        silence = b"\x00" * 16000 * 2  # 1s PCM 16kHz 16-bit
        fetch_embedding(silence, 16000, loop, timeout=60.0)
        log_info("[Huella] modelo del satélite precalentado.")
    except Exception as e:
        log_warning(f"[Huella] no se pudo precalentar el modelo: {e}")


def handle_enrollment_audio(audio_bytes: bytes, sample_rate: int, loop):
    """Procesa el audio de una frase del registro. Devuelve el próximo texto a hablar."""
    # 2026-09-18 — Anti-eco por TIMING: mientras Titán habla, el mic capta
    # su propia voz por los parlantes. El filtro por texto (is_self_echo)
    # no alcanza: su ventana es de 10s desde que EMPIEZA a hablar y la
    # apertura del registro dura ~13s hablada, así que el eco tardío se
    # aceptaba como frase del usuario ("Bien, 1 de 8" sin que nadie hablara)
    # y los fragmentos cortos pedían "repetí la frase" en loop.
    try:
        import time
        from audio.tts import tts as _tts
        if getattr(_tts, "_is_speaking", False) or \
           (time.time() - getattr(_tts, "last_speech_time", 0) < 1.5):
            return None
    except Exception:
        pass
    idx = _enrollment.get("idx", 0)
    n = len(ENROLL_PHRASES)
    # El usuario puede cancelar por voz: el audio del registro no pasa por
    # el STT normal, así que se transcribe acá livianamente.
    try:
        import speech_recognition as sr
        audio = sr.AudioData(audio_bytes, int(sample_rate), 2)
        said = sr.Recognizer().recognize_google(audio, language="es-AR") or ""
        low = said.lower()
        try:
            from audio.tts import tts
            if tts.is_self_echo(said):
                return None  # eco de la propia voz de Titán: ignorar en silencio
        except Exception:
            pass
        if any(k in low for k in ["cancel", "olvid", "deja", "dejalo", "termina", "basta"]):
            return cancel_enrollment()
    except Exception:
        pass
    seconds = len(audio_bytes) / (2 * max(1, int(sample_rate)))
    if seconds < MIN_PHRASE_SECONDS:
        return f"No te escuché bien, repetí la frase {idx + 1}: {ENROLL_PHRASES[idx]}"
    emb = fetch_embedding(audio_bytes, sample_rate, loop, timeout=30.0)
    if not emb:
        _enrollment.update({"active": False, "idx": 0, "embeddings": []})
        return ("No pude comunicarme con la PC Windows para analizar tu voz. "
                "Fijate que el satélite esté abierto y decime 'registrá mi voz' "
                "para arrancar de nuevo.")
    _enrollment["embeddings"].append(emb)
    done = len(_enrollment["embeddings"])
    log_info(f"[Huella] frase {done}/{n} capturada.")
    if done >= n:
        name = _enrollment.get("name", OWNER_NAME)
        display = _enrollment.get("display", name.capitalize())
        ok = save_voiceprint(_enrollment["embeddings"], name=name, display=display)
        _enrollment.update({"active": False, "idx": 0, "embeddings": [],
                            "name": OWNER_NAME, "display": "Exequiel"})
        if ok:
            quien = "tu voz" if name == OWNER_NAME else f"la voz de {display}"
            return (f"Listo, ya sé reconocer {quien}. Quedó guardada la huella, "
                    f"de ahora en más sé cuándo habla {display}.")
        return "Hubo un problema guardando la huella, probá de nuevo en un rato."
    _enrollment["idx"] = done
    return f"Bien. La {done + 1}: {ENROLL_PHRASES[done]}"
