import asyncio
import inspect
import json
import os
import sys
import websockets
from core.logger import log_info, log_error, log_warning, log_success
from tools.system_control import system_control
from tools.app_launcher import app_launcher
from desktop.audio_ducker import audio_ducker

class TitanSatellite:
    def __init__(self, host: str = "192.168.100.5", port: int = 8000, enable_voice: bool = False):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{self.host}:{self.port}/ws"
        self._is_running = True
        self.ws = None
        # Por defecto desactivada: la voz de Titán sale por los parlantes del Servidor DDR3
        self.play_remote_audio_enabled = enable_voice

    async def connect_and_listen(self):
        while self._is_running:
            try:
                log_info(f"[Satélite Windows] Conectando a Titán en {self.ws_url}...")
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
                async with websockets.connect(self.ws_url, **connect_options) as ws:
                    self.ws = ws
                    log_success(f"✅ [Satélite Windows] Conectado exitosamente al servidor DDR3 ({self.host}).")
                    # Registrarse como satélite de Windows
                    await ws.send(json.dumps({
                        "type": "register_satellite",
                        "platform": "windows",
                        "hostname": os.getenv("COMPUTERNAME", "Windows-PC")
                    }))

                    # Iniciar emisión periódica de telemetría (CPU, RAM, Discos, Red y Temperatura)
                    telem_task = asyncio.create_task(self._telemetry_loop(ws))

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            mtype = data.get("type")
                            if mtype == "remote_exec":
                                action = data.get("action", "")
                                args = data.get("args", {})
                                request_id = data.get("request_id", "")
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
                                if getattr(self, "play_remote_audio_enabled", False):
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

            except Exception as e:
                log_warning(f"[Satélite Windows] Conexión perdida ({e}). Reintentando en 4s...")
                await asyncio.sleep(4)

    async def _execute_and_reply(self, ws, request_id: str, action: str, args: dict):
        """Ejecuta la acción en Windows y envía el resultado de vuelta al servidor DDR3."""
        try:
            result = self._run_action(action, args)
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
        """Emite periódicamente las métricas de la PC Principal (Windows) al servidor Titán"""
        while self._is_running:
            try:
                metrics = system_control.get_system_metrics()
                metrics["pc_voice_enabled"] = getattr(self, "play_remote_audio_enabled", False)
                await ws.send(json.dumps({
                    "type": "satellite_telemetry",
                    "platform": "windows",
                    "hostname": os.getenv("COMPUTERNAME", "Windows-PC"),
                    "metrics": metrics
                }))
            except Exception:
                break
            await asyncio.sleep(2.5)

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

            # === VOZ DE TITÁN EN LA PC PRINCIPAL ===
            elif action == "toggle_pc_voice":
                self.play_remote_audio_enabled = not self.play_remote_audio_enabled
                st = "activada" if self.play_remote_audio_enabled else "silenciada"
                msg = f"Voz de Titán en la PC Principal {st}."
                log_info(f"[Satélite Windows] {msg}")
                return {"status": "success", "enabled": self.play_remote_audio_enabled, "message": msg}
            elif action == "set_pc_voice":
                self.play_remote_audio_enabled = bool(args.get("enabled", False))
                st = "activada" if self.play_remote_audio_enabled else "silenciada"
                msg = f"Voz de Titán en la PC Principal {st}."
                log_info(f"[Satélite Windows] {msg}")
                return {"status": "success", "enabled": self.play_remote_audio_enabled, "message": msg}

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

