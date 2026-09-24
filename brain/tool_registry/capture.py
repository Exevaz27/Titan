"""Herramientas de captura y vigilancia: pantalla, J2, brillo, procesos, red."""

from core.config import config

import os

from tools.system_control import system_control

from ._common import _clamp



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

    level = _clamp(level, 0, 100, 50)  # R-3
    res = system_control.set_brightness(level)

    return res.get("message", str(res))


def brightness_up(step: int = 10) -> str:

    """Sube el brillo del monitor principal en un paso o incremento (por defecto 10%)."""

    step = _clamp(step, 1, 50, 10)  # R-3
    res = system_control.brightness_up(step)

    return res.get("message", str(res))


def brightness_down(step: int = 10) -> str:

    """Baja el brillo del monitor principal en un paso o decremento (por defecto 10%)."""

    step = _clamp(step, 1, 50, 10)  # R-3
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

    from brain.local_intents import local_intents
    # S-6: cierra procesos -> pide confirmación.
    return local_intents.request_confirmation("optimize_pc_gaming")





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
