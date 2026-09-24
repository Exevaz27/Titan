"""Paquete de intents locales (antes brain/local_intents.py).

Fachada compatible: `LocalIntentEngine`, `local_intents` y
`try_handle(text) -> (bool, Optional[str])` funcionan igual que antes.
Cada sección numerada del try_handle original vive ahora en su propio
handler; el dispatcher preserva el orden de prioridad exacto.
"""

from typing import Tuple, Optional

from .mode import handle_mode, handle_pending_confirmation
from .datetime_weather import handle_datetime, handle_weather
from .hardware import handle_hardware, handle_doctor, handle_network
from .hud_camera import handle_hud_screens, handle_camera, handle_j2
from .media import handle_volume, handle_youtube, handle_spotify
from .windows import handle_apps, handle_window_control, handle_recycle, handle_wol, handle_power, handle_brightness
from .web import handle_google, handle_web_shortcuts
from .about import handle_about_titan
from .files import handle_organizer, handle_read_aloud
from .clipboard_ai import handle_clipboard_ai
from .voice import handle_voice_enroll


class LocalIntentEngine:
    def __init__(self):
        # El estado de confirmaciones pendientes ya no vive acá:
        # lo maneja core.confirmation (política central con TTL, origen y usuario).
        pass

    def request_confirmation(self, action: str, **args) -> str:
        from core.confirmation import confirmation_manager, current_channel
        origin, requester = current_channel()
        conf = confirmation_manager.request(
            action, origin=origin, requester=requester, args=args
        )
        return conf.prompt_message

    def try_handle(self, text: str) -> Tuple[bool, Optional[str]]:
        if not text:
            return False, None

        clean = text.lower().strip()
        norm = (clean
            .replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("¿", "")
            .replace("?", "")
            .replace("¡", "")
            .replace("!", "")
            .strip())

        # Quitar prefijo de invocación si vino en el texto (ej: "titán prende la tele", "titan pone espn")
        for wake in ["titan ", "titán ", "che titan ", "che titán "]:
            if norm.startswith(wake):
                norm = norm[len(wake):].strip()


        r = handle_mode(self, text, clean, norm)
        if r is not None:
            return True, r
        # P0-5 — Política central de modos restrictivos (rebelde/pibes):
        # acá NO se ejecuta nada local, ni siquiera confirmaciones pendientes
        # pedidas en otro modo. Solo la gestión de modos (arriba) sigue viva
        # para poder salir. El resto lo putea Gemini sin herramientas.
        from core.mode_policy import actions_blocked, pollera_blocks_actions
        if actions_blocked():
            return False, None
        # MODO POLLERA (2026-09-18, rev 2026-09-20): si quien habla no es
        # Oriana (huella), los intents de ACCIONES se saltean; solo quedan
        # consultas puras y confirmaciones pendientes (Exequiel debe poder
        # confirmar lo comprometedor). La gestión de modos (arriba) sigue
        # viva para salir.
        _pollera_block = pollera_blocks_actions()

        for _h in _HANDLERS:
            if _pollera_block and _h not in _POLLERA_QUERY_HANDLERS:
                continue
            r = _h(self, text, clean, norm)
            if r is not None:
                return True, r
        # MODO POLLERA (rev 2026-09-20): si parecía una orden y se bloqueó,
        # NO se responde con frase fija en local (era el loro: random.choice
        # entre 4 frases se repetía). Se deja caer a Gemini, que niega en
        # personaje con el prompt de pollera (igual que rebelde/pibes:
        # "lo putea Gemini sin herramientas"). Seguro: en pollera las tools
        # de Gemini solo están activas si habla Oriana, así que solo puede
        # hablar, nunca ejecutar.
        return False, None


_HANDLERS = [handle_pending_confirmation, handle_voice_enroll, handle_datetime, handle_weather, handle_hardware, handle_hud_screens, handle_camera, handle_volume, handle_youtube, handle_spotify, handle_apps, handle_window_control, handle_recycle, handle_google, handle_web_shortcuts, handle_wol, handle_power, handle_about_titan, handle_j2, handle_brightness, handle_doctor, handle_network, handle_organizer, handle_clipboard_ai, handle_read_aloud]


# MODO POLLERA (2026-09-18): intents que NO son órdenes y siguen vivos
# para cualquiera en modo pollera (consultas puras + confirmaciones
# pendientes + registro de voz, que Exequiel necesita para probar el modo).
_POLLERA_QUERY_HANDLERS = frozenset({
    handle_pending_confirmation, handle_voice_enroll,
    handle_datetime, handle_weather, handle_about_titan,
})


local_intents = LocalIntentEngine()
