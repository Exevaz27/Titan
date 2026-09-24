"""Registro de huellas de voz (2026-09-17, multi-voz 2026-09-18).

Intents: "registrá mi voz" / "registrá la voz de <nombre>",
"olvidá mi voz" / "olvidá la voz de <nombre>", y consulta de estado.
"""

import re
from typing import Optional

from ._common import _mip


def _extract_other_name(norm: str):
    """Si el texto menciona 'la voz de <nombre>', devuelve (interno, display)."""
    m = re.search(r"voz de ([a-zñ ]+?)$", norm.strip())
    if not m:
        return None, None
    raw = m.group(1).strip()
    if not raw or len(raw.split()) > 3:
        return None, None
    from audio.speaker_id import _safe_name
    safe = _safe_name(raw)
    if not safe:
        return None, None
    return safe, raw.title()


def _do_enroll(name: str, display: str) -> str:
    from audio.speaker_id import (
        enrollment_active, start_enrollment, has_voiceprint, warmup_satellite,
    )
    if has_voiceprint(name):
        quien = "tu huella" if name == "exequiel" else f"la huella de {display}"
        return (f"Ya tengo {quien} registrada. Si querés hacerla de nuevo, "
                f"primero decime 'olvidá {'mi voz' if name == 'exequiel' else 'la voz de ' + display}'.")
    msg = start_enrollment(name, display)
    if enrollment_active():
        try:
            import threading
            from audio.stream_listener import stream_listener
            loop = stream_listener._loop
            if loop is not None:
                threading.Thread(target=warmup_satellite, args=(loop,), daemon=True).start()
        except Exception:
            pass
    return msg


def handle_voice_enroll(engine, text, clean, norm) -> Optional[str]:
    from audio.speaker_id import (
        enrollment_active,
        cancel_enrollment,
        has_voiceprint,
        current_identity,
        delete_voiceprint,
        list_voiceprints,
        display_name,
    )

    # Durante un registro en curso el audio lo captura el enroller
    # (ver stream_listener); acá solo se atiende el texto si llegara.
    if enrollment_active():
        if any(_mip(norm, w) for w in ["cancel", "olvida", "deja", "termina", "basta"]):
            return cancel_enrollment()
        return None

    other_name, other_display = _extract_other_name(norm)

    is_delete = any(_mip(norm, p) for p in [
        "olvida mi voz", "borra mi voz", "elimina mi huella", "elimina mi voz",
        "borra mi huella", "olvida la voz", "borra la voz",
    ])
    if is_delete:
        target, target_display = (other_name, other_display) if other_name else ("exequiel", "Exequiel")
        if delete_voiceprint(target):
            quien = "tu huella de voz" if target == "exequiel" else f"la huella de {target_display}"
            return f"Listo, borré {quien}."
        return "No tenía esa huella guardada."

    is_list = any(_mip(norm, p) for p in [
        "voces tenes", "voces registradas", "quienes tienen voz", "quienes tienen huella",
    ])
    if is_list:
        names = list_voiceprints()
        if not names:
            return "Todavía no registré ninguna voz. Decime 'registrá mi voz' y arrancamos."
        quienes = ", ".join(display_name(n) for n in names)
        return f"Tengo registradas las voces de: {quienes}."

    is_status = any(_mip(norm, p) for p in [
        "mi huella de voz", "tenes mi voz", "quien soy para vos",
    ])
    if is_status:
        if has_voiceprint("exequiel"):
            ident, score = current_identity()
            if ident == "exequiel":
                return f"Sí, tengo tu huella registrada. Y por tu voz, sos vos el que me habla (certeza {score:.0%})."
            return "Sí, tengo tu huella registrada."
        return "Todavía no registré tu voz. Decime 'registrá mi voz' y lo hacemos."

    is_enroll = any(_mip(norm, p) for p in [
        "registra mi voz", "registrar mi voz", "guarda mi voz",
        "memoriza mi voz", "aprende mi voz", "reconoce mi voz",
        "quiero que reconozcas mi voz", "registra la voz", "registrar la voz",
    ])
    if not is_enroll:
        return None

    if other_name:
        return _do_enroll(other_name, other_display)
    return _do_enroll("exequiel", "Exequiel")
