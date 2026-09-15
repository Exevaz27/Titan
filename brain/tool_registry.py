import os

from typing import Dict, Any, List, Callable

from core.config import config

from tools.app_launcher import app_launcher

from tools.file_manager import file_manager

from tools.system_control import system_control



# Implementaciones adaptadas para Function Calling de Gemini



def launch_app(app_name: str) -> str:

    """Abre un programa o aplicación nativa o portable en Windows por su nombre (ej: 'spotify', 'inkscape', 'calculadora', 'chrome', 'notepad')."""

    res = app_launcher.launch_app(app_name)

    return res.get("message", str(res))



def register_portable_app(alias: str, file_path: str) -> str:

    """Registra una nueva aplicación o ejecutable portable en el catálogo apps_catalog.json con un alias amigable."""

    res = app_launcher.register_portable_app(alias, file_path)

    return res.get("message", str(res))



def search_files(query: str, extension: str = "", location: str = "", max_results: int = 8) -> str:

    """Busca archivos en la computadora por nombre o extensión en los discos y carpetas configuradas."""

    res = file_manager.search_files(

        query=query,

        extension=extension if extension else None,

        location=location if location else None,

        max_results=max_results

    )

    if res["count"] == 0:

        return f"No se encontraron archivos con el término '{query}'."

    

    lines = [f"Se encontraron {res['count']} archivo(s):"]

    for f in res["files"]:

        size = f.get('size_kb', 0)

        lines.append(f"- {f['name']} ({size} KB) en: {f['path']}")

    return "\n".join(lines)



def open_file(file_path: str) -> str:

    """Abre un archivo específico con su programa predeterminado en Windows."""

    res = file_manager.open_file(file_path)

    return res.get("message", str(res))



def show_in_folder(file_path: str) -> str:

    """Abre el explorador de archivos de Windows y resalta el archivo indicado."""

    res = file_manager.show_in_folder(file_path)

    return res.get("message", str(res))



def trash_file(file_path: str) -> str:

    """Manda un archivo a la papelera de reciclaje de Windows de forma segura (sin borrarlo permanentemente)."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("trash_file", file_path=file_path)



def move_file(source: str, destination: str) -> str:

    """Mueve un archivo de una ruta origen a una ruta destino."""

    res = file_manager.move_file(source, destination)

    return res.get("message", str(res))



def copy_file(source: str, destination: str) -> str:

    """Copia un archivo de una ruta a otra."""

    res = file_manager.copy_file(source, destination)

    return res.get("message", str(res))



def read_file_content(file_path: str) -> str:

    """Lee el contenido de un archivo de texto, código, markdown, csv o notas para poder responder sobre él."""

    res = file_manager.read_file_content(file_path)

    if res.get("status") == "success":

        return f"Contenido de {res['filename']}:\n{res['content']}"

    return res.get("message", "No se pudo leer el archivo.")



def set_volume(level: int) -> str:

    """Ajusta el volumen del sistema de Windows a un porcentaje exacto de 0 a 100."""

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
    res = system_control.cool_down_pc()
    return res.get("message", str(res))

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



def get_weather(city: str = "Buenos Aires") -> str:

    """Consulta el pronóstico y clima actual de cualquier ciudad (temperatura, lluvia, viento)."""

    res = system_control.get_weather(city)

    return res.get("message", str(res))



def get_soccer_info(query: str = "", team: str = "", date: str = "") -> str:

    """Consulta fichas técnicas oficiales, formaciones titulares (el 11 inicial y suplentes de ambos equipos), goles y resultados de fútbol de cualquier partido: tanto históricos (ej. finales de Libertadores, Mundiales, Champions League) como partidos recientes, de hoy o próximos de cualquier equipo (Boca Juniors, River Plate, Selección Argentina, Real Madrid, etc.)."""

    res = system_control.get_soccer_info(query=query, team=team, date=date)

    return res.get("results", str(res))



def search_web(query: str = "") -> str:

    """Busca en internet en tiempo real (Google / Bing / ESPN / Wikipedia) para verificar cualquier información actual o deportiva del mundo: partidos de fútbol pasados o recientes (resultados, ficha técnica y formación titular oficial del 11 con suplentes de cualquier fecha o rival), directores técnicos de cualquier club, fichajes, noticias de hoy, personas, autoridades, cotizaciones, historia y cualquier hecho fáctico."""

    res = system_control.search_web(query)

    return res.get("results", str(res))



def get_boca_juniors_info(topic: str = "todo") -> str:

    """Consulta en tiempo real el fixture y próximo partido oficial confirmado de Boca Juniors (cuándo juega, fecha, hora, rival, estadio, torneo y alineación). Para resultados de partidos pasados, cómo salió Boca en un día específico (ej. ayer o el martes) o marcadores anteriores, usá search_web."""

    res = system_control.get_boca_juniors_info(topic)

    return res.get("results", str(res))



def play_youtube(query: str) -> str:

    """Busca y reproduce inmediatamente una canción, video o artista en YouTube en la computadora."""

    res = system_control.play_youtube(query)

    return res.get("message", str(res))



def play_spotify(query: str = "") -> str:

    """Busca y reproduce inmediatamente una canción, artista, álbum o playlist en Spotify en la computadora."""

    res = system_control.play_spotify(query)

    return res.get("message", str(res))



def get_current_song() -> str:

    """Obtiene el nombre de la canción o artista que está reproduciéndose actualmente en Spotify."""

    res = system_control.get_current_song()

    return res.get("message", str(res))



def empty_recycle_bin() -> str:

    """Vacía la papelera de reciclaje de Windows por completo."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("empty_recycle_bin")



def search_google(query: str) -> str:

    """Abre el navegador predeterminado y busca una consulta directamente en Google."""

    res = system_control.search_google(query)

    return res.get("message", str(res))



def open_web_service(service: str) -> str:

    """Abre un servicio web popular en el navegador como 'whatsapp', 'mercadolibre', 'gmail', 'reddit' o 'twitter'."""

    res = system_control.open_web_service(service)

    return res.get("message", str(res))



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

    import asyncio

    from integrations.telegram_bot import send_file_to_owner

    target_path = None

    if os.path.exists(query_or_path):

        target_path = query_or_path

    else:

        res = file_manager.search_files(query=query_or_path, max_results=1)

        if res.get("count", 0) > 0:

            target_path = res["files"][0]["path"]

    

    if not target_path or not os.path.exists(target_path):

        return f"No encontré ningún archivo que coincida con '{query_or_path}' para mandarte."

    

    try:

        filename = os.path.basename(target_path)

        try:

            loop = asyncio.get_running_loop()

            loop.create_task(send_file_to_owner(target_path, caption=f"📄 Acá tenés: {filename}"))

        except RuntimeError:

            asyncio.run(send_file_to_owner(target_path, caption=f"📄 Acá tenés: {filename}"))

        return f"¡Listo, papá! Te mandé el archivo '{filename}' directo a tu Telegram."

    except Exception as e:

        return f"Hubo un bardo al mandar el archivo a Telegram: {e}"



def analyze_screen(question: str = "Describí qué hay en la pantalla y qué error o información se muestra") -> str:
    """Saca una captura de pantalla y utiliza la visión de Gemini para responder preguntas sobre lo que el usuario está viendo en su monitor (leer errores, explicar imágenes, describir lo que hay en pantalla)."""
    from brain.gemini_client import brain
    import base64
    import asyncio
    from core.state_manager import state_mgr

    res = system_control.take_screenshot()
    if res.get("status") != "success":
        return res.get("message", "No pude capturar la pantalla para analizarla, che.")

    img_bytes = None
    if res.get("photo_base64"):
        try:
            img_bytes = base64.b64decode(res["photo_base64"])
        except Exception:
            pass
    elif res.get("path") and os.path.exists(res["path"]):
        try:
            with open(res["path"], "rb") as f:
                img_bytes = f.read()
        except Exception:
            pass

    if not img_bytes:
        return "No pude obtener la imagen de la pantalla de Windows para analizarla, che."

    loop = getattr(state_mgr, "_loop", None)
    if loop and loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(brain.analyze_screen(img_bytes, question=question), loop)
        try:
            return fut.result(timeout=15.0)
        except Exception as e:
            return f"Error analizando la pantalla: {e}"
    else:
        return asyncio.run(brain.analyze_screen(img_bytes, question=question))




def remember(key: str, value: str) -> str:

    """Guarda un recuerdo, dato personal o preferencia del usuario a largo plazo para nunca olvidarlo."""

    from core.memory import titan_memory

    return titan_memory.remember(key, value)



def recall(key: str) -> str:

    """Busca en la memoria a largo plazo lo que Titán recuerda sobre una palabra, tema o preferencia."""

    from core.memory import titan_memory

    return titan_memory.recall(key)



def list_memories() -> str:

    """Lista todos los recuerdos y preferencias guardadas en la memoria de Titán."""

    from core.memory import titan_memory

    return titan_memory.list_all_memories()



def add_note(text: str) -> str:

    """Anota una tarea, pendiente o recordatorio en la lista de notas personales."""

    from core.memory import titan_memory

    return titan_memory.add_note(text)



def get_notes() -> str:

    """Muestra todas las notas y recordatorios pendientes del usuario."""

    from core.memory import titan_memory

    return titan_memory.get_notes()



def delete_note(note_id_or_text: str) -> str:

    """Elimina una nota por su número de ID o texto coincidente."""

    from core.memory import titan_memory

    return titan_memory.delete_note(note_id_or_text)



def set_timer(minutes: float, label: str = "Temporizador") -> str:

    """Programa un temporizador o alarma en minutos que sonará en la PC y avisará por Telegram."""

    from core.scheduler import titan_scheduler

    return titan_scheduler.set_timer(minutes, label)



def cancel_timer(label: str) -> str:

    """Cancela un temporizador activo por su etiqueta o nombre."""

    from core.scheduler import titan_scheduler

    return titan_scheduler.cancel_timer(label)



def list_timers() -> str:

    """Lista los temporizadores que están corriendo en este momento."""

    from core.scheduler import titan_scheduler

    return titan_scheduler.list_timers()



def capture_j2_photo(facing: str = "") -> str:

    """Saca una foto en tiempo real usando la cámara del celular Samsung Galaxy J2 (que está vigilando la habitación o el escritorio) y la envía directo a Telegram."""

    import asyncio

    from tools.j2_camera import j2_camera

    from integrations.telegram_bot import send_photo_to_owner

    from core.state_manager import state_mgr



    target_facing = facing if facing in ["user", "environment"] else j2_camera.current_facing

    loop = getattr(state_mgr, "_loop", None)

    if not loop or not loop.is_running():

        return "No hay un bucle de eventos activo para comunicarse con el J2."



    try:

        fut = asyncio.run_coroutine_threadsafe(j2_camera.capture_photo(facing_mode=target_facing, timeout=8.0), loop)

        photo_bytes = fut.result(timeout=10.0)



        if not photo_bytes:

            return "No pude obtener la foto del Samsung J2. Fijate que la pantalla del celular esté encendida con el HUD abierto."



        label = j2_camera.get_facing_label()

        caption = f"📸 Foto en vivo desde el Samsung J2 ({label})"

        send_fut = asyncio.run_coroutine_threadsafe(send_photo_to_owner(photo_bytes, caption=caption), loop)

        send_fut.result(timeout=8.0)

        return f"¡Listo! Saqué la foto con la cámara {label} del J2 y te la acabo de mandar a tu Telegram."

    except Exception as e:

        return f"Hubo un error al capturar la foto con el J2: {e}"



def vigilance_check_j2() -> str:

    """Inspecciona y vigila la habitación o el escritorio a través de la cámara del Samsung Galaxy J2. Saca una foto, la analiza con Gemini Visión y envía el reporte detallado con la foto a Telegram."""

    import asyncio

    from tools.j2_camera import j2_camera

    from integrations.telegram_bot import send_photo_to_owner, send_voice_to_owner, send_message_to_owner

    from brain.gemini_client import brain

    from core.state_manager import state_mgr



    loop = getattr(state_mgr, "_loop", None)

    if not loop or not loop.is_running():

        return "No hay un bucle de eventos activo para comunicarse con el J2."



    try:

        fut = asyncio.run_coroutine_threadsafe(j2_camera.capture_photo(timeout=8.0), loop)

        photo_bytes = fut.result(timeout=10.0)



        if not photo_bytes:

            return "No pude acceder a la cámara del Samsung J2 para vigilar. Asegurate de que el HUD esté conectado en el celular."



        label = j2_camera.get_facing_label()

        caption = f"👁️ Vigilancia J2 ({label}): Analizando con IA..."

        asyncio.run_coroutine_threadsafe(send_photo_to_owner(photo_bytes, caption=caption), loop)



        question = (

            "Actuá como Titán vigilando la habitación o el escritorio del usuario a través de la cámara del Samsung J2. "

            "Decile qué ves exactamente: si hay personas, si hay movimiento, si la luz está prendida o apagada, "

            "o si está todo en orden y tranquilo. Respondé con tu tonada y personalidad argentina para ser reproducido por voz."

        )

        vision_fut = asyncio.run_coroutine_threadsafe(brain.analyze_vision(photo_bytes, question=question), loop)

        report = vision_fut.result(timeout=15.0)



        from audio.tts import tts

        voice_fut = asyncio.run_coroutine_threadsafe(tts.synthesize_to_bytes(report), loop)

        voice_bytes = voice_fut.result(timeout=10.0)

        if voice_bytes:

            asyncio.run_coroutine_threadsafe(send_voice_to_owner(voice_bytes, caption="🎙️ Reporte de vigilancia de Titán"), loop)

        else:

            asyncio.run_coroutine_threadsafe(send_message_to_owner(f"🛡️ *Reporte de Titán:*\n{report}"), loop)



        return f"Reporte de vigilancia de la pieza completado: {report}"

    except Exception as e:

        return f"Hubo un bardo al vigilar la pieza con el J2: {e}"



def toggle_j2_camera() -> str:

    """Alterna la cámara del Samsung Galaxy J2 entre la trasera (vigilar la habitación o la puerta) y la frontal (vigilar el escritorio o la silla)."""

    import asyncio

    from tools.j2_camera import j2_camera

    from server.websocket_hub import ws_hub

    from core.state_manager import state_mgr



    new_label = j2_camera.toggle_facing()

    loop = getattr(state_mgr, "_loop", None)

    if loop and loop.is_running():

        asyncio.run_coroutine_threadsafe(ws_hub.broadcast_event({"type": "flip_camera", "mode": j2_camera.current_facing}), loop)

    return f"Cambié la cámara del Samsung J2 a: {new_label}."


def toggle_presence_sensor(enabled: bool) -> str:
    """Activa o desactiva el sensor de presencia inteligente por cámara frontal del Samsung J2."""
    from tools.presence_detector import presence_detector
    if enabled:
        return presence_detector.enable()
    else:
        return presence_detector.disable()

def get_presence_sensor_status() -> str:
    """Consulta el estado del sensor de presencia frontal del Samsung J2 (si está activo, tiempo de inactividad y si detecta al usuario)."""
    from tools.presence_detector import presence_detector
    st = presence_detector.get_status()
    if not st.get("enabled"):
        return "El sensor de presencia frontal está desactivado."
    inact = st.get("inactivity_seconds", 0) // 60
    if st.get("in_cooldown"):
        rem = st.get("cooldown_remaining_seconds", 0) // 60
        return f"El sensor de presencia está activo y en cooldown anti-spam. Restan {rem} minutos."
    if st.get("is_absent"):
        return f"El sensor detecta que el usuario está ausente desde hace {inact} minutos. Al regresar será bienvenido."
    return "El sensor está activo y el usuario se encuentra actualmente presente frente al escritorio."






def vigilance_full_check() -> str:
    """Ejecuta una inspección completa de seguridad y vigilancia: captura foto de la habitación con el Samsung J2, captura la pantalla de Windows y analiza el estado de bloqueo e inactividad."""
    import asyncio
    from tools.surveillance_service import surveillance_service
    from core.state_manager import state_mgr

    loop = getattr(state_mgr, "_loop", None)
    if not loop or not loop.is_running():
        return "El bucle de eventos del asistente no está activo para ejecutar la vigilancia."

    fut = asyncio.run_coroutine_threadsafe(surveillance_service.get_full_security_report(), loop)
    try:
        rep = fut.result(timeout=20.0)
        return rep.get("summary_spoken", "Reporte de seguridad completado.")
    except Exception as e:
        return f"Error ejecutando vigilancia completa: {e}"

def toggle_sentry_mode(enabled: bool) -> str:
    """Activa o desactiva el Modo Centinela para alertas automáticas de intrusión a Telegram."""
    from tools.surveillance_service import surveillance_service
    if enabled:
        return surveillance_service.enable_sentry()
    else:
        return surveillance_service.disable_sentry()

# --- CONTROL DE BRILLO Y PANTALLA ---

def get_brightness() -> str:

    """Consulta el nivel actual de brillo del monitor principal (en porcentaje de 0 a 100)."""

    res = system_control.get_brightness()

    return res.get("message", str(res))



def set_brightness(level: int) -> str:

    """Ajusta el nivel de brillo de la pantalla del monitor a un porcentaje específico entre 0 y 100."""

    res = system_control.set_brightness(level)

    return res.get("message", str(res))



def brightness_up(step: int = 10) -> str:

    """Sube el brillo del monitor principal en un paso o incremento (por defecto 10%)."""

    res = system_control.brightness_up(step)

    return res.get("message", str(res))



def brightness_down(step: int = 10) -> str:

    """Baja el brillo del monitor principal en un paso o decremento (por defecto 10%)."""

    res = system_control.brightness_down(step)

    return res.get("message", str(res))



def toggle_night_light() -> str:

    """Abre la configuración de Luz Nocturna (Night Light) de Windows para descansar la vista."""

    res = system_control.toggle_night_light()

    return res.get("message", str(res))



# --- CONTROL DE PROCESOS / DOCTOR PC ---

def get_top_processes(sort_by: str = "ram", limit: int = 5) -> str:

    """Lista los programas o procesos que más memoria RAM o CPU están consumiendo en la computadora."""

    res = system_control.get_top_processes(sort_by=sort_by, limit=limit)

    if res.get("status") == "success" and "processes" in res:

        lines = [f"Top {len(res['processes'])} procesos por {sort_by.upper()}:"]

        for p in res["processes"]:

            lines.append(f"- {p['name']} (PID {p['pid']}): {p['ram_mb']} MB RAM | {p['cpu_percent']}% CPU")

        return "\n".join(lines)

    return res.get("message", str(res))



def kill_process(name_or_pid: str) -> str:

    """Cierra o finaliza un proceso rebelde o aplicación colgada por su nombre (ej: 'discord', 'chrome.exe') o PID numérico."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("kill_process", name_or_pid=name_or_pid)



def optimize_pc_gaming() -> str:

    """Modo Gamer / Optimización de PC: Cierra aplicaciones secundarias no esenciales en segundo plano para liberar RAM y CPU."""

    res = system_control.optimize_pc_gaming()

    return res.get("message", str(res))



# --- RED Y CONECTIVIDAD ---

def test_network_ping(host: str = "8.8.8.8") -> str:

    """Prueba la latencia y calidad de conexión a internet haciendo ping a un servidor (por defecto Google DNS)."""

    res = system_control.test_network_ping(host)

    return res.get("message", str(res))



def flush_dns() -> str:

    """Limpia y purga la caché DNS de Windows para solucionar problemas de navegación o páginas que no cargan."""

    res = system_control.flush_dns()

    return res.get("message", str(res))



def get_network_info() -> str:

    """Obtiene información sobre la red local, nombre de la máquina y dirección IP de la computadora."""

    res = system_control.get_network_info()

    return res.get("message", str(res))



# --- CREACIÓN Y GESTIÓN DE ARCHIVOS ---

def create_file(filename: str, content: str = "", folder: str = "Desktop") -> str:

    """Crea un archivo nuevo con el contenido indicado en el Escritorio o Descargas."""

    res = file_manager.create_file(filename=filename, content=content, folder=folder)

    return res.get("message", str(res))



def append_to_file(filename: str, content: str) -> str:

    """Agrega texto al final de un archivo existente en el Escritorio o Documentos."""

    res = file_manager.append_to_file(filename=filename, content=content)

    return res.get("message", str(res))



def extract_zip(zip_name_or_path: str, destination: str = "") -> str:

    """Descomprime un archivo .zip en una carpeta con el mismo nombre o la carpeta indicada."""

    res = file_manager.extract_zip(zip_name_or_path=zip_name_or_path, destination=destination)

    return res.get("message", str(res))



def organize_folder(folder_name: str = "Downloads") -> str:

    """Organiza automáticamente una carpeta (por defecto Descargas o Escritorio), clasificando archivos en subcarpetas por tipo."""

    res = file_manager.organize_folder(folder_name=folder_name)

    return res.get("message", str(res))



# --- PORTAPAPELES Y VISIÓN CON IA ---
def summarize_clipboard(max_sentences: int = 3) -> str:
    """Lee el texto copiado en el portapapeles de Windows, extrae las ideas principales con Gemini y devuelve un resumen claro por voz y texto."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para resumir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para resumir el texto copiado."

    try:
        prompt = (
            f"Actuá como Titán, asistente compinche argentino. Resumí el siguiente texto copiado del portapapeles "
            f"extrayendo los puntos clave en un máximo de {max_sentences} oraciones directas, claras y fáciles de escuchar:\n\n{text}"
        )
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    summary = resp.text.strip()
                    return f"Te resumo lo que tenés copiado:\n{summary}"
            except Exception:
                continue
        return "No pude generar el resumen del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al resumir el portapapeles: {e}"

def explain_clipboard() -> str:
    """Lee el código, mensaje de error, comando o texto técnico copiado en el portapapeles de Windows y lo explica de forma didáctica en español argentino."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para explicar, che."
    if not brain.client:
        return "No tengo conexión con Gemini para explicar lo que copiaste."

    try:
        prompt = (
            f"Actuá como Titán, asistente compinche argentino y programador experto. "
            f"Explicá qué hace, qué significa o cómo solucionar el siguiente contenido copiado en el portapapeles "
            f"(puede ser código fuente, una traza de error de terminal, un comando o un fragmento técnico). "
            f"Sé didáctico, conciso y directo, sin vueltas innecesarias:\n\n{text}"
        )
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    explanation = resp.text.strip()
                    return f"Mirá, esto es lo que tenés copiado:\n{explanation}"
            except Exception:
                continue
        return "No pude analizar ni explicar el contenido del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al explicar el portapapeles: {e}"

def translate_clipboard(target_language: str = "español") -> str:
    """Lee el texto actual copiado en el portapapeles de Windows, lo traduce al idioma especificado con Gemini y copia el resultado al portapapeles."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para traducir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para traducir el texto."

    try:
        prompt = f"Traducí el siguiente texto al idioma {target_language}. Devolvé ÚNICAMENTE el texto traducido sin notas ni explicaciones:\n\n{text}"
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    translated = resp.text.strip()
                    system_control.set_clipboard(translated)
                    return f"¡Listo! Traduje el texto al {target_language} y te lo dejé copiado en el portapapeles listo para pegar:\n'{translated[:140]}...'"
            except Exception:
                continue
        return "No pude traducir el texto del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al traducir el portapapeles: {e}"

def rewrite_clipboard(style: str = "profesional") -> str:
    """Reescribe y corrige la ortografía y redacción del texto copiado en el portapapeles con el estilo solicitado (profesional, casual, formal, etc.) y lo vuelve a copiar al portapapeles."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para mejorar o reescribir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para reescribir el texto."

    try:
        prompt = f"Reescribí y mejorá la redacción del siguiente texto con un estilo {style} (corrigiendo faltas de ortografía, puntuación y mejorando el tono). Devolvé ÚNICAMENTE el texto reescrito sin saludos ni explicaciones:\n\n{text}"
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    rewritten = resp.text.strip()
                    system_control.set_clipboard(rewritten)
                    return f"¡De diez! Reescribí el texto con estilo {style} y ya lo tenés copiado en el portapapeles:\n'{rewritten[:140]}...'"
            except Exception:
                continue
        return "No pude reescribir el texto del portapapeles."
    except Exception as e:
        return f"Hubo un error al reescribir el portapapeles: {e}"

def extract_text_from_screen() -> str:

    """Saca una captura de la pantalla actual, extrae todo el texto visible usando OCR inteligente con Gemini Visión y copia el texto extraído al portapapeles de Windows."""

    from brain.gemini_client import brain

    from google.genai import types



    res = system_control.take_screenshot()

    if res.get("status") != "success" or not res.get("path"):

        return res.get("message", "No pude capturar la pantalla para extraer texto, che.")



    path = res["path"]

    try:

        with open(path, "rb") as f:

            img_bytes = f.read()



        if not brain.client:

            return "No está inicializado el cliente de Gemini para visión."



        image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")

        prompt = "Extraé y transcribí todo el texto visible en esta captura de pantalla (OCR inteligente). Mantené el orden, estructura y formato. Si hay código, tablas o párrafos, transcribilos con fidelidad. Devolvé únicamente el texto extraído sin introducciones."



        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

        for cand in models_to_try:

            try:

                resp = brain.client.models.generate_content(model=cand, contents=[image_part, prompt])

                if resp and resp.text:

                    extracted = resp.text.strip()

                    system_control.set_clipboard(extracted)

                    return f"¡Listo, papá! Extraje el texto de la pantalla y te lo copié en el portapapeles:\n'{extracted[:150]}...'"

            except Exception:

                continue

        return "No logré extraer texto legible de la pantalla."

    except Exception as e:

        return f"Error extrayendo texto de la pantalla: {e}"

# ---------------------------------------------------------
# HERRAMIENTAS PARA TELEVISOR BGH ANDROID TV (192.168.100.8)
# ---------------------------------------------------------
from tools.tv_control import tv_control

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
    res = tv_control.volume_up(steps)
    return res.get("message", "Volumen de la tele subido.")

def tv_volume_down(steps: int = 2) -> str:
    """Baja el volumen de la tele BGH Android TV."""
    res = tv_control.volume_down(steps)
    return res.get("message", "Volumen de la tele bajado.")

def tv_mute() -> str:
    """Mutea o desmutea el volumen de la tele BGH Android TV."""
    res = tv_control.mute()
    return res.get("message", "Muteé la tele.")

def tv_set_volume(level: int) -> str:
    """Ajusta el volumen de la tele BGH Android TV a un nivel específico de 0 a 100."""
    res = tv_control.set_volume(level)
    return res.get("message", f"Volumen de la tele puesto en {level}.")

def tv_play_pause() -> str:
    """Alterna Play / Pausa en la reproducción de la tele BGH Android TV (YouTube, Netflix, OnPlay, etc.)."""
    res = tv_control.play_pause()
    return res.get("message", "Play/Pausa en la tele.")

def tv_open_app(app_name: str) -> str:
    """Abre una aplicación en la tele BGH Android TV por su nombre (ej: 'onplay', 'youtube', 'netflix', 'vlc', 'spotify')."""
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


# Lista de funciones para registrar en Gemini

AVAILABLE_TOOLS: List[Callable] = [

    launch_app,

    register_portable_app,

    search_files,

    open_file,

    show_in_folder,

    trash_file,

    move_file,

    copy_file,

    read_file_content,

    create_file,

    append_to_file,

    extract_zip,

    organize_folder,

    set_volume,

    volume_up,

    volume_down,

    mute,

    media_play_pause,

    media_next,

    media_prev,

    get_brightness,

    set_brightness,

    brightness_up,

    brightness_down,

    toggle_night_light,

    lock_workstation,

    minimize_all,

    take_screenshot,

    get_system_metrics,

    cool_down_pc,

    set_power_plan,

    get_top_processes,

    kill_process,

    optimize_pc_gaming,

    test_network_ping,

    flush_dns,

    get_network_info,

    switch_screen_view,

    set_avatar_stage,

    flip_camera,

    set_assistant_name,

    get_weather,

    get_soccer_info,

    search_web,

    get_boca_juniors_info,

    play_youtube,

    play_spotify,

    get_current_song,

    empty_recycle_bin,

    search_google,

    open_web_service,

    shutdown_pc,

    restart_pc,

    sleep_pc,

    wake_windows_pc,

    get_clipboard,

    set_clipboard,

    summarize_clipboard,
    explain_clipboard,
    translate_clipboard,

    rewrite_clipboard,

    extract_text_from_screen,

    send_file_to_telegram,

    analyze_screen,

    remember,

    recall,

    list_memories,

    add_note,

    get_notes,

    delete_note,

    set_timer,

    cancel_timer,

    list_timers,

    capture_j2_photo,

    vigilance_check_j2,

    toggle_j2_camera,
    toggle_presence_sensor,
    get_presence_sensor_status,
    toggle_sentry_mode,
    # Herramientas de tele BGH Android TV
    tv_turn_on,
    tv_turn_off,
    tv_power_toggle,
    tv_volume_up,
    tv_volume_down,
    tv_mute,
    tv_set_volume,
    tv_play_pause,
    tv_open_app,
    tv_open_onplay,
    tv_tune_channel,
    tv_list_channels,
    tv_send_key,
    tv_type_text,
    tv_get_status
]



# Diccionario mapeado por nombre para despacho rápido

TOOLS_MAP: Dict[str, Callable] = {fn.__name__: fn for fn in AVAILABLE_TOOLS}



