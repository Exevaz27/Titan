import asyncio
import inspect
import json
import os
import random
import sys
import websockets
from core.logger import log_info, log_error, log_warning, log_success
from core import rpc_auth
from core.satellite_tls import build_ws_target
from tools.system_control import system_control
from tools.app_launcher import app_launcher
from desktop.audio_ducker import audio_ducker

# P0-4 — Allowlist explícita de acciones RPC que el satélite acepta ejecutar.
# Nada fuera de esta lista se ejecuta, aunque venga firmada por el servidor.
# (Lista derivada de las ramas de _run_action + set_wallpaper.)
RPC_ALLOWED_ACTIONS = frozenset({
    "play_spotify", "play_youtube", "media_play_pause", "media_next",
    "media_prev", "stop_music", "get_current_song",
    "set_volume", "volume_up", "volume_down", "mute",
    "set_brightness", "brightness_up", "brightness_down",
    "toggle_night_light",
    "minimize_all", "lock_workstation", "get_pc_security_info",
    "close_active_window", "maximize_active_window",
    "minimize_active_window", "switch_active_window",
    "launch_app", "take_screenshot", "search_google", "open_web_service",
    "empty_recycle_bin",
    "get_clipboard", "set_clipboard",
    "get_top_processes", "kill_process", "optimize_pc_gaming",
    "flush_dns", "get_network_info", "test_network_ping",
    "shutdown_pc", "restart_pc", "sleep_pc",
    "search_files", "open_file", "show_in_folder", "trash_file", "read_file_content",
    "get_system_metrics", "get_temperature", "cool_down_pc",
    "set_power_plan", "get_power_plan",
    "duck_audio", "unduck_audio",
    "toggle_pc_voice", "set_pc_voice",
    "set_wallpaper",
    "is_media_active",
})

class TitanSatellite:
    def __init__(self, host: str = "192.168.100.5", port: int = 8000, enable_voice: bool = False):
        self.host = host
        self.port = port
        # S-11: puerto del canal TLS (wss://). Se configura con TITAN_TLS_PORT.
        self.tls_port = int(os.getenv("TITAN_TLS_PORT", "8443").strip())
        self.ws_url = f"ws://{self.host}:{self.port}/ws"
        self._is_running = True
        self.ws = None
        # Por defecto desactivada: la voz de Titán sale por los parlantes del Servidor DDR3
        # B-26: la bandera real vive en system_control (fuente única de verdad);
        # el satélite solo la sincroniza al arrancar.
        system_control.pc_voice_enabled = enable_voice
        # P0-4 — Estado de autenticación mutua con el servidor.
        # El satélite NO ejecuta ningún remote_exec hasta verificar el proof
        # del servidor (challenge-response con el token como clave).
        self._server_verified = False
        self._auth_nonce = None
        self._rpc_token = ""

    async def connect_and_listen(self):
        # P0-5 — Limpieza de artefactos privados/residuales en la PC Windows
        # (capturas viejas en Pictures/Screenshots, temporales de fondos).
        # Corre una vez al arrancar y después cada 6 horas, independiente de
        # la conexión con el servidor.
        asyncio.create_task(self._artifact_cleanup_loop())
        # B-15: contador para el backoff exponencial de reconexión.
        reconnect_attempts = 0
        while self._is_running:
            try:
                # S-11: wss:// con certificado pineado si está el archivo;
                # si no, ws:// con aviso fuerte (no lo dispara un atacante,
                # solo una instalación incompleta).
                ws_url, ssl_ctx = build_ws_target(self.host, self.port, self.tls_port)
                if ssl_ctx is None:
                    log_warning("[Satélite Windows] ⚠️ Sin certs/titan-satellite.crt: conectando por ws:// EN TEXTO PLANO (token sniffable en la LAN).")
                else:
                    log_info("[Satélite Windows] 🔒 Canal cifrado wss:// (certificado del servidor verificado).")
                log_info(f"[Satélite Windows] Conectando a Titán en {ws_url}...")
                headers = {}
                satellite_token = os.getenv("TITAN_SATELLITE_TOKEN", "").strip()
                satellite_device_id = os.getenv("TITAN_DEVICE_ID", "windows-satellite").strip()
                log_info(
                    f"[Satélite Windows] Identidad configurada: device_id={satellite_device_id or 'ausente'}, "
                    f"token={'presente' if satellite_token else 'ausente'}"
                )
                if satellite_token:
                    headers["X-Titan-Token"] = satellite_token
                if satellite_device_id:
                    headers["X-Titan-Device-ID"] = satellite_device_id
                connect_options = {
                    "ping_interval": 20,
                    "ping_timeout": 20,
                }
                header_option = "additional_headers" if "additional_headers" in inspect.signature(websockets.connect).parameters else "extra_headers"
                connect_options[header_option] = headers
                if ssl_ctx is not None:
                    connect_options["ssl"] = ssl_ctx
                async with websockets.connect(ws_url, **connect_options) as ws:
                    self.ws = ws
                    # B-15: conexión establecida → se resetea el backoff.
                    reconnect_attempts = 0
                    # P0-4 — Cada (re)conexión exige verificar al servidor de
                    # nuevo: nonce fresco y flag de verificación reseteado.
                    self._rpc_token = satellite_token
                    self._server_verified = False
                    self._auth_nonce = rpc_auth.generate_nonce()
                    log_success(f"✅ [Satélite Windows] Conectado exitosamente al servidor DDR3 ({self.host}).")
                    # Registrarse como satélite de Windows, desafiando al
                    # servidor a probar que conoce el token (auth mutua).
                    await ws.send(json.dumps({
                        "type": "register_satellite",
                        "platform": "windows",
                        "hostname": os.getenv("COMPUTERNAME", "Windows-PC"),
                        "auth_nonce": self._auth_nonce,
                    }))

                    # Iniciar emisión periódica de telemetría (CPU, RAM, Discos, Red y Temperatura)
                    telem_task = asyncio.create_task(self._telemetry_loop(ws))
                    try:
                        async for message in ws:
                            try:
                                data = json.loads(message)
                                mtype = data.get("type")
                                if mtype == "satellite_auth_ok":
                                    # P0-4 — El servidor prueba que conoce el token.
                                    # Sin proof válido no se ejecuta NADA remoto.
                                    proof = data.get("server_proof", "")
                                    if rpc_auth.verify_server_proof(self._rpc_token, self._auth_nonce or "", proof):
                                        self._server_verified = True
                                        log_success("[Satélite Windows] 🔐 Servidor verificado (auth mutua OK). Aceptando órdenes remotas.")
                                    else:
                                        log_error("[Satélite Windows] ⛔ El servidor NO pudo probar su identidad. Cierro la conexión.")
                                        await ws.close(code=1008, reason="Verificación del servidor fallida")
                                        break
                                elif mtype == "remote_exec":
                                    action = data.get("action", "")
                                    args = data.get("args", {})
                                    request_id = data.get("request_id", "")
                                    if not self._server_verified:
                                        log_warning(f"[Satélite Windows] ⛔ Orden '{action}' ignorada: servidor aún no verificado.")
                                        continue
                                    if not rpc_auth.verify_remote_command(self._rpc_token, data):
                                        log_warning(f"[Satélite Windows] ⛔ Orden '{action}' ignorada: firma HMAC inválida.")
                                        if request_id:
                                            asyncio.create_task(self._execute_and_reply(
                                                ws, request_id, action, {},
                                                pre_error="Firma HMAC inválida: orden rechazada.",
                                            ))
                                        continue
                                    if action not in RPC_ALLOWED_ACTIONS:
                                        log_warning(f"[Satélite Windows] ⛔ Orden '{action}' rechazada: no está en la allowlist RPC.")
                                        if request_id:
                                            asyncio.create_task(self._execute_and_reply(
                                                ws, request_id, action, {},
                                                pre_error=f"Acción no permitida por política RPC: {action}",
                                            ))
                                        continue
                                    log_info(f"[Satélite Windows] 🎯 Orden remota recibida: {action} (args: {args})")
                                    # Ejecutar en background para no bloquear el loop de mensajes
                                    asyncio.create_task(
                                        self._execute_and_reply(ws, request_id, action, args)
                                    )
                                elif mtype == "audio_duck":
                                    action = data.get("action", "duck")
                                    target = int(data.get("target", 15))
                                    if action == "duck":
                                        audio_ducker.duck(target)
                                    else:
                                        audio_ducker.unduck()
                                elif mtype == "state_change":
                                    state = data.get("state")
                                    if state in ("LISTENING", "PROCESSING", "SPEAKING"):
                                        audio_ducker.duck(15)
                                    elif state == "IDLE":
                                        audio_ducker.unduck()
                                elif mtype == "play_audio":
                                    # Solo reproducir en PC Principal si el usuario lo activó explícitamente
                                    # B-26: la bandera real vive en system_control.
                                    if getattr(system_control, "pc_voice_enabled", False):
                                        b64_audio = data.get("audio_base64")
                                        if b64_audio:
                                            asyncio.create_task(self._play_remote_audio(b64_audio))
                                elif mtype in ("interrupt", "stop_speaking", "barge_in"):
                                    try:
                                        import pygame
                                        if pygame.mixer.get_init():
                                            pygame.mixer.stop()
                                    except Exception:
                                        pass
                                elif mtype == "wake_pulse":
                                    audio_ducker.duck(15)
                            except Exception as e:
                                log_warning(f"[Satélite Windows] Error procesando mensaje: {e}")
                    finally:
                        # B-15: al morir la conexión, cancelar la telemetría.
                        # Sin esto la tarea vieja quedaba huérfana pegándole a
                        # un ws muerto y en cada reconexión se sumaba otra.
                        telem_task.cancel()
                        try:
                            await telem_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                # B-15: backoff exponencial con jitter en vez de reintentar
                # cada 4s clavados (si la DDR3 está caída un rato, no tiene
                # sentido martillarla; el jitter evita reintentos sincronizados).
                delay = min(4.0 * (2 ** reconnect_attempts), 60.0)
                reconnect_attempts += 1
                delay *= random.uniform(0.75, 1.25)
                log_warning(f"[Satélite Windows] Conexión perdida ({e}). Reintentando en {delay:.1f}s...")
                await asyncio.sleep(delay)

    async def _execute_and_reply(self, ws, request_id: str, action: str, args: dict, pre_error: str = ""):
        """Ejecuta la acción en Windows y envía el resultado de vuelta al servidor DDR3.

        Si `pre_error` viene con texto, no se ejecuta nada: se responde el
        error directamente (usado para rechazos de firma/allowlist P0-4).
        """
        if pre_error:
            result = {"status": "error", "message": pre_error}
        else:
            try:
                # B-9: la acción corre en un hilo worker (run_in_executor) en
                # vez de directo en el event loop. Antes una acción larga
                # (screenshot, powershell) congelaba el loop: el satélite no
                # respondía ping ni recibía órdenes hasta que terminaba.
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._run_action, action, args)
            except Exception as e:
                result = {"status": "error", "message": f"Error ejecutando {action}: {e}"}

        # Solo responder si el servidor mandó un request_id (RPC bidireccional)
        if request_id:
            try:
                await ws.send(json.dumps({
                    "type": "rpc_reply",
                    "request_id": request_id,
                    "result": result
                }))
            except Exception as e:
                log_warning(f"[Satélite Windows] No se pudo enviar rpc_reply para {action}: {e}")

    async def _play_remote_audio(self, b64_audio: str):
        """Reproduce chunks de audio y fillers recibidos en tiempo real desde el servidor DDR3"""
        try:
            import base64
            import io
            import pygame
            raw = base64.b64decode(b64_audio)
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            bio = io.BytesIO(raw)
            sound = pygame.mixer.Sound(bio)
            sound.set_volume(0.95)
            sound.play()
        except Exception as e:
            log_warning(f"[Satélite Windows] Error reproduciendo audio remoto: {e}")

    async def _telemetry_loop(self, ws):
        """Emite periódicamente las métricas de la PC Principal (Windows) al servidor Titán.

        R-8: backoff exponencial ante fallos de envío. Antes, al primer error
        el loop moría (o el send se colgaba sin timeout en una conexión
        semi-abierta); ahora reintenta con espera creciente en vez de
        martillar un socket moribundo cada 2.5s. La tarea se cancela igual
        desde el finally de la conexión (B-15), así que este loop nunca
        sobrevive a su websocket.
        """
        failures = 0
        while self._is_running:
            try:
                metrics = system_control.get_system_metrics()
                metrics["pc_voice_enabled"] = getattr(system_control, "pc_voice_enabled", False)
                payload = json.dumps({
                    "type": "satellite_telemetry",
                    "platform": "windows",
                    "hostname": os.getenv("COMPUTERNAME", "Windows-PC"),
                    "metrics": metrics
                })
                # Timeout: un send colgado en una conexión semi-abierta no
                # debe wedger la tarea para siempre.
                await asyncio.wait_for(ws.send(payload), timeout=10)
                failures = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                failures += 1
                delay = min(2.5 * (2 ** (failures - 1)), 60.0)
                log_warning(f"[Satélite Windows] Telemetría falló ({e}); reintentando en {delay:.1f}s...")
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break
                continue
            await asyncio.sleep(2.5)

    async def _artifact_cleanup_loop(self):
        """P0-5 — Barre artefactos privados/residuales cada 6 horas."""
        from core.artifact_cleanup import sweep_all
        while self._is_running:
            try:
                report = sweep_all()
                total = sum(r.get("deleted", 0) for r in report.values())
                if total:
                    log_info(f"[Satélite Windows] Limpieza de artefactos: {report}")
            except Exception:
                pass
            await asyncio.sleep(6 * 3600)

    def _run_action(self, action: str, args: dict) -> dict:
        """Ejecuta una acción de Windows y devuelve {status, message}."""
        try:
            # === AUDIO / MULTIMEDIA ===
            if action == "play_spotify":
                return system_control.play_spotify(args.get("query", ""))
            elif action == "play_youtube":
                return system_control.play_youtube(args.get("query", ""))
            elif action == "media_play_pause":
                return system_control.media_play_pause()
            elif action == "media_next":
                return system_control.media_next()
            elif action == "media_prev":
                return system_control.media_prev()
            elif action == "stop_music":
                return system_control.stop_music()
            elif action == "get_current_song":
                return system_control.get_current_song()

            # === VOLUMEN ===
            elif action == "set_volume":
                return system_control.set_volume(int(args.get("level", 50)))
            elif action == "volume_up":
                return system_control.volume_up(int(args.get("step", 15)))
            elif action == "volume_down":
                return system_control.volume_down(int(args.get("step", 15)))
            elif action == "mute":
                return system_control.mute()

            # === BRILLO ===
            elif action == "set_brightness":
                return system_control.set_brightness(int(args.get("level", 70)))
            elif action == "brightness_up":
                return system_control.brightness_up(int(args.get("step", 10)))
            elif action == "brightness_down":
                return system_control.brightness_down(int(args.get("step", 10)))
            elif action == "toggle_night_light":
                return system_control.toggle_night_light()

            # === VENTANAS Y ESCRITORIO ===
            elif action == "minimize_all":
                return system_control.minimize_all()
            elif action == "close_active_window":
                # B-24: la DDR3 delega acá (en Linux ctypes.windll no existe)
                return system_control.close_active_window()
            elif action == "maximize_active_window":
                return system_control.maximize_active_window()
            elif action == "minimize_active_window":
                return system_control.minimize_active_window()
            elif action == "switch_active_window":
                return system_control.switch_active_window()
            elif action == "lock_workstation":
                return system_control.lock_workstation()
            elif action == "get_pc_security_info":
                return system_control.get_pc_security_info()

            # === APPS Y ARCHIVOS ===
            elif action == "launch_app":
                return app_launcher.launch_app(args.get("app_name", ""))
            elif action == "take_screenshot":
                res = system_control.take_screenshot()
                if res.get("status") == "success" and res.get("path") and os.path.exists(res["path"]):
                    try:
                        import base64
                        import io
                        from PIL import Image
                        with Image.open(res["path"]) as img:
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            bio = io.BytesIO()
                            img.save(bio, format="JPEG", quality=85, optimize=True)
                            res["photo_base64"] = base64.b64encode(bio.getvalue()).decode("ascii")
                    except Exception as e_b64:
                        try:
                            import base64
                            with open(res["path"], "rb") as f:
                                res["photo_base64"] = base64.b64encode(f.read()).decode("ascii")
                        except Exception as e_fallback:
                            log_warning(f"[Satélite Windows] Error serializando captura: {e_fallback}")
                return res
            elif action == "search_google":
                return system_control.search_google(args.get("query", ""))
            elif action == "set_wallpaper":
                # P0-4 — El servidor ya validó la URL; acá se vuelve a
                # validar en la descarga (defensa en profundidad).
                return system_control.set_wallpaper(args.get("url", ""))
            elif action == "open_web_service":
                return system_control.open_web_service(args.get("service", ""))
            elif action == "empty_recycle_bin":
                return system_control.empty_recycle_bin()

            # === PORTAPAPELES ===
            elif action == "get_clipboard":
                return system_control.get_clipboard()
            elif action == "set_clipboard":
                return system_control.set_clipboard(args.get("text", ""))

            # === PROCESOS / DOCTOR PC ===
            elif action == "get_top_processes":
                return system_control.get_top_processes(
                    sort_by=args.get("sort_by", "ram"),
                    limit=int(args.get("limit", 5))
                )
            elif action == "kill_process":
                return system_control.kill_process(args.get("name_or_pid", ""))
            elif action == "optimize_pc_gaming":
                return system_control.optimize_pc_gaming()

            # === RED ===
            elif action == "flush_dns":
                return system_control.flush_dns()
            elif action == "get_network_info":
                return system_control.get_network_info()
            elif action == "test_network_ping":
                return system_control.test_network_ping(args.get("host", "8.8.8.8"))

            # === ENERGÍA ===
            elif action == "shutdown_pc":
                return system_control.shutdown_pc()
            elif action == "restart_pc":
                return system_control.restart_pc()
            elif action == "sleep_pc":
                return system_control.sleep_pc()

            # === ARCHIVOS (delegados desde Linux al satélite Windows) ===
            elif action == "search_files":
                from tools.file_manager import file_manager
                return file_manager.search_files(
                    query=args.get("query", ""),
                    extension=args.get("extension"),
                    location=args.get("location"),
                    max_results=int(args.get("max_results", 10))
                )
            elif action == "read_file_content":
                from tools.file_manager import file_manager
                return file_manager.read_file_content(
                    args.get("file_path", ""),
                    int(args.get("max_chars", 3000))
                )
            elif action == "open_file":
                from tools.file_manager import file_manager
                return file_manager.open_file(args.get("file_path", ""))
            elif action == "show_in_folder":
                from tools.file_manager import file_manager
                return file_manager.show_in_folder(args.get("file_path", ""))
            elif action == "trash_file":
                from tools.file_manager import file_manager
                return file_manager.trash_file(args.get("file_path", ""))

            # === TELEMETRÍA Y CONTROL TÉRMICO / ENERGÍA ===
            elif action == "get_system_metrics":
                return system_control.get_system_metrics()
            elif action == "get_temperature":
                return system_control.get_hardware_temperature()
            elif action == "cool_down_pc":
                return system_control.cool_down_pc()
            elif action == "set_power_plan":
                return system_control.set_power_plan(args.get("plan_mode", "balanced"))
            elif action == "get_power_plan":
                return system_control.get_power_plan()

            # === AUDIO DUCKING DIRECTO ===
            elif action == "duck_audio":
                audio_ducker.duck(int(args.get("target", 15)))
                return {"status": "success", "message": "Audio atenuado"}
            elif action == "unduck_audio":
                audio_ducker.unduck()
                return {"status": "success", "message": "Audio restaurado"}
            elif action == "is_media_active":
                # B-11: la DDR3 pregunta si hay audio en la PC (pycaw no existe en Linux)
                return {"status": "success", "media_active": audio_ducker.is_media_active()}

            # === VOZ DE TITÁN EN LA PC PRINCIPAL ===
            # B-26: la implementación real vive en system_control (bandera
            # pc_voice_enabled); el satélite delega en vez de duplicar lógica.
            elif action == "toggle_pc_voice":
                return system_control.toggle_pc_voice()
            elif action == "set_pc_voice":
                return system_control.set_pc_voice(args.get("enabled", False))

            else:
                log_warning(f"[Satélite Windows] Acción no reconocida: {action}")
                return {"status": "error", "message": f"Acción no reconocida: {action}"}

        except Exception as e:
            log_error(f"[Satélite Windows] Error ejecutando {action}: {e}")
            return {"status": "error", "message": f"Error ejecutando {action}: {e}"}

    def stop(self):
        self._is_running = False

def run_standalone():
    host = "192.168.100.5"
    enable_voice = "--enable-voice" in sys.argv
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            host = arg
            break
    sat = TitanSatellite(host=host, enable_voice=enable_voice)
    try:
        asyncio.run(sat.connect_and_listen())
    except KeyboardInterrupt:
        sat.stop()

if __name__ == "__main__":
    run_standalone()

