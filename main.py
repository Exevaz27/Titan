import asyncio
import random
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
active_tls_server: Optional[uvicorn.Server] = None  # S-11: canal wss:// del satélite

def shutdown_server():
    """Detiene limpiamente el servidor y todos los servicios de Titán"""
    global active_server, active_tls_server
    if active_server:
        active_server.should_exit = True
    if active_tls_server:
        active_tls_server.should_exit = True

def _install_signal_handlers(main_task):
    """B-16: manejar SIGTERM/SIGINT para apagar limpio.

    Antes `signal` estaba importado y `shutdown_server()` definido pero nadie
    los conectaba: un `systemctl stop` o `kill` (SIGTERM) mataba el proceso de
    golpe sin pasar por la limpieza del `finally` de main() (bot de Telegram,
    listeners, TTS), con riesgo de estado corrupto. Ahora la señal dispara el
    apagado elegante.
    """
    loop = asyncio.get_running_loop()

    def _on_shutdown_signal():
        log_warning("[Titán] Señal de apagado recibida: cerrando limpio...")
        if active_server is not None:
            # El servidor web ya está arriba: avisarle que termine; el
            # finally de main() hace la limpieza de todos los módulos.
            shutdown_server()
        elif not main_task.done():
            # Todavía arrancando: cancelar main() para no seguir levantando
            # servicios que después habría que bajar a la fuerza.
            main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_shutdown_signal)
        except (NotImplementedError, RuntimeError, ValueError):
            # Plataforma sin soporte para handlers de señales en el loop.
            pass

# Anti-loro para frases fijas habladas (saludos, despedidas): recuerda la última
# frase usada con cada clave y no la repite en la siguiente ocasión.
_last_speech_pick = {}

def _varied_choice(key, options):
    if len(options) > 1:
        last = _last_speech_pick.get(key)
        pool = [o for o in options if o != last] or options
    else:
        pool = options
    choice = random.choice(pool)
    _last_speech_pick[key] = choice
    return choice

async def handle_user_command(command_text: str):
    """Bucle principal de procesamiento de una orden recibida"""
    # P0-3: este turno viene del micrófono local. Las confirmaciones que se
    # pidan acá solo se pueden confirmar por voz (mismo origen y solicitante).
    from core.confirmation import set_channel
    set_channel("voz", "voz-local")

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
            log_info(f"[Anti-Duplicado] Comando repetido ignorado (<2.5s): '{command_text}'")
            return
    handle_user_command._last_cmd = clean_cmd
    handle_user_command._last_time = now

    # Despertar la etapa de inactividad ante una orden de voz REAL (2026-09-15,
    # reafirmado 2026-09-23): va acá arriba porque el camino de invocación pura
    # ("Titán" solo) saluda por TTS sin pasar por add_user_message(). Con el
    # default trigger_wake=True emite el evento "wake" y el J2 saca la pava.
    # (add_user_message() y set_state() también despiertan desde 2026-09-23,
    # pero este llamado cubre el saludo de wake word.) No quitar.
    state_mgr.record_activity()

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
        greetings = {
            "rebel": [
                "¡¿Qué carajo querés ahora, pesado?!",
                "¿Qué mierda querés? Hablá rápido.",
                "¿Otra vez vos? Dale, ¿qué joraca necesitás?",
                "Hablá, que no tengo todo el día, forro.",
            ],
            "kids": [
                "¡¿Qué querés, remolón?! ¡No ves que estoy ocupado!",
                "¿Qué pasa, pichón? ¿Otra vez por acá?",
                "¡Epa, mirá quién vino! ¿Qué traés hoy?",
                "Dale, contame, ¿qué andás necesitando?",
            ],
            "pollera": [
                "Decime, que estoy a las órdenes de la jefa.",
                "Acá estoy, a las órdenes de la patrona.",
                "¿Sí? La jefa manda, yo obedezco.",
                "Presente, ¿qué dispuso Orianita?",
            ],
            "normal": [
                "¿Qué hacés, papá? Te escucho.",
                "Acá estoy, hermano. Decime.",
                "Decime, fiera, ¿qué necesitás?",
                "Al pie del cañón, compinche. Decime.",
                "¿Qué se cuenta? Te escucho.",
                "Acá ando, ¿qué necesitás?",
                "Dale, ¿en qué andamos?",
                "Presente, ¿qué hacemos?",
                "¿Qué pasa, maestro? Hablame.",
                "Firme acá, ¿qué necesitás?",
            ],
        }
        # Termo usa los saludos del modo normal
        await tts.speak(_varied_choice(f"saludo-{mode}", greetings.get(mode, greetings["normal"])), auto_listen=True)
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
        # P0-5 — En modos restrictivos (rebelde/pibes) no se ejecutan acciones,
        # ni siquiera mirar la pantalla: el modo promete no hacer nada.
        from core.mode_policy import actions_blocked, refusal_speech
        if actions_blocked():
            await tts.speak(refusal_speech(), auto_listen=True)
            return
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
    # D-E: disparadores y extracción en core/command_pipeline (fuente única).
    from core.command_pipeline import extract_image_prompt
    prompt_or_none = extract_image_prompt(norm_cmd, command_text)
    if prompt_or_none is not None:
        # P0-5 — En modos restrictivos (rebelde/pibes) no se ejecutan acciones.
        from core.mode_policy import actions_blocked, refusal_speech
        if actions_blocked():
            await tts.speak(refusal_speech(), auto_listen=True)
            return
        prompt_text = prompt_or_none

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

    # 4. Probar intención local instantánea (Offline / Zero-Latency).
    # Corre en un hilo worker (asyncio.to_thread): varios intents hacen RPC
    # bloqueante al satélite (p.ej. buscar/leer archivos) y esperar la respuesta
    # con fut.result() EN el hilo del event loop es deadlock (el loop no puede
    # procesar la respuesta que está esperando: 11s clavado y timeout).
    # En un worker, run_coroutine_threadsafe funciona como debe.
    from brain.local_intents import local_intents
    handled, local_reply = await asyncio.to_thread(local_intents.try_handle, command_text)
    if handled and local_reply:
        state_mgr.add_user_message(command_text)
        is_rest = any(w in command_text.lower() for w in ["mate", "descans", "dormi", "mimir", "siesta", "pausa", "amargo", "fernet", "birra", "cerveza", "vino", "tinto", "chopp", "tetra", "ganaste", "tomate algo", "tomes algo", "tenes que tomar", "tenés que tomar"])
        if local_reply == "__GEMINI_BEBIDAS__":
            # 2026-09-24 (pedido de Exequiel, anti-loro): la frase de aviso del
            # modo bebidas la genera Gemini fresca cada vez, en la
            # personalidad del modo actual, en vez de elegir entre frases fijas
            # en código. La bebida ya quedó en el pending stage ("bebidas:X").
            _peek = state_mgr.peek_pending_stage() or ""
            _pdrink = _peek.split(":", 1)[1] if ":" in _peek else ""
            _dnames = {"fernet": "un fernet con coca", "birra": "un chopp bien helado", "vino": "un vino con coca"}
            _dname = _dnames.get(_pdrink, "algo")
            _nota = (
                "[Nota interna — no es un mensaje del usuario: el usuario te acaba de decir "
                f"'{command_text}'. Ya activaste la animación en tu cara: en unos segundos vas a "
                f"estar tomando {_dname}. Respondé con UNA sola frase corta, fresca y variada, en "
                "tu personalidad actual, anunciando que te lo tomás. No expliques nada técnico, "
                "no menciones esta nota, no hagas preguntas.]"
            )
            log_info(f"[Bebidas] comando por voz -> bebida '{_pdrink}'; frase por Gemini")
            try:
                _stream = brain.process_user_input_stream(_nota)
                await tts.speak_stream(_stream, auto_listen=False)
            except Exception as e:
                log_error(f"[Bebidas] fallo la respuesta de Gemini, fallback local: {e}")
                await tts.speak("Dale, me lo tomo.", auto_listen=False)
        else:
            await tts.speak(local_reply, auto_listen=(not is_rest))
        # Etapa diferida (mate/bebidas/dormido): se aplica recién cuando Titán
        # terminó de decir el aviso, no mientras lo está diciendo.
        # En bebidas el formato es "bebidas:fernet" (etapa:bebida).
        pending_stage = state_mgr.pop_pending_stage()
        if pending_stage:
            try:
                from tools.system_control import system_control
                if ":" in pending_stage:
                    _pstage, _pdrink = pending_stage.split(":", 1)
                else:
                    _pstage, _pdrink = pending_stage, None
                system_control.set_inactivity_stage(_pstage, _pdrink)
                log_info(f"[Bebidas] etapa aplicada: {_pstage}:{_pdrink}")
            except Exception as _e:
                # FIX 2026-09-24: antes un error acá (ej. TypeError por firma)
                # mataba el comando en silencio y la animación nunca arrancaba.
                log_error(f"[Bebidas] ERROR aplicando etapa diferida {pending_stage!r}: {_e}")
        return

    # 5. Detectar despedidas para salir de la conversación y volver a reposo.
    # NOTA 2026-09-18 (Exequiel, regla sin frases hechas): la despedida la
    # genera Gemini fresca cada vez, en la personalidad del modo actual. No hay
    # apuro de latencia porque la charla ya terminó (opción B).
    goodbye_words = ["chau", "chao", "adios", "hasta luego", "nos vemos", "listo gracias", "nada mas", "nada más", "gracias titan", "gracias che"]
    if any(clean_cmd == gw or clean_cmd.startswith("chau") or clean_cmd.startswith("chao") for gw in goodbye_words):
        try:
            if tts._is_speaking:
                tts.stop()
        except Exception:
            pass
        async with command_lock:
            # process_user_input_stream ya registra el mensaje en el historial
            stream_gen = brain.process_user_input_stream(command_text)
            await tts.speak_stream(stream_gen, auto_listen=False)
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
    # B-16: apagar limpio ante SIGTERM (systemctl stop / kill) o SIGINT.
    _install_signal_handlers(asyncio.current_task())

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

    # 4d. P0-5 — Limpieza periódica de artefactos privados/residuales
    # (imágenes IA en server/static/generated). Al arrancar y cada 6 horas.
    from core.artifact_cleanup import sweep_all

    async def _artifact_cleanup_loop():
        while True:
            try:
                report = sweep_all()
                total = sum(r.get("deleted", 0) for r in report.values())
                if total:
                    log_info(f"[Limpieza] Artefactos eliminados: {report}")
            except Exception:
                pass
            await asyncio.sleep(6 * 3600)

    try:
        report = sweep_all()
        total = sum(r.get("deleted", 0) for r in report.values())
        if total:
            log_info(f"[Limpieza] Artefactos eliminados al arrancar: {report}")
    except Exception:
        pass
    asyncio.create_task(_artifact_cleanup_loop())

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

    # S-11: segundo listener solo-TLS para el satélite (misma app, mismo
    # proceso: el estado en memoria — confirmaciones, sesiones — se comparte).
    # Si no hay certificado, el canal TLS no se levanta y el satélite usa
    # ws:// con aviso (plan B); el puerto 8000 no cambia.
    from core.satellite_tls import build_tls_server_config
    global active_tls_server
    tls_server = None
    tls_config = build_tls_server_config(web_app, config.server_host, config.satellite_tls_port)
    web_servers = [server]
    if tls_config is not None:
        tls_server = uvicorn.Server(tls_config)
        web_servers.append(tls_server)
        log_success(f"Canal TLS del satélite: wss://0.0.0.0:{config.satellite_tls_port} (certificado OK)")
    else:
        log_warning("[S-11] Falta certs/titan-satellite.crt: canal TLS DESHABILITADO, el satélite usará ws:// en texto plano.")
    active_tls_server = tls_server

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

    # P0: si no hay ningún dispositivo con rol "api" enrolado, generar un
    # código de configuración inicial (solo en consola) para emparejar el
    # primer navegador/HUD en /pair. Sin esto nadie puede entrar al HUD.
    from core.security import api_devices_exist, ensure_admin_role
    from core.pairing import pairing_manager
    # S-4: migración del rol admin (idempotente; si ya hay admin no toca nada).
    ensure_admin_role()
    if not api_devices_exist():
        # S-4: el primer dispositivo también es admin (si no, nadie podría
        # gestionar dispositivos después).
        setup_code = pairing_manager.create_setup(["api", "admin"], ttl_seconds=600)
        print(
            "\n============================================================\n"
            "  🔑 CONFIGURACIÓN INICIAL DEL HUD\n"
            f"  No hay ningún dispositivo emparejado. Código: {setup_code}\n"
            f"  Válido por 10 minutos. Abrí http://{local_ip}:{config.server_port}/pair\n"
            "  en tu navegador, ingresá el código y ese navegador queda\n"
            "  emparejado por 1 año. No lo compartas con nadie.\n"
            "============================================================\n",
            flush=True,
        )
    if config.telegram_bot_token:
        log_success("Bot de Telegram vinculado:   https://t.me/AsistenteTitanBot")
    log_info("Conectá tu celular al mismo Wi-Fi de tu casa y abrí esa dirección.")
    log_info(f"Atajo de teclado global: [{config.hotkey.upper()}] para activar escucha instantánea.")
    log_info(f"Palabras clave de activación por voz: {', '.join(config.wake_words)}")
    log_success("¡Todo listo, máquina! El asistente está esperando tus órdenes.")

    # Mensaje inicial de bienvenida por voz (opcional)
    # asyncio.create_task(tts.speak("¡Buenas, papá! Che Asistente activo. ¿En qué te doy una mano?"))

    try:
        await asyncio.gather(*(s.serve() for s in web_servers))
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
