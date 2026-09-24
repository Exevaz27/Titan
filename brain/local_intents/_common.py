"""Helpers compartidos de los handlers de intents locales."""
import random


def _strip_accents(s: str) -> str:
    """R-2: misma normalización que try_handle aplica a norm (solo áéíóú;
    la ñ se conserva, igual que en norm)."""
    return (s.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u"))


def _mip(norm: str, pattern: str) -> bool:
    """R-2: match insensible a tildes. Los patrones con tilde nunca
    matcheaban porque norm ya viene sin tildes."""
    return _strip_accents(pattern) in norm


# Anti-loro para respuestas fijas habladas: recuerda la última frase usada
# con cada clave y no la repite en la siguiente ocasión. (La misma idea vive
# en main.py para saludos/despedidas; acá para los intents locales.)
_last_speech_pick = {}

def _varied_choice(key, options):
    if len(options) > 1:
        last = _last_speech_pick.get(key)
        pool = [o for o in options if o != last] or options
    else:
        pool = options
    choice = random.choice(pool)
    _last_speech_pick[key] = choice
    return choice
