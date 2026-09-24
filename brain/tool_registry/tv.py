"""Herramientas de la tele BGH Android TV."""

from tools.tv_control import tv_control

from ._common import _clamp



# ---------------------------------------------------------
# HERRAMIENTAS PARA TELEVISOR BGH ANDROID TV (192.168.100.8)
# ---------------------------------------------------------
def tv_turn_on() -> str:
    """Enciende la tele BGH Android TV."""
    res = tv_control.turn_on()
    return res.get("message", "Tele prendida.")


def tv_turn_off() -> str:
    """Apaga o pone en modo reposo/standby la tele BGH Android TV."""
    res = tv_control.turn_off()
    return res.get("message", "Tele apagada.")


def tv_power_toggle() -> str:
    """Alterna el encendido o apagado de la tele BGH Android TV."""
    res = tv_control.power_toggle()
    return res.get("message", "Comando de encendido/apagado enviado a la tele.")


def tv_volume_up(steps: int = 2) -> str:
    """Sube el volumen de la tele BGH Android TV."""
    steps = _clamp(steps, 1, 20, 2)  # R-3
    res = tv_control.volume_up(steps)
    return res.get("message", "Volumen de la tele subido.")


def tv_volume_down(steps: int = 2) -> str:
    """Baja el volumen de la tele BGH Android TV."""
    steps = _clamp(steps, 1, 20, 2)  # R-3
    res = tv_control.volume_down(steps)
    return res.get("message", "Volumen de la tele bajado.")


def tv_mute() -> str:
    """Mutea o desmutea el volumen de la tele BGH Android TV."""
    res = tv_control.mute()
    return res.get("message", "Muteé la tele.")


def tv_set_volume(level: int) -> str:
    """Ajusta el volumen de la tele BGH Android TV a un nivel específico de 0 a 100."""
    level = _clamp(level, 0, 100, 50)  # R-3
    res = tv_control.set_volume(level)
    return res.get("message", f"Volumen de la tele puesto en {level}.")


def tv_play_pause() -> str:
    """Alterna Play / Pausa en la reproducción de la tele BGH Android TV (YouTube, Netflix, OnPlay, etc.)."""
    res = tv_control.play_pause()
    return res.get("message", "Play/Pausa en la tele.")


def tv_next_track() -> str:
    """H-3: pasa al siguiente video/capítulo/tema en la tele BGH Android TV."""
    res = tv_control.next_track()
    return res.get("message", "Pasé al siguiente en la tele.")


def tv_prev_track() -> str:
    """H-3: vuelve al video/capítulo/tema anterior en la tele BGH Android TV."""
    res = tv_control.prev_track()
    return res.get("message", "Volví al anterior en la tele.")


def tv_open_app(app_name: str) -> str:
    """Abre una aplicación en la tele BGH Android TV por su nombre (ej: 'onplay', 'youtube', 'netflix', 'vlc', 'spotify', 'xupertv', 'cloudstream', 'ukiku').

    XuperTV (películas y series; el usuario la llama "xuper", "super tv" o "súper tv") SIEMPRE se abre sola por su cadena de VPN: no hay que hacer nada extra, la tool ya maneja la espera y los reintentos."""
    res = tv_control.open_app(app_name)
    return res.get("message", f"Abriendo {app_name} en la tele.")


def tv_open_onplay(channel: str = "") -> str:
    """Abre la aplicación OnPlay en la tele BGH Android TV y opcionalmente sintoniza un canal numérico o por nombre."""
    res = tv_control.open_onplay_live(channel if channel else None)
    return res.get("message", "Abriendo OnPlay en la tele.")


def tv_tune_channel(channel_query: str) -> str:
    """Sintoniza un canal específico en OnPlay en la tele BGH por su nombre o número (ej: 'ESPN Premium', 'TNT Sports', 'TyC Sports', 'Telefe', 'TN', '15', '17')."""
    res = tv_control.tune_channel(channel_query)
    return res.get("message", f"Sintonizando {channel_query} en la tele.")


def tv_list_channels(category: str = "") -> str:
    """Lista los canales disponibles en OnPlay agrupados por categoría o filtrados por búsqueda."""
    channels = tv_control.list_channels(category if category else None)
    if not channels:
        return "No encontré canales para esa categoría en OnPlay."
    sample = channels[:15]
    lines = [f"{c['number']}. {c['name']} ({c['category']})" for c in sample]
    res_str = "\n".join(lines)
    if len(channels) > 15:
        res_str += f"\n... y {len(channels) - 15} canales más (Total: {len(channels)})."
    return res_str


def tv_send_key(key_name: str) -> str:
    """Envía una tecla de navegación del control remoto a la tele BGH: 'arriba', 'abajo', 'izquierda', 'derecha', 'ok', 'atras', 'inicio', 'menu'."""
    res = tv_control.send_key(key_name)
    return res.get("message", f"Tecla {key_name} enviada a la tele.")


def tv_type_text(text: str) -> str:
    """Escribe un texto en el buscador o campo de texto activo de la tele BGH Android TV."""
    res = tv_control.type_text(text)
    return res.get("message", f"Texto '{text}' escrito en la tele.")


def tv_get_status() -> str:
    """Consulta el estado de conexión y energía de la tele BGH Android TV."""
    res = tv_control.get_status()
    return f"Estado de la tele BGH: {res.get('power')}, IP {res.get('ip')}."
