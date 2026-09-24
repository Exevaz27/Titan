"""D-E: átomos compartidos del pipeline de comandos (voz/HUD y Telegram).

Hallazgo de la D-E: la "triplicación" del informe era parcial.
- El WS (/ws `chat_prompt`/`command`) NO tiene intents propios: deriva a
  `main.handle_user_command` (el pipeline de voz). Sin duplicación.
- Telegram NO reimplementa los intents locales: llama a
  `brain.local_intents.try_handle`. Sin duplicación.
- La duplicación REAL: la lista de disparadores de generación de imágenes
  vivía en dos lugares (`main.py` con 36, `integrations/telegram_bot.py`
  con 39 = los 36 + 3 comandos con `/`), con el matcheo y la extracción
  del prompt copiados casi verbatim. Si se agregaba un trigger en un
  canal, el otro quedaba desactualizado.

Este módulo es la única fuente de verdad para esos disparadores.
El renderizado sigue siendo de cada canal (tts.speak vs _send_text,
teclados, fotos): acá solo vive la clasificación, sin efectos.

Orden de IMAGE_TRIGGERS: idéntico al original de voz (el orden importa
para la extracción: se usa el primer trigger que aparece con `in`).
TELEGRAM_IMAGE_TRIGGERS: los 3 comandos con `/` PRIMERO + la base,
idéntico al orden original de Telegram.
"""

from typing import Optional, Sequence

# Disparadores en lenguaje natural. Fuente única (antes: main.py).
IMAGE_TRIGGERS = (
    "creame una imagen de", "creá una imagen de", "crea una imagen de",
    "creame una imagen", "creá una imagen", "crea una imagen",
    "haceme una imagen de", "hacé una imagen de", "hace una imagen de",
    "haceme una imagen", "hacé una imagen", "hace una imagen",
    "generame una imagen de", "generá una imagen de", "genera una imagen de",
    "generame una imagen", "generá una imagen", "genera una imagen",
    "dibujame una imagen de", "dibujá una imagen de", "dibuja una imagen de",
    "dibujame un", "dibujame una", "dibujame el", "dibujame la", "dibujame",
    "dibujá un", "dibujá una", "dibujá el", "dibujá la", "dibujá",
    "dibuja un", "dibuja una", "dibuja el", "dibuja la", "dibuja",
)

# Telegram suma sus comandos con `/` al principio, como en el original.
TELEGRAM_IMAGE_TRIGGERS = (
    "/imagen", "/dibujar", "/crear_imagen",
) + IMAGE_TRIGGERS


def extract_image_prompt(
    norm_text: str,
    original_text: str,
    triggers: Sequence[str] = IMAGE_TRIGGERS,
) -> Optional[str]:
    """Detecta un comando de generación de imágenes y extrae el prompt.

    Replica EXACTA la lógica que antes estaba duplicada en main.py y en
    integrations/telegram_bot.py (dos pasos: detección con
    startswith/rodeado-por-espacios, y extracción con el primer trigger
    que aparece con `in`):

    - Devuelve None si no es un comando de imagen.
    - Devuelve el prompt (str, ya sin espacios) si hay trigger + prompt.
    - Devuelve "" si hay trigger pero sin prompt (el canal muestra su
      mensaje de ayuda/pregunta correspondiente).

    `norm_text` es el texto ya normalizado por el canal (voz: lower();
    Telegram: strip().lower()); `original_text` es el texto original
    para extraer el prompt con sus mayúsculas intactas.
    """
    is_img = any(
        norm_text.startswith(pfx) or f" {pfx} " in f" {norm_text} "
        for pfx in triggers
    )
    if not is_img:
        return None
    for pfx in triggers:
        if pfx in norm_text:
            idx = norm_text.find(pfx)
            return original_text[idx + len(pfx):].strip()
    return None


def is_image_command(
    norm_text: str,
    triggers: Sequence[str] = IMAGE_TRIGGERS,
) -> bool:
    """True si el texto normalizado es un comando de generación de imágenes."""
    return any(
        norm_text.startswith(pfx) or f" {pfx} " in f" {norm_text} "
        for pfx in triggers
    )
