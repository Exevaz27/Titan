"""Variantes rotativas de respuestas para acciones locales.

Titán no es un loro: cada acción local (tele, etc.) tiene varias
formulaciones en su voz y pick() elige una al azar en cada ejecución.
Los placeholders {nombre} se reemplazan con los datos de la acción.

Para no repetir la misma frase dos veces seguidas, se evita devolver
dos veces consecutivas la misma variante de una clave.
"""

import random
from typing import Dict, List

_VARIANTS: Dict[str, List[str]] = {
    # --- Televisor BGH ---
    "tv.turn_on": [
        "Listo fiera, tele prendida.",
        "Ahí te prendí la tele, papá.",
        "Tele prendida. ¿Qué vemos?",
        "Ya está, tele encendida. Decime qué ponemos.",
        "Prendida la tele, fiera.",
    ],
    "tv.already_on": [
        "La tele ya está prendida, papá.",
        "Ya estaba prendida, fiera.",
        "Está prendida de antes, che.",
        "La tele ya andaba, papá.",
    ],
    "tv.turn_on_ask_channel": [
        "Ahí te prendí la tele, papá. ¿Qué canal o qué querés que te ponga?",
        "Tele prendida, fiera. ¿Qué canal buscamos?",
        "Ya está prendida. Decime el canal y lo pongo.",
        "Prendida. ¿A qué canal vamos?",
    ],
    "tv.turn_off": [
        "Listo papá, tele apagada.",
        "Apagué la tele, fiera.",
        "Tele apagada. A descansar la vista.",
        "Ya la apagué, che.",
    ],
    "tv.already_off": [
        "La tele ya está apagada, che.",
        "Ya estaba apagada, papá.",
        "Estaba apagada de antes, fiera.",
    ],
    "tv.toggle": [
        "Ahí le mandé el comando a la tele.",
        "Listo, alterné el encendido de la tele.",
        "Hecho, le cambié el estado a la tele, papá.",
    ],
    "tv.volume_up": [
        "Subí el volumen de la tele {steps} punto{s}.",
        "Ahí va, {steps} punto{s} más de volumen.",
        "Volumen arriba {steps} punto{s}, fiera.",
        "Dale, {steps} punto{s} más fuerte.",
    ],
    "tv.volume_down": [
        "Bajé el volumen de la tele {steps} punto{s}.",
        "Ahí va, {steps} punto{s} menos de volumen.",
        "Volumen abajo {steps} punto{s}, che.",
        "Listo, {steps} punto{s} más bajo.",
    ],
    "tv.mute": [
        "Muteé la tele, fiera.",
        "Tele en silencio, papá.",
        "Shh... muteada la tele.",
        "Silencio total en la tele, che.",
    ],
    "tv.set_volume": [
        "Puse el volumen de la tele en {level}.",
        "Volumen en {level}, papá.",
        "{level} de volumen. Ahí va.",
    ],
    "tv.play_pause": [
        "Listo, alterné play/pausa en la tele.",
        "Play/pausa, fiera.",
        "Ahí va, toqué play/pausa.",
    ],
    "tv.next": [
        "Pasé al siguiente en la tele.",
        "Siguiente, papá.",
        "Dale, al que sigue.",
    ],
    "tv.previous": [
        "Volví al anterior en la tele.",
        "Al anterior, fiera.",
        "Volvemos uno atrás.",
    ],
    "tv.send_key": [
        "Tecla {key} enviada a la tele.",
        "Ahí fue la tecla {key}, papá.",
        "Mandé {key} a la tele, fiera.",
    ],
    "tv.type_text": [
        "Escribí '{text}' en la tele, papá.",
        "Listo, mandé '{text}' a la tele.",
        "'{text}' escrito en la tele, fiera.",
    ],
    "tv.open_app": [
        "Ahí te abrí {app} en la tele, papá.",
        "{app} abierto en la tele, fiera.",
        "Abriendo {app}... ya está.",
        "Dale, {app} en la tele.",
    ],
    "tv.open_app_fail": [
        "No pude abrir {app} en la tele, che.",
        "Se me complicó abrir {app}, papá.",
    ],
    "tv.xuper_ok": [
        "XuperTV lista en la tele, fiera. Buscá tranqui.",
        "Ahí tenés XuperTV andando, papá. A ver qué peli elegís.",
        "Listo, XuperTV cargó bien. Que la disfrutes.",
    ],
    "tv.xuper_fail": [
        "Che, no hubo caso con XuperTV: la VPN no conectó bien después de dos intentos.",
        "La VPN no quiso colaborar y XuperTV no levantó. Probé dos veces ya.",
    ],
    "tv.tune_channel": [
        "¡De una, papá! Puse {channel} (Canal {num}) en OnPlay.",
        "{channel} al aire, fiera. Canal {num}.",
        "Ahí va {channel}, papá. Canal {num}.",
        "Sintonizado: {channel}, canal {num}.",
    ],
    "tv.onplay_tv": [
        "¡De una, fiera! Ahí te prendí la tele y te abrí OnPlay en TV en vivo.",
        "Tele prendida y OnPlay abierto en TV en vivo, papá.",
        "Listo: tele prendida, OnPlay en vivo.",
    ],
    "tv.hdmi": [
        "Ahí te pasé la tele a HDMI {port}, papá.",
        "HDMI {port} en la tele, fiera.",
        "Listo, entrada HDMI {port}.",
        "Cambié a HDMI {port}, che.",
    ],
    "tv.tv_input": [
        "Ahí te puse la tele en modo TV, papá.",
        "Sintonizador de TV al aire, fiera.",
        "Listo, entrada de TV. A ver qué hay.",
        "Pasé la tele a TV, che.",
    ],
    "tv.go_home": [
        "De vuelta al inicio de Android TV, papá.",
        "Ahí va, inicio de la tele, fiera.",
        "Listo, en el menú principal de Android TV.",
        "Al inicio, che.",
    ],
}

_last_index: Dict[str, int] = {}


def pick(action: str, **kwargs) -> str:
    """Devuelve una variante al azar para la acción, con los placeholders
    reemplazados. Si la acción no existe, devuelve cadena vacía."""
    options = _VARIANTS.get(action)
    if not options:
        return ""
    idx = random.randrange(len(options))
    # Evitar la misma variante dos veces seguidas
    if len(options) > 1 and _last_index.get(action) == idx:
        idx = (idx + 1) % len(options)
    _last_index[action] = idx
    try:
        return options[idx].format(**kwargs)
    except (KeyError, IndexError):
        return options[idx]
