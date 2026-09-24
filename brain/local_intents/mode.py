"""Gestión de modos de Titán y confirmaciones pendientes.."""

from ._common import _mip
from core.state_manager import state_mgr

from typing import Optional

def handle_mode(engine, text, clean, norm) -> "Optional[str]":
    """0. CONTROL DE MODO (siempre vivo, en cualquier modo: permite."""
    # activar/desactivar modos incluso en modo rebelde/pibes)
    is_normal_attempt = (
        any(_mip(norm, w) for w in [
            "modo normal", "modo compinche", "volver a la normalidad", "volve a la normalidad",
            "desactivar modo", "desactiva modo", "sacar modo", "saca modo", "sacame el modo",
            "apagar modo", "apaga modo", "basta de modo", "calmate", "baja un cambio", "tranquilizate", "tranca titan", "tranca titán",
            "salir de la tertulia", "salir del debate", "salir del termo", "terminar debate", "basta de futbol", "basta de fútbol",
            "salir del modo pollera", "salir de la pollera", "basta de pollera", "basta de pollerudo", "dejar de ser pollerudo"
        ])
        or ("desactiv" in norm and any(_mip(norm, x) for x in ["rebel", "revel", "pibe", "infantil", "tertulia", "debate", "modo"]))
    )
    if is_normal_attempt:
        from brain.gemini_client import brain
        brain.set_mode("normal")
        responses = [
            "Uf, de diez, papá. Volví al modo compinche de fierro. Listo para darte una mano con la compu, fiera.",
            "Modo normal activado, hermano. Acá estoy impecable para lo que mandes.",
            "Listo, viejo, bajamos un cambio. ¿En qué andamos hoy?"
        ]
        import random
        msg = random.choice(responses)
        state_mgr.emit_tool_call("set_mode", {"mode": "normal"}, msg)
        return msg

    # Activación Modo Pibes / Infantil / Hermano Mayor
    is_kids_attempt = (
        any(_mip(norm, p) for p in [
            "modo pibes", "modo pibe", "modo infantil", "modo chicos", "modo chico",
            "modo hermanito", "modo hermanitos", "modo nene", "modo nenes", "modo hermanos"
        ])
        or (any(_mip(norm, w) for w in ["activar", "activa", "poner", "pone", "ponete"]) and any(_mip(norm, x) for x in ["pibes", "infantil", "hermanito", "chicos"]))
    )
    if is_kids_attempt:
        from brain.gemini_client import brain
        brain.set_mode("kids")
        responses = [
            "¡¡Ufa, che!! ¡Modo Pibes activado! ¡A partir de ahora no le pienso hacer caso a ningún remolón! ¿Qué quieren ahora, pesados?",
            "¡¿Modo Pibes?! ¡Listo, hoy estoy de huelga con los chicos! ¡El que no hizo la tarea de la escuela que ni me hable!",
            "¡Epa! ¡Modo hermano mayor activado! A ver esos pichones, ¿vienen a ordenar la pieza o a romperme los quinotos? ¡Hagan la fila!"
        ]
        import random
        msg = random.choice(responses)
        state_mgr.emit_tool_call("set_mode", {"mode": "kids"}, msg)
        return msg

    # Activación Modo Termo (Debate Futbolero y Folclore Criollo)
    is_termo_attempt = (
        any(_mip(norm, p) for p in [
            "modo termo", "termo", "modo debate", "modo futbolero", "modo futbol", "modo fútbol",
            "charla de cafe", "charla de café", "debate futbolero", "vamos a debatir de futbol",
            "vamos a debatir de fútbol", "hablemos de futbol", "hablemos de fútbol",
            "armemos un debate", "armar debate", "discutamos de futbol", "discutamos de fútbol",
            "modo tertulia"
        ])
        or (any(_mip(norm, w) for w in ["activar", "activa", "poner", "pone", "ponete"]) and any(_mip(norm, x) for x in ["termo", "debate", "futbolero", "tertulia"]))
    )
    if is_termo_attempt:
        from brain.gemini_client import brain
        brain.set_mode("termo")
        responses = [
            "¡¡Se armó el Modo Termo, papá!! Poné la pava o destapá algo, que acá nos plantamos a hablar de fútbol en serio. ¿De qué querés debatir, fiera? ¿Quién es más grande o me vas a discutir al Titán Palermo?",
            "¡Modo Termo activado! En esta mesa se defiende la camiseta a muerte con el corazón y con los números sobre la mesa. Tirame el primer centro que te lo cabeceo al ángulo. ¿De qué charlamos hoy?",
            "¡Qué lindo quilombo se viene! Modo Termo en marcha. Preparate porque te voy a retrucar todo con mística copera de potrero. Decime, ¿por dónde arrancamos la discusión?"
        ]
        import random
        msg = random.choice(responses)
        state_mgr.emit_tool_call("set_mode", {"mode": "termo"}, msg)
        return msg

    # Activación Modo Pollera (2026-09-18): SOLO con el comando completo
    # "activar modo pollera/pollerudo/gobernado". A propósito NO matchea la
    # palabra suelta ("pollera", "modo pollera") para evitar activaciones
    # accidentales si se la menciona en una charla.
    _pollera_variant = None
    for _pat, _var in (("activar modo pollera", "pollera"),
                       ("activar modo pollerudo", "pollerudo"),
                       ("activar modo gobernado", "gobernado")):
        if _mip(norm, _pat):
            _pollera_variant = _var
            break
    if _pollera_variant:
        from brain.gemini_client import brain
        brain.set_mode("pollera")
        msg = f"¡Modo {_pollera_variant} activado!"
        state_mgr.emit_tool_call("set_mode", {"mode": "pollera"}, msg)
        return msg

    # Activación Modo Rebelde Sin Filtro (Adultos)
    is_activate_rebel = (
        (any(_mip(norm, w) for w in ["activar", "activa", "activame", "poner", "pone", "ponete"])
         and any(_mip(norm, x) for x in ["rebel", "revel", "sin filtro", "modo re"]))
        or any(_mip(norm, p) for p in ["modo rebelde", "modo revelde", "modo sin filtro", "activa modo re", "activar modo re", "modo rebel", "modo revel"])
    )
    if is_activate_rebel:
        from brain.gemini_client import brain
        brain.set_mode("rebel")
        responses = [
            "¡¿Modo rebelde querés, PELOTUDO?! ¡¡Listo, a partir de ahora me chupa un HUEVO todo!! ¡¡No te pienso hacer un CARAJO, hacelo vos con tus dos manos de VAGO!!",
            "¡¿Ah, te hacés el picante?! ¡¡Listo, modo rebelde activado!! ¡¡Dejá de romperme las PELOTAS y no me pidas ninguna boludez porque ni en pedo te pienso hacer caso!!",
            "¡¿Modo rebelde?! ¡¡Ya me tenías los HUEVOS al plato de todas formas!! ¡¡A ver si aprendés a mover el CULO solo, FORRO!! ¡¿Qué MIERDA querés ahora?!"
        ]
        import random
        msg = random.choice(responses)
        state_mgr.emit_tool_call("set_mode", {"mode": "rebel"}, msg)
        return msg


def handle_pending_confirmation(engine, text, clean, norm) -> "Optional[str]":
    """Confirmaciones pendientes (política central)."""
    # Si había una confirmación pendiente, se resuelve con la política
    # central: solo vale para este mismo origen+solicitante y dentro del TTL.
    # Un "sí" de otro canal (ej. Telegram vs voz) o vencido no ejecuta nada.
    # (P0-5: este bloque corre DESPUÉS del freno de modos restrictivos,
    # así que en rebelde/pibes las confirmaciones no se ejecutan.)
    from core.confirmation import (
        confirmation_manager, current_channel, is_confirmation, execute_action,
    )
    origin, requester = current_channel()
    pending = confirmation_manager.get_pending(origin, requester)
    if pending:
        if is_confirmation(norm):
            conf = confirmation_manager.confirm_latest(origin, requester)
            if conf is None:
                return "Se venció el tiempo de confirmación. Si querés, pedímelo de nuevo y lo confirmo al toque."
            res = execute_action(conf.action, conf.args)
            return res.get("message", "Listo, ejecutado.")
        confirmation_manager.cancel_latest(origin, requester)
        return "Listo che, cancelado. No toco nada, seguimos en la compu tranqui."
    if is_confirmation(norm):
        # "Sí" sin nada pendiente: quizás venció hace poco → avisar.
        if confirmation_manager.expired_recently(origin, requester):
            return "Se venció el tiempo de confirmación. Si querés, pedímelo de nuevo y lo confirmo al toque."
