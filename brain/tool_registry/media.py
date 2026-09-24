"""Herramientas de audio, energía, ventanas, portapapeles y temporizadores."""

from core.config import config

from tools.file_manager import file_manager

import os

from tools.system_control import system_control

from ._common import _clamp



def set_volume(level: int) -> str:

    """Ajusta el volumen del sistema de Windows a un porcentaje exacto de 0 a 100."""

    level = _clamp(level, 0, 100, 50)  # R-3
    res = system_control.set_volume(level)

    return res.get("message", str(res))


def volume_up() -> str:

    """Sube el volumen del sistema."""

    res = system_control.volume_up(15)

    return res.get("message", str(res))


def volume_down() -> str:

    """Baja el volumen del sistema."""

    res = system_control.volume_down(15)

    return res.get("message", str(res))


def mute() -> str:

    """Mutea o desmutea el volumen maestro de Windows."""

    res = system_control.mute()

    return res.get("message", str(res))


def media_play_pause() -> str:

    """Alterna reproducción o pausa en Spotify, YouTube u otro reproductor activo."""

    res = system_control.media_play_pause()

    return res.get("message", str(res))


def media_next() -> str:

    """Pasa a la siguiente canción o pista de música."""

    res = system_control.media_next()

    return res.get("message", str(res))


def media_prev() -> str:

    """Vuelve a la canción anterior."""

    res = system_control.media_prev()

    return res.get("message", str(res))


def lock_workstation() -> str:

    """Bloquea la sesión actual de Windows inmediatamente."""

    res = system_control.lock_workstation()

    return res.get("message", str(res))


def minimize_all() -> str:

    """Minimiza todas las ventanas abiertas y muestra el escritorio de Windows."""

    res = system_control.minimize_all()

    return res.get("message", str(res))


def take_screenshot() -> str:

    """Saca una captura de pantalla completa y la guarda en la carpeta Imágenes/Screenshots."""

    res = system_control.take_screenshot()

    return res.get("message", str(res))


def get_system_metrics(target: str = "primary") -> str:
    """Obtiene el porcentaje de uso de CPU, temperatura de hardware, memoria RAM y espacio libre en discos.
    Args:
        target: 'primary' (por defecto) para la PC Principal con Windows, o 'ddr3' para el Servidor Titán (DDR3).
    """
    is_ddr3 = target.lower() in ["ddr3", "servidor", "server", "secundaria"]
    if is_ddr3:
        res = system_control.get_system_metrics()
        temp_str = f", Temperatura: {res['temp_c']}°C" if res.get("temp_c") else ""
        return f"[Servidor Titán DDR3] CPU: {res['cpu_percent']}%{temp_str}, RAM: {res['ram_percent']}% ({res['ram_used_gb']}/{res['ram_total_gb']} GB)."

    try:
        from server.websocket_hub import ws_hub
        sat = ws_hub.get_satellite_metrics()
    except Exception:
        sat = {}

    if sat.get("connected"):
        res = sat
        label = "PC Principal (Windows)"
    else:
        local_m = system_control.get_system_metrics()
        if local_m.get("platform") == "windows":
            res = local_m
            label = "PC Principal (Windows)"
        else:
            temp_d = f", Temp: {local_m['temp_c']}°C" if local_m.get("temp_c") else ""
            return f"Aviso: La PC Principal está desconectada o el satélite inactivo. [Servidor Titán DDR3] CPU: {local_m['cpu_percent']}%{temp_d}, RAM: {local_m['ram_percent']}%."

    disks_info = []
    for d, info in res.get("disks", {}).items():
        disks_info.append(f"Disco {d}: {info.get('free_gb', 0)} GB libres de {info.get('total_gb', 0)} GB")
    disks_str = ", ".join(disks_info)
    temp_str = f", Temperatura: {res['temp_c']}°C" if res.get("temp_c") else ""

    return f"[{label}] CPU: {res['cpu_percent']}%{temp_str}, RAM: {res['ram_percent']}% ({res.get('ram_used_gb', 0)}/{res.get('ram_total_gb', 0)} GB). Discos: {disks_str}."


def cool_down_pc() -> str:
    """Aplica refrigeración activa en la PC Principal: cambia el plan de energía a Modo Frío (Economizador) y cierra tareas de fondo para bajar la temperatura del procesador inmediatamente."""
    from brain.local_intents import local_intents
    # S-6: cambia plan de energía y cierra procesos -> pide confirmación.
    return local_intents.request_confirmation("cool_down_pc")


def set_power_plan(plan_mode: str) -> str:
    """Cambia el modo térmico / perfil de energía de la PC Principal: 'eco' (Modo Frío/Economizador para bajar temperatura), 'balanced' (Equilibrado normal), o 'performance' (Alto rendimiento/Turbo para juegos)."""
    res = system_control.set_power_plan(plan_mode)
    return res.get("message", str(res))


def switch_screen_view(view_name: str) -> str:
    """Cambia la pantalla activa en el celular o display secundario. Opciones: 'face', 'telemetry', o 'orb'."""
    res = system_control.switch_screen_view(view_name)
    return res.get("message", str(res))


def set_avatar_stage(stage: str) -> str:
    """Cambia la animación/etapa de reposo del avatar en el celular: 'mate' (tomar mates), 'drowsy' (modorra/sueño), 'sleeping' (dormir/siesta), 'wake' (despertar sobresaltado), 'idle' (normal activo)."""
    res = system_control.set_inactivity_stage(stage)
    return res.get("message", str(res))


def flip_camera(camera_mode: str = "toggle") -> str:

    """Cambia entre la cámara frontal y la cámara trasera del celular."""

    res = system_control.flip_camera(camera_mode)

    return res.get("message", str(res))


def set_assistant_name(new_name: str) -> str:

    """Cambia el nombre con el que se identifica el asistente de voz."""

    nom = config.set_assistant_name(new_name)

    return f"A partir de ahora me llamo {nom}, hermano."


def shutdown_pc() -> str:

    """Apaga la computadora de forma segura en 10 segundos."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("shutdown")


def restart_pc() -> str:

    """Reinicia la computadora de forma segura en 10 segundos."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("restart")


def sleep_pc() -> str:

    """Pone la computadora en modo suspensión de bajo consumo energético."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("sleep")


def wake_windows_pc() -> str:
    """Envía Wake-on-LAN desde la PC Linux para encender la PC Windows."""
    from tools.wake_on_lan import wake_windows_pc as send_wol
    res = send_wol()
    return res.get("message", str(res))


def get_clipboard() -> str:

    """Lee el texto actual copiado en el portapapeles de la computadora."""

    res = system_control.get_clipboard()

    return res.get("message", str(res))


def set_clipboard(text: str) -> str:

    """Copia un texto específico al portapapeles de Windows en la computadora."""

    res = system_control.set_clipboard(text)

    return res.get("message", str(res))


def send_file_to_telegram(query_or_path: str) -> str:

    """Busca un archivo o documento en la computadora y se lo envía directamente al usuario por Telegram a su celular."""

    target_path = None

    if os.path.exists(query_or_path):

        target_path = query_or_path

    else:

        res = file_manager.search_files(query=query_or_path, max_results=1)

        if res.get("count", 0) > 0:

            target_path = res["files"][0]["path"]

    

    if not target_path or not os.path.exists(target_path):

        return f"No encontré ningún archivo que coincida con '{query_or_path}' para mandarte."

    # La matriz de autonomía exige confirmación: se resuelve el archivo
    # ANTES de pedirla, así el usuario confirma el archivo real.
    from brain.local_intents import local_intents
    return local_intents.request_confirmation(
        "send_file_to_telegram",
        target_path=target_path,
        filename=os.path.basename(target_path),
    )


def set_timer(minutes: float, label: str = "Temporizador") -> str:

    """Programa un temporizador o alarma en minutos que sonará en la PC y avisará por Telegram."""

    from core.scheduler import titan_scheduler
    # R-3: minutos válidos 0..1440 (24h); un valor absurdo o negativo no tiene sentido.
    try:
        minutes = max(0.0, min(1440.0, float(minutes)))
    except (TypeError, ValueError):
        minutes = 10.0

    return titan_scheduler.set_timer(minutes, label)


def cancel_timer(label: str) -> str:

    """Cancela un temporizador activo por su etiqueta o nombre."""

    from core.scheduler import titan_scheduler

    return titan_scheduler.cancel_timer(label)


def list_timers() -> str:

    """Lista los temporizadores que están corriendo en este momento."""

    from core.scheduler import titan_scheduler

    return titan_scheduler.list_timers()
