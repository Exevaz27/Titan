"""P0-5 — Política central de modos restrictivos (rebelde / pibes).

Premisa de estos modos: Titán NO ejecuta acciones. Antes de P0-5 ese freno
vivía en tres lugares distintos y con tres alcances distintos:

- Gemini: `tools=None` en modo rebelde (bien, pero solo cubre a Gemini).
- Voz local (`local_intents`): freno solo para intents locales, DESPUÉS de
  resolver confirmaciones pendientes (un "dale" en modo rebelde ejecutaba
  un apagado pedido en modo normal).
- Telegram: SIN freno. Los botones (apagar, TV, captura...) y comandos
  (/tv, /dormir...) ejecutaban igual en modo rebelde.
- HUD/voz directa (`main.py`, `/ws`): ramas directas (mirar pantalla,
  generar imagen, cool_down_pc...) sin freno.

Este módulo es el punto único de verdad. Todos los caminos de ejecución
(voz, Telegram, HUD) lo consultan antes de actuar.
"""

from __future__ import annotations

# Modos en los que Titán no ejecuta acciones.
RESTRICTED_MODES = ("rebel", "kids")


def current_mode() -> str:
    """Modo actual del cerebro ("normal" si no se puede determinar)."""
    try:
        from brain.gemini_client import brain

        return getattr(brain, "current_mode", "normal") or "normal"
    except Exception:
        return "normal"


def actions_blocked() -> bool:
    """True si el modo actual prohíbe ejecutar acciones."""
    return current_mode() in RESTRICTED_MODES


def refusal_text() -> str:
    """Respuesta corta para Telegram/botones cuando se bloquea una acción."""
    if current_mode() == "kids":
        return (
            "🟡 *Modo Pibes activo*\n"
            "¡Ni lo sueñes, remolón! En este modo no hago nada. "
            "Si querés que te dé una mano, cambiá al modo compinche."
        )
    return (
        "🔴 *Modo Rebelde activo*\n"
        "¡¿Me estás cargando?! En modo rebelde no te pienso hacer un carajo. "
        "Hacelo vos con tus dos manos, vago."
    )


def pollera_blocks_actions() -> bool:
    """MODO POLLERA (2026-09-18): True si estamos en modo pollera y quien
    habla NO es Oriana (huella de voz). En ese caso solo Oriana puede dar
    órdenes de acciones; el resto solo puede cambiar de modo o consultar.
    Si no se puede determinar la identidad, se bloquea (fail-closed)."""
    if current_mode() != "pollera":
        return False
    try:
        from audio.speaker_id import current_identity
        ident, _ = current_identity()
        return ident != "oriana"
    except Exception:
        return True


def refusal_speech() -> str:
    """Versión hablada y breve para la voz."""
    if current_mode() == "kids":
        return "¡Ni lo sueñes, remolón! En modo pibes no hago nada."
    return "¡En modo rebelde no te pienso hacer un carajo!"


# Callbacks de Telegram que NO ejecutan acciones: solo navegan entre menús.
# Todo lo demás (tv:, power:, vigilance:, cmd:*, confirm:*) se bloquea en
# modos restrictivos. Los cambios de modo (mode:*) siempre están permitidos
# para poder salir del modo.
TELEGRAM_NAVIGATION_CALLBACKS = frozenset({
    "cmd:back_menu",
    "cmd:power_menu",
    "cmd:tv_menu",
    "cmd:vigilance_menu",
})


def telegram_callback_allowed(data: str) -> bool:
    """True si el callback puede atenderse en modo restrictivo."""
    if not data:
        return False
    if data.startswith("mode:"):
        return True
    return data in TELEGRAM_NAVIGATION_CALLBACKS
