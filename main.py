import asyncio
import signal
import sys
from typing import Optional
import uvicorn
from pathlib import Path

from core.config import config
from core.logger import log_info, log_success, log_warning, log_error
from core.state_manager import state_mgr, AssistantState
from audio.listener import listener
from audio.tts import tts
from brain.gemini_client import brain
from tools.hotkey_listener import hotkey_listener
from server.web_server import app as web_app, set_command_processor

BANNER = """
====================================================================
   🇦🇷  CHE ASISTENTE // ASISTENTE DE VOZ PARA WINDOWS  🇦🇷
   Personalidad: Amigo de fierro (Tonada bien argenta)
   Motor IA: Google Gemini API | Voz: Microsoft Edge-TTS (es-AR)
====================================================================
"""

command_lock = asyncio.Lock()
active_server: Optional[uvicorn.Server] = None

def shutdown_server():
    """Detiene limpiamente el servidor y todos los servicios de Titán"""
    global active_server
    if active_server:
        active_server.should_exit = True

async def handle_user_command(command_text: str):
    """Bucle principal de procesamiento de una orden recibida"""
    if not command_text or not command_text.strip():
        return

    clean_cmd = command_text.strip().lower()

    # 0. FILTRO ANTI-ECO GLOBAL: si coincide con lo que Titán acaba de decir por los altavoces, descartar
    from audio.tts import tts
    if tts.is_self_echo(command_text):
        log_info(f"[Anti-Eco Global] Comando descartado por ser eco de los altavoces: '{command_text}'")
        return

    # Registrar actividad para el sensor de presencia (usuario activo en escritorio)
    from tools.presence_detector import presence_detector
    presence_detector.record_user_activity()

    # 1. Evitar duplicados si ambos micrófonos (PC y Celular) captaron la misma orden al unísono
    import time
    now = time.time()
    if hasattr(handle_user_command, "_last_cmd") and hasattr(handle_user_command, "_last_time"):
        if handle_user_command._last_cmd == clean_cmd and (now - handle_user_command._last_time) < 2.5:
            return
    handle_user_command._last_cmd = clean_cmd
    handle_user_command._last_time = now

    # 2. Si el usuario dice una frase compuesta explícita de silencio (ej: "pará titán", "callate titán", "silencio titán", etc.)
    from audio.wake_word import check_barge_in_phrase
    is_stop_phrase, matched_stop = check_barge_in_phrase(clean_cmd)
    if is_stop_phrase:
        stop_keywords = ["pará", "para", "callate", "cállate", "silencio", "basta", "frená", "frena", "esperá", "espera", "bancá", "banca"]
        if any(kw in matched_stop for kw in stop_keywords):
            tts.stop()
            state_mgr.set_state(AssistantState.LISTENING, "Te escucho...")
            return

    log_info(f"Procesando comando: '{command_text}'")
    listener.is_waiting_for_command = False
    from audio.stream_listener import stream_listener
    stream_listener.is_waiting_for_command = False

    # 3. Si el usuario SOLO dijo el nombre o palabra de activación (ej: "Titán", "Cuautitlán", "Palermo", "un titán")
    from audio.wake_word import wake_detector
    is_wake, remainder = wake_detector.check(command_text)
    is_pure_invocation = (is_wake and not remainder) or (clean_cmd in {"un", "el", "la", "ah", "eh", "eu", "ey", "a ver", "che", "hola"}) or (len(clean_cmd) <= 2)
    if is_pure_invocation:
        mode = getattr(brain, "current_mode", "normal")
        if mode == "rebel":
            await tts.speak("¡¿Qué carajo querés ahora, pesado?!", auto_listen=True)
            return
        elif mode == "kids":
            await tts.speak("¡¿Qué querés, remolón?! ¡No ves que estoy ocupado!", auto_listen=True)
            return
        import random
        greetings = [
            "¿Qué hacés, papá? Te escucho.",
            "Acá estoy, hermano. Decime.",
            "Decime, fiera, ¿qué necesitás?",
            "Al pie del cañón, compinche. Decime."
        ]
        await tts.speak(random.choice(greetings), auto_listen=True)
        return

    # 3.5. Comandos directos de visión y análisis de la pantalla de la PC
    norm_cmd = command_text.lower()
    is_screen_cmd = any(p in norm_cmd for p in [
        "mira la pantalla", "mirá la pantalla", "mirar la pantalla", "mira mi pantalla", "mirá mi pantalla",
        "mira lo que tengo en pantalla", "mirá lo que tengo en pantalla", "fijate la pantalla", "fijate en la pantalla",
        "fijate lo que tengo en pantalla", "que hay en la pantalla", "qué hay en la pantalla", "que ves en la pantalla",
        "qué ves en la pantalla", "analiza la pantalla", "analizá la pantalla", "mira el monitor", "mirá el monitor",
        "mira este error", "mirá este error", "que error es este", "qué error es este", "fijate este error",
        "fijate que paso en la compu", "fijate qué pasó en la compu", "mira la compu", "mirá la compu",
        "mira lo que me salio", "mirá lo que me salió", "que dice la pantalla", "qué dice la pantalla",
        "lee la pantalla", "leé la pantalla", "leeme la pantalla", "leéme la pantalla"
    ])
    if is_screen_cmd:
        state_mgr.add_user_message(command_text)
        state_mgr.set_state(AssistantState.PROCESSING, "Mirando la pantalla de tu compu...")
        from server.websocket_hub import ws_hub
        if not ws_hub.has_windows_satellite():
            await tts.speak("Che papá, no detecto la compu conectada para mirar la pantalla. Asegurate de tener el satélite de Titán abierto en Windows.", auto_listen=False)
            return

        try:
            res = await ws_hub.call_remote("take_screenshot", {}, timeout=10.0)
            b64 = res.get("photo_base64")
            if not b64:
                await tts.speak("Che papá, parece que la pantalla está bloqueada o apagada. Desbloqueá la compu para que pueda ver.", auto_listen=False)
                return

            import base64
            img_bytes = base64.b64decode(b64)
            analysis = await brain.analyze_screen(img_bytes, question=command_text)
            await tts.speak(analysis, auto_listen=True)
            return
        except Exception as e:
            log_error(f"Error analizando pantalla por voz: {e}")
            await tts.speak("Se me complicó mirar la pantalla en este momento, fiera. Probá de nuevo en un toque.", auto_listen=False)
            return

    # 3.7. Comandos de creación o edición de imágenes con IA por voz
    image_triggers = [
        "creame una imagen de", "creá una imagen de", "crea una imagen de",
        "creame una imagen", "creá una imagen", "crea una imagen",
        "haceme una imagen de", "hacé una imagen de", "hace una imagen de",
        "haceme una imagen", "hacé una imagen", "hace una imagen",
        "generame una imagen de", "generá una imagen de", "genera una imagen de",
        "generame una imagen", "generá una imagen", "genera una imagen",
        "dibujame una imagen de", "dibujá una imagen de", "dibuja una imagen de",
        "dibujame un", "dibujame una", "dibujame el", "dibujame la", "dibujame",
        "dibujá un", "dibujá una", "dibujá el", "dibujá la", "dibujá",
        "dibuja un", "dibuja una", "dibuja el", "dibuja la", "dibuja"
    ]
    is_image_cmd = any(norm_cmd.startswith(pfx) or f" {pfx} " in f" {norm_cmd} " for pfx in image_triggers)
    if is_image_cmd:
        prompt_text = ""
        for pfx in image_triggers:
            if pfx in norm_cmd:
                idx = norm_cmd.find(pfx)
                prompt_text = command_text[idx + len(pfx):].strip()
                break

        if not prompt_text:
            await tts.speak("¿Qué querés que te dibuje, papá? Decime y te creo la imagen al toque.", auto_listen=True)
            return

        state_mgr.add_user_message(command_text)
        state_mgr.set_state(AssistantState.PROCESSING, "Creando imagen con IA...")

        from server.websocket_hub import ws_hub
        from tools.image_generator import image_generator

        # Avisar al HUD para que muestre la tarjeta de carga
        await ws_hub.broadcast_event({"type": "image_generating", "prompt": prompt_text})

        # Filler hablado en los parlantes de la DDR3
        filler_task = asyncio.create_task(
            tts.speak("¡De una, fiera! Ya te la empiezo a crear en máxima calidad con FLUX, bancame unos segundos...", auto_listen=False)
        )

        res = await image_generator.generate(prompt_text)
        try:
            await filler_task
        except Exception:
            pass

        if res.get("status") == "success":
            await ws_hub.broadcast_event({
                "type": "image_generated",
                "url": res["url"],
                "filename": res["filename"],
                "prompt": res["prompt"],
                "enriched_prompt": res.get("enriched_prompt", ""),
                "timestamp": time.strftime("%H:%M")
            })
            await tts.speak("¡Listo, papá! Ahí te generé la imagen en alta definición, mirala en la pantalla de Control.", auto_listen=False)
            state_mgr.set_state(AssistantState.IDLE, "Imagen lista en Control")
        else:
            await tts.speak("Uh, che, se me complicó generar la imagen. Probá de nuevo en un ratito.", auto_listen=False)
            state_mgr.set_state(AssistantState.IDLE, "En reposo")
        return

    # 4. Probar intención local instantánea (Offline / Zero-Latency):
    from brain.local_intents import local_intents
    handled, local_reply = local_intents.try_handle(command_text)
    if handled and local_reply:
        state_mgr.add_user_message(command_text)
        is_rest = any(w in command_text.lower() for w in ["mate", "descans", "dormi", "mimir", "siesta", "pausa", "amargo"])
        await tts.speak(local_reply, auto_listen=(not is_rest))
        return

    # 5. Detectar despedidas para salir de la conversación y volver a reposo
    goodbye_words = ["chau", "chao", "adios", "hasta luego", "nos vemos", "listo gracias", "nada mas", "nada más", "gracias titan", "gracias che"]
    if any(clean_cmd == gw or clean_cmd.startswith("chau") or clean_cmd.startswith("chao") for gw in goodbye_words):
        state_mgr.add_user_message(command_text)
        mode = getattr(brain, "current_mode", "normal")
        if mode == "rebel":
            import random
            rebel_byes = [
                "¡Tomátelas de acá, forro! Ni vuelvas.",
                "¡Al fin te vas, pesado de mierda! No vuelvas a joder.",
                "Chau y andate bien a la mierda, a ver si me dejás en paz un rato."
            ]
            await tts.speak(random.choice(rebel_byes), auto_listen=False)
        elif mode == "kids":
            import random
            kids_byes = [
                "¡Al fin te vas a tomar la chocolatada! ¡Chau, salame!",
                "¡Tomátelas, y andá a hacer la tarea de matemática!",
                "¡Chau pichón, no me molestes más hasta mañana!"
            ]
            await tts.speak(random.choice(kids_byes), auto_listen=False)
        else:
            await tts.speak("¡Nos vemos, papá! Acá estoy si me precisás.", auto_listen=False)
        return

    # Interrumpir habla previa si existía y consultar a Gemini en streaming directo:
    try:
        if tts._is_speaking:
            tts.stop()
    except Exception:
        pass

    async with command_lock:
        stream_gen = brain.process_user_input_stream(command_text)
        await tts.speak_stream(stream_gen, auto_listen=True)

async def main():
    print(BANNER)
    loop = asyncio.get_running_loop()
    state_mgr.set_loop(loop)

    # 1. Conectar procesador de comandos al servidor web
    set_command_processor(handle_user_command)

    # 2. Conectar listener de voz y modo conversacional
    listener.register_command_handler(handle_user_command)
    from audio.stream_listener import stream_listener
    stream_listener.set_command_callback(handle_user_command, loop)

    def on_tts_finished():
        from audio.speaker_monitor import speaker_monitor
        if speaker_monitor.is_media_active():
            speaker_monitor.unduck()
            state_mgr.set_state(AssistantState.IDLE, "Música sonando (decí 'Titán' para ordenar)")
            return

        # Si Titán está tomando mates o durmiendo, no forzar modo escucha conversacional
        if state_mgr.inactivity_stage in ["mate", "drowsy", "sleeping"]:
            state_mgr.set_state(AssistantState.IDLE, "En reposo")
            return

        stream_listener.enter_conversational_turn(timeout=10.0)
        listener.enter_conversational_turn(timeout=10.0)
    tts.on_speech_finished = on_tts_finished

    # 3. Iniciar listener de atajos de teclado globales (Ctrl+Espacio / Alt+A)
    hotkey_listener.start(on_trigger_callback=listener.trigger_manual_listen)

    # 4. Iniciar escucha de audio (micrófono en segundo plano)
    listener.start(loop)

    # 4b. Iniciar bot oficial de Telegram si hay token configurado
    if config.telegram_bot_token:
        from integrations.telegram_bot import telegram_service
        asyncio.create_task(telegram_service.start())

    # 4c. Iniciar detector de presencia por cámara frontal (Samsung J2)
    from tools.presence_detector import presence_detector
    presence_detector.start(loop)

    # 5. Configurar e iniciar servidor web FastAPI (Uvicorn)
    server_config = uvicorn.Config(
        app=web_app,
        host=config.server_host,
        port=config.server_port,
        log_level="warning",
        loop="asyncio"
    )
    global active_server
    server = uvicorn.Server(server_config)
    active_server = server

    import socket
    def _get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    local_ip = _get_local_ip()
    log_success(f"Servidor HUD en tu PC:       http://127.0.0.1:{config.server_port}")
    log_success(f"Servidor HUD en tu CELULAR:  http://{local_ip}:{config.server_port}")
    if config.telegram_bot_token:
        log_success("Bot de Telegram vinculado:   https://t.me/AsistenteTitanBot")
    log_info("Conectá tu celular al mismo Wi-Fi de tu casa y abrí esa dirección.")
    log_info(f"Atajo de teclado global: [{config.hotkey.upper()}] para activar escucha instantánea.")
    log_info(f"Palabras clave de activación por voz: {', '.join(config.wake_words)}")
    log_success("¡Todo listo, máquina! El asistente está esperando tus órdenes.")

    # Mensaje inicial de bienvenida por voz (opcional)
    # asyncio.create_task(tts.speak("¡Buenas, papá! Che Asistente activo. ¿En qué te doy una mano?"))

    try:
        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        log_info("Cerrando módulos del asistente...")
        try:
            from tools.presence_detector import presence_detector
            presence_detector.stop()
        except Exception:
            pass
        if config.telegram_bot_token:
            from integrations.telegram_bot import telegram_service
            await telegram_service.stop()
        hotkey_listener.stop()
        listener.stop()
        tts.stop()
        log_success("Asistente detenido limpiamente.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSaliendo...")
        sys.exit(0)
