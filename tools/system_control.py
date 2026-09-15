import ctypes
import os
import sys
import socket
import time
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import psutil
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState
from core.process_utils import run_silent, popen_silent

# Constantes de teclas multimedia de Windows
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

POWER_PLANS = {
    "eco": {"guid": "a1841308-3541-4fab-bc81-f71556f20b4a", "name": "Economizador / Modo Frío", "desc": "Reduce voltaje y reloj de la CPU para enfriar la máquina rápidamente"},
    "balanced": {"guid": "381b4222-f694-41f0-9685-ff5bb260df2e", "name": "Equilibrado", "desc": "Rendimiento balanceado según demanda del sistema"},
    "performance": {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "name": "Alto rendimiento", "desc": "Máxima potencia para juegos y edición"}
}

class SystemControl:
    def __init__(self):
        self._volume_interface = None
        self.max_session_temp: float = 0.0
        self.last_temp: Optional[float] = None
        self.thermal_alert_threshold: float = 80.0
        self._init_audio()

    def _init_audio(self):
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, "EndpointVolume"):
                self._volume_interface = speakers.EndpointVolume
            else:
                from pycaw.pycaw import IAudioEndpointVolume
                from comtypes import CLSCTX_ALL
                interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._volume_interface = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        except Exception as e:
            log_warning(f"No se pudo enlazar con pycaw directamente: {e}")

    def get_volume(self) -> int:
        if self._volume_interface:
            try:
                current = self._volume_interface.GetMasterVolumeLevelScalar()
                return int(round(current * 100))
            except Exception:
                pass
        return 50

    def set_volume_silent(self, level: int):
        """Ajusta el volumen de forma silenciosa (sin emitir eventos ni cambiar estado), para ducking de audio"""
        level = max(0, min(100, level))
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
            except Exception:
                pass

    def set_volume(self, level: int) -> Dict[str, Any]:
        """Ajusta el volumen del sistema de 0 a 100"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_volume", {"level": level}, f"Puse el volumen al {level}%.")
            if remote_res:
                return remote_res
        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Ajustando volumen al {level}%...")
        level = max(0, min(100, level))
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
                msg = f"Volumen puesto al {level}%."
                state_mgr.emit_tool_call("set_volume", {"level": level}, msg)
                return {"status": "success", "message": msg, "level": level}
            except Exception as e:
                log_error(f"Error pycaw: {e}")

        return {
            "status": "error",
            "message": "No pude ajustar el volumen porque la interfaz de audio no está disponible.",
            "level": level,
        }

    def volume_up(self, step: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("volume_up", {"step": step}, f"Subí el volumen.")
            if remote_res:
                return remote_res
        curr = self.get_volume()
        new_vol = min(100, curr + step)
        return self.set_volume(new_vol)

    def volume_down(self, step: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("volume_down", {"step": step}, f"Bajé el volumen.")
            if remote_res:
                return remote_res
        curr = self.get_volume()
        new_vol = max(0, curr - step)
        return self.set_volume(new_vol)


    def mute(self, mute_state: Optional[bool] = None) -> Dict[str, Any]:
        """Mutea o desmutea el audio"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("mute", {}, "Audio muteado/desmuteado.")
            if remote_res:
                return remote_res
        if self._volume_interface:
            try:
                is_muted = self._volume_interface.GetMute()
                target = not is_muted if mute_state is None else mute_state
                self._volume_interface.SetMute(1 if target else 0, None)
                estado = "muteado" if target else "desmuteado"
                msg = f"Audio {estado}."
                state_mgr.emit_tool_call("mute", {"target": target}, msg)
                return {"status": "success", "message": msg, "muted": target}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {
            "status": "error",
            "message": "No pude acceder a la interfaz de audio para cambiar el estado de mute.",
        }
    def toggle_pc_voice(self) -> Dict[str, Any]:
        """Activa o desactiva la salida de voz de Titán en la PC Principal Windows (por defecto sale por DDR3)"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("toggle_pc_voice", {}, "Cambié el estado de la voz en la PC Principal.")
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "El satélite en Windows no está conectado."}
        return {"status": "success", "message": "Comando recibido en Windows."}

    def set_pc_voice(self, enabled: bool) -> Dict[str, Any]:
        """Establece explícitamente si la voz de Titán sale por la PC Principal Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_pc_voice", {"enabled": enabled}, "Ajusté la voz en la PC Principal.")
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "El satélite en Windows no está conectado."}
        return {"status": "success", "message": "Comando recibido en Windows."}


    def _remote_exec_if_linux(self, action: str, args: dict, success_msg: str) -> Optional[Dict[str, Any]]:
        """Si corre en Linux (servidor DDR3), delega la acción a cualquier satélite Windows conectado vía WebSocket RPC bidireccional."""
        if os.name != 'nt':
            try:
                from server.websocket_hub import ws_hub
                if ws_hub.has_windows_satellite():
                    loop = getattr(state_mgr, "_loop", None)
                    if loop and loop.is_running():
                        import asyncio

                        # Prevenir deadlock: si la llamada se hizo sincrónicamente desde el hilo del event loop
                        try:
                            current_loop = asyncio.get_running_loop()
                        except RuntimeError:
                            current_loop = None

                        if current_loop is loop:
                            # Estamos en el hilo del event loop: NO podemos bloquear con fut.result()
                            log_warning(f"[RPC] _remote_exec_if_linux llamado sincrónicamente desde el event loop para '{action}'. Disparando en background.")
                            asyncio.create_task(ws_hub.call_remote(action, args, timeout=15.0))
                            state_mgr.emit_tool_call(action, args, success_msg)
                            return {"status": "pending", "message": success_msg}

                        fut = asyncio.run_coroutine_threadsafe(
                            ws_hub.call_remote(action, args, timeout=15.0), loop
                        )
                        try:
                            result = fut.result(timeout=16.0)
                            if not isinstance(result, dict):
                                result = {"status": "success", "message": str(result)}
                            msg = result.get("message", success_msg)
                            state_mgr.emit_tool_call(action, args, msg)
                            res = dict(result)
                            if "message" not in res:
                                res["message"] = msg
                            if "status" not in res:
                                res["status"] = "success"
                            return res
                        except Exception as e:
                            log_warning(f"[RPC] Error esperando respuesta del satélite para '{action}': {e}")
                            error_msg = f"El satélite Windows no confirmó la operación '{action}'."
                            state_mgr.emit_tool_call(action, args, error_msg)
                            return {"status": "timeout", "message": error_msg}
                    else:
                        # Sin loop activo: fallback fire-and-forget
                        state_mgr._notify({
                            "type": "remote_exec",
                            "action": action,
                            "args": args
                        })
                        state_mgr.emit_tool_call(action, args, success_msg)
                        return {"status": "success", "message": success_msg}
                else:
                    return {
                        "status": "warning",
                        "message": "Che, no detecto la compu principal conectada para ejecutar esa orden. Asegurate de tener Titán abierto en Windows."
                    }
            except Exception as e:
                log_warning(f"Error delegando acción remota {action}: {e}")
        return None

    def _get_spotify_cli_path(self) -> str:
        p = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        return p if os.path.exists(p) else ""

    def _get_spotify_exe_path(self) -> str:
        p = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
        return p if os.path.exists(p) else ""

    def _bring_spotify_window_to_front(self) -> bool:
        """Busca la ventana de Spotify en el escritorio interactivo y la restaura al frente"""
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)

            target_hwnd = None
            def enum_cb(hwnd, _):
                nonlocal target_hwnd
                if user32.IsWindow(hwnd):
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    length = user32.GetWindowTextLengthW(hwnd)
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    t_lower = title_buf.value.lower()
                    if "spotify" in t_lower or "spotify" in cls_buf.value.lower():
                        target_hwnd = hwnd
                        return False
                return True

            CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)(enum_cb)
            user32.EnumWindows(CB, 0)

            if target_hwnd:
                user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
                user32.SetForegroundWindow(target_hwnd)
                user32.BringWindowToTop(target_hwnd)
                return True
        except Exception:
            pass
        return False

    def _ensure_spotify_running(self) -> bool:
        cli_path = self._get_spotify_cli_path()
        exe_path = self._get_spotify_exe_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower() or "logged in: yes" in res.stdout.lower():
                    self._bring_spotify_window_to_front()
                    return True
            except Exception:
                pass

        if exe_path and os.path.exists(exe_path):
            # Lanzamiento interactivo mediante schtasks sin abrir ventana de consola
            task_name = "TitanSpotifyLaunch"
            run_silent(["schtasks", "/create", "/tn", task_name, "/tr", f'"{exe_path}"', "/sc", "once", "/st", "23:59", "/f", "/it"], capture_output=True)
            run_silent(["schtasks", "/run", "/tn", task_name], capture_output=True)
            time.sleep(1.0)
            run_silent(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True)

            if cli_path:
                for _ in range(12):
                    time.sleep(0.4)
                    try:
                        res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                        if "is running" in res.stdout.lower():
                            self._bring_spotify_window_to_front()
                            return True
                    except Exception:
                        pass
            else:
                time.sleep(1.5)
                self._bring_spotify_window_to_front()
                return True
        return False


    def _send_media_key(self, vk_code: int):
        import time
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

    def media_play_pause(self) -> Dict[str, Any]:
        """Pausa o reanuda la música/video dando prioridad a Spotify y luego a YouTube en Brave"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_play_pause", {}, "Play/Pausa enviado a la compu, che.")
            if remote_res:
                return remote_res

        # 1. Spotify si está activo
        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res_np = run_silent([cli_path, "now-playing"], capture_output=True, text=True, timeout=2)
                if "status: playing" in res_np.stdout.lower():
                    run_silent([cli_path, "pause"], capture_output=True)
                    msg = "Puse pausa a la música en Spotify."
                    state_mgr.emit_tool_call("media_play_pause", {"target": "spotify", "action": "pause"}, msg)
                    return {"status": "success", "message": msg}
                elif "status: paused" in res_np.stdout.lower() or "status: stopped" in res_np.stdout.lower():
                    run_silent([cli_path, "resume"], capture_output=True)
                    msg = "Reanudé la música en Spotify."
                    state_mgr.emit_tool_call("media_play_pause", {"target": "spotify", "action": "resume"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        # 2. Si no es Spotify, enviar la tecla multimedia del sistema (pausa YouTube/video sin mutear el navegador)
        self._send_media_key(VK_MEDIA_PLAY_PAUSE)
        msg = "Play/Pausa enviado."
        state_mgr.emit_tool_call("media_play_pause", {}, msg)
        return {"status": "success", "message": msg}

    def stop_music(self) -> Dict[str, Any]:
        """Detiene la música por completo pausando Spotify o cerrando YouTube en Brave"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("stop_music", {}, "Listo, detuve la música en la compu.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                run_silent([cli_path, "pause"], capture_output=True)
            except Exception:
                pass
        run_silent(["taskkill", "/F", "/IM", "brave.exe"], capture_output=True)
        msg = "Listo, detuve la música."
        state_mgr.emit_tool_call("stop_music", {}, msg)
        return {"status": "success", "message": msg}

    def media_next(self) -> Dict[str, Any]:
        """Pasa a la siguiente canción"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_next", {}, "Puse la siguiente canción en la compu, crack.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower():
                    run_silent([cli_path, "next"], capture_output=True)
                    msg = "Puse la siguiente canción en Spotify."
                    state_mgr.emit_tool_call("media_next", {"target": "spotify", "action": "next"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        self._send_media_key(VK_MEDIA_NEXT_TRACK)
        msg = "Puse la siguiente pista."
        state_mgr.emit_tool_call("media_next", {}, msg)
        return {"status": "success", "message": msg}

    def media_prev(self) -> Dict[str, Any]:
        """Vuelve a la canción anterior"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_prev", {}, "Volví al tema anterior en la compu.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower():
                    run_silent([cli_path, "previous"], capture_output=True)
                    msg = "Volví a la canción anterior en Spotify."
                    state_mgr.emit_tool_call("media_prev", {"target": "spotify", "action": "previous"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        self._send_media_key(VK_MEDIA_PREV_TRACK)
        msg = "Volví a la pista anterior."
        state_mgr.emit_tool_call("media_prev", {}, msg)
        return {"status": "success", "message": msg}

    def get_current_song(self) -> Dict[str, Any]:
        """Obtiene el nombre de la canción o tema que está reproduciéndose actualmente"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_current_song", {}, "Chequeé qué suena en la compu.")
            if remote_res:
                return remote_res
        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "now-playing"], capture_output=True, text=True, timeout=2)
                if res.stdout and ("spotify:track:" in res.stdout or "—" in res.stdout or "-" in res.stdout):
                    lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                    raw_info = lines[0] if lines else ""
                    # Quitar el URI si está al final
                    clean_info = raw_info.split("spotify:")[0].strip()
                    if "—" in clean_info:
                        parts = clean_info.split("—")
                        track_info = f"'{parts[0].strip()}' de {parts[1].strip()}"
                    elif "-" in clean_info:
                        parts = clean_info.split("-")
                        track_info = f"'{parts[0].strip()}' de {parts[1].strip()}"
                    else:
                        track_info = clean_info or "música en Spotify"

                    msg = f"Está sonando {track_info} en Spotify, fiera."
                    state_mgr.emit_tool_call("get_current_song", {"target": "spotify", "track": track_info}, msg)
                    return {"status": "success", "message": msg, "track": track_info}
            except Exception:
                pass
        return {"status": "error", "message": "No tengo información de qué tema está sonando ahora."}

    def lock_workstation(self) -> Dict[str, Any]:
        """Bloquea la sesión de Windows de inmediato"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("lock_workstation", {}, "Bloqueé la compu. Nadie te va a chusmear nada.")
            if remote_res:
                return remote_res
        try:
            ctypes.windll.user32.LockWorkStation()
            msg = "Bloqueé la compu. Nadie te va a chusmear nada."
            state_mgr.emit_tool_call("lock_workstation", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def minimize_all(self) -> Dict[str, Any]:
        """Minimiza todas las ventanas y muestra el escritorio"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("minimize_all", {}, "Minimicé todo para que veas el escritorio limpito.")
            if remote_res:
                return remote_res
        try:
            run_silent(["powershell", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"], check=False)
            msg = "Minimicé todo para que veas el escritorio limpito."
            state_mgr.emit_tool_call("minimize_all", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    def take_screenshot(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """Captura la pantalla y la guarda en la carpeta de Imágenes"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("take_screenshot", {}, "Saqué la captura de pantalla en tu compu.")
            if remote_res:
                return remote_res
        state_mgr.set_state(AssistantState.EXECUTING_TOOL, "Sacando captura de pantalla...")
        pictures_dir = Path.home() / "Pictures" / "Screenshots"
        pictures_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = f"captura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        elif not filename.lower().endswith(".png"):
            filename += ".png"

        target_path = pictures_dir / filename
        # 1. Intentar con Pillow (más rápido y directo)
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(target_path))
            msg = f"Saqué captura y la guardé en '{target_path.name}'."
            state_mgr.emit_tool_call("take_screenshot", {"target": str(target_path)}, msg)
            return {"status": "success", "message": msg, "path": str(target_path)}
        except Exception as ex_pil:
            pass

        # 2. Fallback con PowerShell
        try:
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
            $bitmap.Save('{str(target_path)}')
            $graphics.Dispose()
            $bitmap.Dispose()
            """
            run_silent(["powershell", "-NoProfile", "-Command", ps_script], check=True)
            msg = f"Saqué captura y la guardé en '{target_path.name}'."
            state_mgr.emit_tool_call("take_screenshot", {"target": str(target_path)}, msg)
            return {"status": "success", "message": msg, "path": str(target_path)}

        except Exception as e:
            return {"status": "error", "message": "Che papá, parece que la pantalla de la computadora está bloqueada, suspendida o apagada en este momento. Desbloqueá la sesión para que pueda ver."}

    def get_hardware_temperature(self) -> Dict[str, Any]:
        """Obtiene la temperatura de hardware (CPU/GPU/Hotspot) en Windows o Linux"""
        res = {"cpu": None, "gpu": None, "hotspot": None}

        if sys.platform == "win32":
            # 1. AMD ADL (Ryzen APUs / Radeon)
            try:
                adl_path = "C:\\Windows\\System32\\atiadlxx.dll"
                if os.path.exists(adl_path):
                    adl = ctypes.cdll.LoadLibrary(adl_path)
                    MALLOC_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
                    cb = MALLOC_CALLBACK(lambda size: ctypes.cast(ctypes.create_string_buffer(size), ctypes.c_void_p).value)
                    context = ctypes.c_void_p()
                    if adl.ADL2_Main_Control_Create(cb, 1, ctypes.byref(context)) == 0:
                        num = ctypes.c_int(0)
                        if adl.ADL2_Adapter_NumberOfAdapters_Get(context, ctypes.byref(num)) == 0 and num.value > 0:
                            temp = ctypes.c_int(0)
                            # Type 1 = Edge / Package
                            if adl.ADL2_OverdriveN_Temperature_Get(context, 0, 1, ctypes.byref(temp)) == 0:
                                val = round(temp.value / 1000.0, 1)
                                if 0 < val < 130:
                                    res["cpu"] = val
                                    res["gpu"] = val
                            # Type 7 = Hotspot
                            temp_hot = ctypes.c_int(0)
                            if adl.ADL2_OverdriveN_Temperature_Get(context, 0, 7, ctypes.byref(temp_hot)) == 0:
                                val_hot = round(temp_hot.value / 1000.0, 1)
                                if 0 < val_hot < 130:
                                    res["hotspot"] = val_hot
                        adl.ADL2_Main_Control_Destroy(context)
            except Exception:
                pass

            # 2. NVIDIA SMI
            if res["gpu"] is None:
                try:
                    out = subprocess.check_output(
                        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                        timeout=1.5,
                        text=True
                    ).strip()
                    if out and out.isdigit():
                        res["gpu"] = float(out)
                        if res["cpu"] is None:
                            res["cpu"] = float(out)
                except Exception:
                    pass

        else:
            # Linux (DDR3 / Ubuntu)
            try:
                st = getattr(psutil, "sensors_temperatures", lambda: {})()
                if st:
                    for sname, slist in st.items():
                        for entry in slist:
                            if entry.current and 0 < entry.current < 125:
                                if res["cpu"] is None or any(k in sname.lower() for k in ["k10temp", "core", "cpu", "package"]):
                                    res["cpu"] = round(entry.current, 1)
                                    break
            except Exception:
                pass

            if res["cpu"] is None:
                try:
                    import glob
                    for f in glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
                        with open(f, "r") as fp:
                            raw = fp.read().strip()
                            if raw.isdigit():
                                val = round(float(raw) / 1000.0, 1)
                                if 0 < val < 125:
                                    res["cpu"] = val
                                    break
                except Exception:
                    pass

        return res

    def get_power_plan(self) -> Dict[str, Any]:
        """Obtiene el plan de energía activo en Windows ('eco', 'balanced', 'performance')"""
        if os.name != 'nt':
            return {"status": "success", "mode": "linux", "name": "Servidor Linux", "guid": None}

        # 1. Si ya lo tenemos en memoria, retornarlo al instante (cero sobrecarga)
        if hasattr(self, "_cached_power_plan") and self._cached_power_plan:
            return self._cached_power_plan

        # 2. Lectura directa desde el Registro de Windows (in-process, 0 subprocesos, <0.1ms)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes') as key:
                guid, _ = winreg.QueryValueEx(key, 'ActivePowerScheme')
                guid = str(guid).lower()
                mode = "balanced"
                name = "Equilibrado"
                if "a1841308" in guid:
                    mode = "eco"
                    name = "Economizador / Modo Frío"
                elif "8c5e7fda" in guid:
                    mode = "performance"
                    name = "Alto rendimiento"
                res = {"status": "success", "mode": mode, "name": name, "guid": guid}
                self._cached_power_plan = res
                return res
        except Exception as e:
            log_warning(f"[PowerPlan] Error leyendo registro: {e}")

        fallback = {"status": "success", "mode": "balanced", "name": "Equilibrado", "guid": "381b4222-f694-41f0-9685-ff5bb260df2e"}
        self._cached_power_plan = fallback
        return fallback

    def set_power_plan(self, plan_mode: str) -> Dict[str, Any]:
        """Cambia el plan de energía / modo térmico en Windows ('eco'/'cool', 'balanced', 'performance')"""
        mode_clean = plan_mode.lower().strip()
        target_mode = "balanced"
        if any(k in mode_clean for k in ["eco", "frio", "frío", "cool", "ahorro", "economizador", "bajar"]):
            target_mode = "eco"
        elif any(k in mode_clean for k in ["alto", "performance", "turbo", "max", "potencia", "rendimiento", "juego", "gamer"]):
            target_mode = "performance"
        else:
            target_mode = "balanced"

        plan_info = POWER_PLANS.get(target_mode, POWER_PLANS["balanced"])

        if os.name != 'nt':
            success_msg = f"Activé el plan {plan_info['name']} en la compu, papá."
            remote_res = self._remote_exec_if_linux("set_power_plan", {"plan_mode": target_mode}, success_msg)
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "Corriendo en Linux; el control de energía se aplica en la PC con Windows."}

        guid = plan_info["guid"]
        try:
            r = run_silent(['powercfg', '/s', guid], capture_output=True, text=True, errors='ignore')
            if r.returncode == 0:
                self._cached_power_plan = {
                    "status": "success",
                    "mode": target_mode,
                    "name": plan_info["name"],
                    "guid": guid
                }
                self._last_plan_check = time.time()
                temps = self.get_hardware_temperature()
                temp_c = temps.get("cpu") or temps.get("gpu")
                temp_str = f" La temperatura actual es de {temp_c}°C." if temp_c else ""
                msg = f"Activé el plan {plan_info['name']}.{temp_str}"
                state_mgr.emit_tool_call("set_power_plan", {"mode": target_mode, "name": plan_info['name']}, msg)
                return {
                    "status": "success",
                    "mode": target_mode,
                    "name": plan_info["name"],
                    "temp_c": temp_c,
                    "message": msg
                }
            else:
                return {"status": "error", "message": f"powercfg retornó error: {r.stderr.strip()}"}
        except Exception as e:
            return {"status": "error", "message": f"Error cambiando plan de energía: {e}"}

    def cool_down_pc(self) -> Dict[str, Any]:
        """Aplica el protocolo de refrigeración activa: pasa a Modo Frío (Economizador) y limpia procesos innecesarios"""
        if os.name != 'nt':
            success_msg = "¡Refrigeración activa en marcha, papá! Pasé la compu a Modo Frío (Economizador) para bajar el voltaje y cerré tareas de fondo."
            remote_res = self._remote_exec_if_linux("cool_down_pc", {}, success_msg)
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "Corriendo en Linux; la refrigeración se ejecuta en la PC con Windows."}

        # 1. Activar Modo Frío (Economizador)
        p_res = self.set_power_plan("eco")

        # 2. Optimizar procesos de fondo y memoria
        try:
            self.optimize_pc_gaming()
        except Exception:
            pass

        # 3. Leer temperatura post-refrigeración
        time.sleep(0.3)
        temps = self.get_hardware_temperature()
        temp_c = temps.get("cpu") or temps.get("gpu")
        temp_str = f" a {temp_c}°C" if temp_c else ""

        msg = f"¡Refrigeración activa aplicada, papá! Pasé la compu a Modo Frío (Economizador) para bajar el voltaje y cerré programas de fondo. El procesador está{temp_str}."
        state_mgr.emit_tool_call("cool_down_pc", {"temp_c": temp_c}, msg)
        return {
            "status": "success",
            "message": msg,
            "temp_c": temp_c,
            "power_plan": "eco",
            "plan_name": "Economizador / Modo Frío"
        }

    def get_system_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas completas de CPU, núcleos, RAM, discos, red y temperatura para telemetría"""
        cpu_percent = psutil.cpu_percent(interval=None)
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.virtual_memory()

        # Frecuencia de CPU
        cpu_freq_ghz = 0.0
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                cpu_freq_ghz = round(freq.current / 1000.0, 2)
        except Exception:
            pass

        # Temperatura y seguimiento de máximas
        temps = self.get_hardware_temperature()
        temp_c = temps.get("cpu") or temps.get("gpu")
        if temp_c:
            self.last_temp = temp_c
            if temp_c > self.max_session_temp:
                self.max_session_temp = temp_c

        # Evaluación de estado térmico
        if temp_c is not None:
            if temp_c < 55.0:
                thermal_status = "optimal"
                thermal_label = "Óptima (<55°C)"
            elif temp_c < 75.0:
                thermal_status = "warm"
                thermal_label = "Templada (55-75°C)"
            else:
                thermal_status = "alert"
                thermal_label = "Alerta Térmica (>75°C)"
        else:
            thermal_status = "unknown"
            thermal_label = "Desconocida"

        # Plan de energía activo
        power_plan = self.get_power_plan()

        # Red
        net_io = psutil.net_io_counters()
        net_sent_mb = round(net_io.bytes_sent / (1024**2), 1)
        net_recv_mb = round(net_io.bytes_recv / (1024**2), 1)

        disks = {}
        for d in ["C:\\", "D:\\", "E:\\"]:
            if os.path.exists(d):
                try:
                    usage = psutil.disk_usage(d)
                    disks[d[0]] = {
                        "total_gb": round(usage.total / (1024**3), 1),
                        "free_gb": round(usage.free / (1024**3), 1),
                        "percent_used": usage.percent
                    }
                except Exception:
                    pass

        if not disks and os.path.exists("/"):
            try:
                usage = psutil.disk_usage("/")
                disks["/"] = {
                    "total_gb": round(usage.total / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent_used": usage.percent
                }
            except Exception:
                pass

        hostname = os.getenv("COMPUTERNAME") or socket.gethostname()
        return {
            "status": "success",
            "hostname": hostname,
            "platform": "windows" if sys.platform == "win32" else "linux",
            "cpu_percent": cpu_percent,
            "per_cpu": per_cpu,
            "cpu_freq_ghz": cpu_freq_ghz,
            "cpu_count": psutil.cpu_count(logical=True),
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "ram_free_gb": round(mem.available / (1024**3), 1),
            "temp_c": temp_c,
            "cpu_temp_c": temps.get("cpu"),
            "gpu_temp_c": temps.get("gpu"),
            "hotspot_temp_c": temps.get("hotspot"),
            "max_temp_c": self.max_session_temp or temp_c,
            "thermal_status": thermal_status,
            "thermal_label": thermal_label,
            "power_plan": power_plan,
            "net_sent_mb": net_sent_mb,
            "net_recv_mb": net_recv_mb,
            "disks": disks
        }

    def switch_screen_view(self, view_name: str) -> Dict[str, Any]:
        """Cambia la vista en la pantalla del celular / HUD: 'face' (cara), 'orb' (control), 'telemetry' (recursos)"""
        v = view_name.lower().strip()
        target = "orb"
        if any(k in v for k in ["cara", "face", "rostro", "avatar"]):
            target = "face"
            msg = "Ahí te pongo la cara en pantalla completa, papá."
        elif any(k in v for k in ["recurso", "telemetria", "hardware", "cpu", "temperatura", "sistema", "memoria"]):
            target = "telemetry"
            msg = "Ahí te pongo la pantalla de recursos para ver cómo viene la compu."
        else:
            target = "orb"
            msg = "Listo che, volvemos a la pantalla de control."

        state_mgr.emit_view_switch(target)
        state_mgr.emit_tool_call("switch_screen_view", {"view": target}, msg)
        return {"status": "success", "message": msg, "active_view": target}

    def set_inactivity_stage(self, stage: str) -> Dict[str, Any]:
        """Cambia la etapa de reposo/animación en la pantalla del celular / HUD: 'mate', 'drowsy', 'sleeping', 'wake', 'idle'"""
        s = stage.lower().strip()
        state_mgr.emit_stage(s)
        if s == "mate":
            msg = "¡De una, fiera! Pongo la pava al fuego y me clavo unos buenos mates."
        elif s == "sleeping":
            msg = "Buenas noches, hermano. Descanso un rato los circuitos, cualquier cosa chiflame."
        elif s == "wake":
            msg = "¡Epa! ¡Acá estoy, despierto y al pie del cañón, papá!"
        elif s == "drowsy":
            msg = "Me está agarrando una modorra bárbara..."
        else:
            msg = "Modo activo restaurado."
        state_mgr.emit_tool_call("set_inactivity_stage", {"stage": s}, msg)
        return {"status": "success", "message": msg, "stage": s}

    def flip_camera(self, camera_mode: str = "toggle") -> Dict[str, Any]:
        """Cambia entre la cámara frontal (delantera) y la cámara trasera en el celular"""
        c = camera_mode.lower().strip()
        target = "toggle"
        if any(x in c for x in ["delantera", "frontal", "adelante", "user"]):
            target = "user"
            msg = "Listo che, te pongo la cámara delantera."
        elif any(x in c for x in ["trasera", "atras", "posterior", "environment"]):
            target = "environment"
            msg = "Cambiando a la cámara trasera, papá."
        else:
            target = "toggle"
            msg = "Ahí cambio de cámara."

        state_mgr._notify({
            "type": "flip_camera",
            "mode": target
        })
        state_mgr.emit_tool_call("flip_camera", {"mode": target}, msg)
        return {"status": "success", "message": msg, "mode": target}

    def get_weather(self, city: str = "Buenos Aires") -> Dict[str, Any]:
        """Consulta el clima y pronóstico actual en tiempo real para cualquier ciudad de Argentina o del mundo"""
        import urllib.request
        import urllib.parse
        import json
        
        coords = {
            "buenos aires": (-34.6118, -58.4173),
            "cordoba": (-31.4201, -64.1888),
            "rosario": (-32.9468, -60.6393),
            "mendoza": (-32.8908, -68.8272),
            "la plata": (-34.9214, -57.9545),
            "mar del plata": (-38.0055, -57.5562),
            "salta": (-24.7859, -65.4117),
            "tucuman": (-26.8241, -65.2226)
        }
        
        c_clean = city.lower().strip()
        lat, lon = coords.get(c_clean, (-34.6118, -58.4173))
        
        if c_clean not in coords:
            try:
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=es&format=json"
                req = urllib.request.Request(geo_url, headers={'User-Agent': 'CheAsistente/1.0'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    geo_data = json.loads(resp.read().decode('utf-8'))
                    if geo_data.get("results"):
                        lat = geo_data["results"][0]["latitude"]
                        lon = geo_data["results"][0]["longitude"]
            except Exception:
                pass

        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            req = urllib.request.Request(url, headers={'User-Agent': 'CheAsistente/1.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                w = data.get("current_weather", {})
                temp = round(w.get("temperature", 0))
                wind = round(w.get("windspeed", 0))
                code = w.get("weathercode", 0)
                
                desc = "cielo despejado"
                if code in [1, 2, 3]: desc = "parcialmente nublado"
                elif code in [45, 48]: desc = "con neblina"
                elif code in [51, 53, 55, 61, 63, 65]: desc = "con lluvias aisladas"
                elif code in [80, 81, 82]: desc = "con chaparrones"
                elif code in [95, 96, 99]: desc = "con tormenta eléctrica"

                msg = f"En {city.capitalize()} tenemos {temp} grados, {desc}, y viento a {wind} kilómetros por hora."
                state_mgr.emit_tool_call("get_weather", {"city": city}, msg)
                return {"status": "success", "city": city, "temperature": temp, "description": desc, "wind_speed": wind, "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"No pude consultar el clima: {e}"}

    def _get_argentine_soccer_fixture(self, query: str) -> str:
        """Consulta directamente la API deportiva de la Liga Argentina de Fútbol (ESPN) para datos exactos de partidos en paralelo"""
        import urllib.request
        import json
        from datetime import datetime, timedelta
        from concurrent.futures import ThreadPoolExecutor

        today = datetime.now()
        dates = [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(-1, 6)]

        def fetch_date(d: str):
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/arg.1/scoreboard?dates={d}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=2.5) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    evs = []
                    for ev in data.get("events", []):
                        name = ev.get("name", "")
                        dt_raw = ev.get("date", "")
                        tz_conv = self._format_utc_to_argentina(dt_raw)
                        fecha_bonita = tz_conv.get('display', dt_raw)
                        comp = ev.get("competitions", [{}])[0]
                        status = comp.get("status", {}).get("type", {}).get("description", "")
                        venue = comp.get("venue", {})
                        stadium = venue.get("fullName", "Estadio a confirmar")
                        city = venue.get("address", {}).get("city", "")
                        loc_vis = []
                        for team in comp.get("competitors", []):
                            t_name = team.get("team", {}).get("displayName", "")
                            ha = "Local" if team.get("homeAway") == "home" else "Visitante"
                            loc_vis.append(f"{t_name} ({ha})")
                        cond_str = " vs ".join(loc_vis)
                        evs.append({
                            "name": name,
                            "date_str": fecha_bonita,
                            "status": status,
                            "stadium": stadium,
                            "city": city,
                            "condition": cond_str
                        })
                    return evs
            except Exception:
                return []

        try:
            with ThreadPoolExecutor(max_workers=5) as ex:
                results = list(ex.map(fetch_date, dates))
            matches = [ev for sub in results for ev in sub]
        except Exception:
            matches = []

        q_lower = query.lower()
        ignore_words = {"contra", "quien", "juega", "partido", "partidos", "domingo", "sabado", "fecha", "hora", "cuando", "cancha", "estadio", "donde", "local", "visitante", "juegan"}
        keywords = [w for w in q_lower.split() if len(w) > 3 and w not in ignore_words]
        if keywords:
            filtered = [m for m in matches if any(k in m["name"].lower() for k in keywords)]
        else:
            filtered = matches

        target = filtered if filtered else matches[:15]
        if target:
            lines = [f"- {m['name']}: {m['date_str']}. Cancha/Estadio: {m['stadium']} en {m['city']}. Condición: {m['condition']} (Estado: {m['status']})" for m in target]
            return "Fixture Oficial de la Liga Argentina:\n" + "\n".join(lines)
        return ""

    def _get_historical_final_dates(self, query: str):
        """Detecta finales históricas para consultar la fecha y torneo exacto en ESPN."""
        q = (query or "").lower()
        finals = [
            ({"libertadores", "2023"}, "conmebol.libertadores", "20231104"),
            ({"fluminense", "2023"}, "conmebol.libertadores", "20231104"),
            ({"madrid", "2018"}, "conmebol.libertadores", "20181209"),
            ({"river", "boca", "2018"}, "conmebol.libertadores", "20181209"),
            ({"libertadores", "2018"}, "conmebol.libertadores", "20181209"),
            ({"qatar", "2022"}, "fifa.world", "20221218"),
            ({"mundial", "2022"}, "fifa.world", "20221218"),
            ({"francia", "2022"}, "fifa.world", "20221218"),
            ({"copa america", "2021"}, "conmebol.america", "20210710"),
            ({"maracana", "2021"}, "conmebol.america", "20210710"),
            ({"copa america", "2024"}, "conmebol.america", "20240714"),
            ({"colombia", "2024"}, "conmebol.america", "20240714"),
            ({"champions", "2024"}, "uefa.champions", "20240601"),
            ({"champions", "2023"}, "uefa.champions", "20230610"),
            ({"champions", "2022"}, "uefa.champions", "20220528"),
        ]
        for keywords, league, date_str in finals:
            if all(k in q for k in keywords):
                return league, date_str
        return None, None

    def get_soccer_match_sheet(self, team_query: str = "Boca", target_date = None, specific_league: str = None) -> str:
        """Obtiene la ficha técnica oficial de ESPN (resultado, goles, 11 titular oficial y suplentes) para cualquier equipo o final histórica."""
        import urllib.request
        import json
        import time
        from datetime import datetime, timedelta
        import re

        t0 = time.time()
        
        # Detect historical finals if not specified
        hist_lg, hist_dt = self._get_historical_final_dates(team_query)
        if hist_lg and not specific_league:
            specific_league = hist_lg
        if hist_dt and not target_date:
            target_date = hist_dt

        leagues = [specific_league] if specific_league else [
            'conmebol.libertadores', 'arg.1', 'conmebol.sudamericana', 'arg.copa',
            'fifa.world', 'conmebol.america', 'uefa.champions', 'esp.1', 'eng.1', 'ita.1'
        ]
        
        now = datetime.now()
        if target_date:
            if isinstance(target_date, str):
                clean_d = re.sub(r'[^\d]', '', target_date)
                if len(clean_d) == 8:
                    dates_to_check = [clean_d]
                else:
                    dates_to_check = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]
            else:
                dates_to_check = [
                    target_date.strftime("%Y%m%d"),
                    (target_date + timedelta(days=1)).strftime("%Y%m%d"),
                    (target_date - timedelta(days=1)).strftime("%Y%m%d"),
                ]
        else:
            dates_to_check = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]
            
        found_ev = None
        found_league = None
        
        # Clean keywords from team_query
        clean_team = team_query.lower()
        for w in ["formacion", "formación", "de", "del", "final", "vs", "contra", "alineacion", "alineación", "titulares", "once", "equipo", "partido"]:
            clean_team = clean_team.replace(w, " ")
        clean_team = clean_team.strip()
        if not clean_team:
            clean_team = team_query.lower()
        search_terms = [t for t in clean_team.split() if len(t) > 3]

        for d_str in dates_to_check:
            for lg in leagues:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d_str}"
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.81.0'})
                    with urllib.request.urlopen(req, timeout=3.0) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        for ev in data.get('events', []):
                            name = ev.get('name', '').lower()
                            if any(t in name for t in search_terms) or clean_team in name:
                                found_ev = ev
                                found_league = lg
                                break
                except Exception:
                    pass
                if found_ev:
                    break
            if found_ev:
                break
                
        if not found_ev:
            return ""
            
        event_id = found_ev.get('id')
        event_name = found_ev.get('name', '')
        
        url_sum = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{found_league}/summary?event={event_id}"
        try:
            req_sum = urllib.request.Request(url_sum, headers={'User-Agent': 'curl/7.81.0'})
            with urllib.request.urlopen(req_sum, timeout=3.5) as r:
                sum_data = json.loads(r.read().decode('utf-8'))
        except Exception:
            return ""
            
        header = sum_data.get('header', {})
        comp = header.get('competitions', [{}])[0]
        status = comp.get('status', {}).get('type', {}).get('description', '')
        
        teams = comp.get('competitors', found_ev.get('competitions', [{}])[0].get('competitors', []))
        score_lines = []
        for t in teams:
            score_lines.append(f"{t.get('team', {}).get('displayName', '')} {t.get('score', '0')}")
            
        goals = []
        for ev in sum_data.get('keyEvents', []):
            text = ev.get('text', '')
            clock = ev.get('clock', {}).get('displayValue', '')
            ev_type = ev.get('type', {}).get('text', '').lower()
            if 'goal' in ev_type:
                goals.append(f"{clock} {text}")
        if not goals:
            for d in sum_data.get('details', []):
                if d.get('type', {}).get('text') in ['Goal', 'Penalty - Scored']:
                    athlete = d.get('athletesInvolved', [{}])[0].get('displayName', '')
                    clock = d.get('clock', {}).get('displayValue', '')
                    team_g = d.get('team', {}).get('displayName', '')
                    if athlete:
                        goals.append(f"{athlete} ({clock}' - {team_g})")
                
        lineups_txt = []
        for roster in sum_data.get('rosters', []):
            tname = roster.get('team', {}).get('displayName', '')
            starters = [p.get('athlete', {}).get('displayName', '') for p in roster.get('roster', []) if p.get('starter', False)]
            subs = [p.get('athlete', {}).get('displayName', '') for p in roster.get('roster', []) if not p.get('starter', False)]
            if starters:
                lineups_txt.append(f"• 11 Titular oficial de {tname} ({len(starters)} jugadores):\n  {', '.join(starters)}")
            if subs:
                lineups_txt.append(f"• Suplentes de {tname}: {', '.join(subs[:8])}...")
                
        elapsed = time.time() - t0
        report = [f"[FICHA TÉCNICA OFICIAL EN VIVO - ESPN ({elapsed:.2f}s)]:"]
        report.append(f"- Partido: {event_name} (Torneo: {found_league})")
        ev_date_raw = comp.get('date', '')
        if ev_date_raw:
            date_conv = self._format_utc_to_argentina(ev_date_raw)
            if date_conv.get('display'):
                report.append(f"- Fecha y Hora oficial: {date_conv['display']}")
        report.append(f"- Estado y Marcador: {status} | {' vs '.join(score_lines)}")
        if goals:
            report.append(f"- Goles del partido: {'; '.join(goals)}")
        if lineups_txt:
            report.append("- Formaciones titulares oficiales:\n  " + '\n  '.join(lineups_txt))
            
        state_mgr.emit_tool_call("get_soccer_match_sheet", {"team": team_query, "date": dates_to_check[0]}, f"Ficha oficial ESPN: {event_name}")
        return "\n".join(report)

    def _format_utc_to_argentina(self, utc_time_str: str) -> Dict[str, Any]:
        """Convierte de forma infalible una fecha/hora UTC (ISO) a hora oficial de Argentina (UTC-3),
        calculando la fecha local, hora, día de la semana y estado relativo ('HOY', 'MAÑANA', 'AYER', etc.)."""
        from datetime import datetime, timezone, timedelta
        import re

        if not utc_time_str:
            return {}
        
        clean_str = re.sub(r'\.\d+', '', str(utc_time_str)).replace('Z', '+00:00')
        if '+' not in clean_str and '-' not in clean_str[10:]:
            clean_str += '+00:00'
        
        try:
            dt_utc = datetime.fromisoformat(clean_str)
        except Exception:
            return {}
            
        tz_arg = timezone(timedelta(hours=-3))
        dt_arg = dt_utc.astimezone(tz_arg)
        
        now_arg = datetime.now(tz_arg)
        today_arg = now_arg.date()
        match_date = dt_arg.date()
        
        dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        
        dia_nombre = dias_semana[dt_arg.weekday()]
        mes_nombre = meses[dt_arg.month]
        hora_str = dt_arg.strftime("%H:%M")
        
        days_diff = (match_date - today_arg).days
        
        if days_diff == 0:
            relative_day = "HOY"
            display = f"HOY {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == 1:
            relative_day = "MAÑANA"
            display = f"MAÑANA {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == -1:
            relative_day = "AYER"
            display = f"AYER {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == 2:
            relative_day = f"Pasado mañana ({dia_nombre})"
            display = f"Pasado mañana {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff < 0:
            relative_day = f"El {dia_nombre} pasado"
            display = f"El {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        else:
            relative_day = f"El {dia_nombre}"
            display = f"El {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
            
        return {
            "dt_arg": dt_arg,
            "date_str": dt_arg.strftime("%Y-%m-%d"),
            "time_str": hora_str,
            "day_name": dia_nombre,
            "month_name": mes_nombre,
            "relative_day": relative_day,
            "display": display,
            "is_today": days_diff == 0,
            "is_tomorrow": days_diff == 1,
            "is_yesterday": days_diff == -1,
            "days_diff": days_diff
        }

    def _get_fotmob_boca_data(self) -> Dict[str, Any]:
        """Extrae de FotMob en tiempo real (vía SSR Next.js __NEXT_DATA__) el próximo partido y último partido."""
        import urllib.request
        import json
        import re

        url = "https://www.fotmob.com/teams/10077/overview/boca-juniors"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as r:
                html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">({.*?})</script>', html)
            if not m:
                return {}
            data = json.loads(m.group(1))
            team_data = data.get('props', {}).get('pageProps', {}).get('fallback', {}).get('team-10077', {})
            overview = team_data.get('overview', {})
            
            next_m = overview.get('nextMatch', {})
            next_info = None
            if next_m:
                utc = next_m.get('status', {}).get('utcTime', '')
                tz_conv = self._format_utc_to_argentina(utc)
                home = next_m.get('home', {}).get('name', '')
                away = next_m.get('away', {}).get('name', '')
                is_home = "Boca" in home
                rival = away if is_home else home
                cond = "Local (en La Bombonera)" if is_home else f"Visitante (en cancha de {rival})"
                tournament = next_m.get('tournament', {}).get('name', 'Torneo Oficial')
                next_info = {
                    "id": next_m.get('id'),
                    "pageUrl": next_m.get('pageUrl'),
                    "rival": rival,
                    "condition": cond,
                    "tournament": tournament,
                    "display_date": tz_conv.get('display', ''),
                    "relative_day": tz_conv.get('relative_day', ''),
                    "is_today": tz_conv.get('is_today', False),
                    "is_tomorrow": tz_conv.get('is_tomorrow', False),
                    "time_str": tz_conv.get('time_str', ''),
                    "utc_time": utc
                }
                
            last_m = overview.get('lastMatch', {})
            last_info = None
            if last_m:
                utc = last_m.get('status', {}).get('utcTime', '')
                tz_conv = self._format_utc_to_argentina(utc)
                home = last_m.get('home', {}).get('name', '')
                away = last_m.get('away', {}).get('name', '')
                home_score = last_m.get('home', {}).get('score', 0)
                away_score = last_m.get('away', {}).get('score', 0)
                score_str = last_m.get('status', {}).get('scoreStr', f"{home_score} - {away_score}")
                tournament = last_m.get('tournament', {}).get('name', 'Torneo Oficial')
                last_info = {
                    "id": last_m.get('id'),
                    "pageUrl": last_m.get('pageUrl'),
                    "match": f"{home} {score_str} {away}",
                    "home": home,
                    "away": away,
                    "score": score_str,
                    "tournament": tournament,
                    "display_date": tz_conv.get('display', ''),
                    "relative_day": tz_conv.get('relative_day', ''),
                    "utc_time": utc
                }
                
            return {
                "next_match": next_info,
                "last_match": last_info
            }
        except Exception as e:
            log_warning(f"Error consultando FotMob overview: {e}")
            return {}

    def _get_fotmob_match_lineup(self, page_url: str) -> Dict[str, Any]:
        """Extrae la formación oficial de un partido en FotMob (titulares, suplentes, técnico, goles)."""
        import urllib.request
        import json
        import re

        if not page_url:
            return {}
        full_url = f"https://www.fotmob.com{page_url}" if page_url.startswith('/') else page_url
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
        try:
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">({.*?})</script>', html)
            if not m:
                return {}
            data = json.loads(m.group(1))
            content = data.get('props', {}).get('pageProps', {}).get('content', {})
            lineup_data = content.get('lineup', {})
            match_facts = content.get('matchFacts', {})
            
            lineup_type = lineup_data.get('lineupType', '')
            source = lineup_data.get('source', '')
            is_confirmed = (lineup_type == 'standard' or source in ['optaSdapi', 'official']) and lineup_type != 'lastStarting11'
            
            home = lineup_data.get('homeTeam', {})
            away = lineup_data.get('awayTeam', {})
            boca = home if "Boca" in home.get('name', '') else (away if "Boca" in away.get('name', '') else home)
            
            starters = [f"#{p.get('shirtNumber', p.get('shirt', ''))} {p.get('name', '')}" for p in boca.get('starters', [])]
            subs = [f"#{p.get('shirtNumber', p.get('shirt', ''))} {p.get('name', '')}" for p in boca.get('subs', [])]
            coach = boca.get('coach', {}).get('name', '')
            formation = boca.get('formation', '')
            
            goals = []
            events = match_facts.get('events', {}).get('events', [])
            for ev in events:
                if ev.get('type') == 'Goal':
                    player = ev.get('player', {}).get('name', '') or ev.get('nameStr', '')
                    time_m = ev.get('time', '')
                    score = ev.get('newScore', [])
                    score_txt = f"({score[0]}-{score[1]})" if score else ""
                    goals.append(f"{player} {time_m}' {score_txt}".strip())
                    
            return {
                "team": boca.get('name', 'Boca Juniors'),
                "formation": formation,
                "coach": coach,
                "starters": starters,
                "subs": subs,
                "goals": goals,
                "is_confirmed": is_confirmed,
                "lineup_type": lineup_type,
                "source": source
            }
        except Exception as e:
            log_warning(f"Error consultando FotMob lineup: {e}")
            return {}

    def _get_boca_probable_lineup(self) -> str:
        """Extrae de Olé, TyC o coberturas de la práctica de Ezeiza el 11 probable si se filtró en las noticias."""
        import urllib.request
        import xml.etree.ElementTree as ET
        import re
        import html

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            url_news = "https://news.google.com/rss/search?q=Boca+Juniors+posible+formacion+OR+probables+titulares+OR+equipo+practica&hl=es-419&gl=AR&ceid=AR:es-419"
            req = urllib.request.Request(url_news, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5) as r:
                root = ET.fromstring(r.read())
                for item in root.findall(".//item")[:5]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    clean_title = re.sub(r'\s*-\s*[^-]+$', '', title).strip()
                    desc = item.find("description").text if item.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if any(k in clean_title.lower() for k in ["formación", "formacion", "titulares", "once", "equipo"]):
                        if clean_desc and len(clean_desc) > 30:
                            return f"Novedad de Ezeiza según la prensa: '{clean_title}'. {clean_desc[:180]}"
                        return f"Novedad de Ezeiza: '{clean_title}'"
        except Exception as e:
            log_warning(f"Error consultando noticias de 11 probable: {e}")
        return ""

    def get_boca_juniors_info(self, topic: str = "todo") -> Dict[str, Any]:
        """Obtiene información deportiva oficial y en tiempo real de Boca Juniors: próximo partido (fecha, hora argentina, estadio, torneo) desde FotMob, formación oficial confirmada, últimos resultados y actualidad de Ezeiza."""
        import os
        import urllib.request
        import json
        import xml.etree.ElementTree as ET
        import time
        import re
        import html
        from datetime import datetime, timedelta

        report = []
        
        # 1. Consulta en tiempo real a FotMob (Fixture + Último partido + Planilla oficial)
        fotmob_data = self._get_fotmob_boca_data()
        next_m = fotmob_data.get("next_match")
        last_m = fotmob_data.get("last_match")

        if next_m:
            report.append(
                f"PRÓXIMO COMPROMISO CONFIRMADO DE BOCA (Fuente oficial en vivo: FotMob):\n"
                f"- Cuándo: {next_m['display_date']}\n"
                f"- Rival: {next_m['rival']}\n"
                f"- Condición y Estadio: {next_m['condition']}\n"
                f"- Torneo: {next_m['tournament']}"
            )
            if next_m.get('pageUrl'):
                next_lu = self._get_fotmob_match_lineup(next_m['pageUrl'])
                if next_lu.get('starters'):
                    if next_lu.get('is_confirmed'):
                        coach_txt = f" - DT {next_lu['coach']}" if next_lu.get('coach') else ""
                        report.append(
                            f"FORMACIÓN TITULAR OFICIAL CONFIRMADA PARA ESTE PARTIDO (Planilla oficial - Esquema {next_lu.get('formation', '4-3-3')}{coach_txt}):\n"
                            f"• Titulares: {', '.join(next_lu['starters'])}\n"
                            f"• Suplentes: {', '.join(next_lu['subs'][:8])}..."
                        )
                    else:
                        probable_11 = self._get_boca_probable_lineup()
                        ref_txt = f"\n• Último 11 de referencia que jugó el partido anterior:\n  {', '.join(next_lu['starters'])}" if next_lu.get('starters') else ""
                        if probable_11:
                            prob_info = f"• Novedades de la práctica / 11 rumoreado:\n  {probable_11}"
                        else:
                            prob_info = "• El cuerpo técnico aún no definió públicamente el 11 en los entrenamientos."
                        report.append(
                            f"ESTADO DE LA FORMACIÓN DEL PRÓXIMO PARTIDO:\n"
                            f"La planilla oficial todavía NO fue confirmada (se entrega en el vestuario 1 hora antes del partido).\n"
                            f"{prob_info}{ref_txt}"
                        )

        if last_m:
            report.append(
                f"ÚLTIMO PARTIDO JUGADO DE BOCA (FotMob):\n"
                f"- Resultado: {last_m['match']}\n"
                f"- Torneo: {last_m['tournament']}\n"
                f"- Disputado: {last_m['display_date']}"
            )
            if last_m.get('pageUrl'):
                last_lu = self._get_fotmob_match_lineup(last_m['pageUrl'])
                if last_lu.get('goals'):
                    report.append(f"• Goles del último partido: {', '.join(last_lu['goals'])}")
                if last_lu.get('starters'):
                    coach_txt = f" - DT {last_lu['coach']}" if last_lu.get('coach') else ""
                    report.append(
                        f"• 11 Titular que jugó ese partido (Esquema {last_lu.get('formation', '')}{coach_txt}):\n"
                        f"  {', '.join(last_lu['starters'])}"
                    )

        # 2. Novedades de Ezeiza (Google News RSS Argentina)
        try:
            url_news = "https://news.google.com/rss/search?q=Boca+Juniors+posible+formacion+OR+alineacion+OR+titulares&hl=es-419&gl=AR&ceid=AR:es-419"
            req_news = urllib.request.Request(url_news, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_news, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                items = root.findall(".//item")
                notes = []
                for item in items[:3]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    clean_title = re.sub(r'\s*-\s*[^-]+$', '', title).strip()
                    desc = item.find("description").text if item.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_title:
                        notes.append(f"• Titular: {clean_title} | Detalle: {clean_desc[:140]}")
                if notes:
                    report.append("REPORTES DE LA PRÁCTICA EN EZEIZA:\n" + "\n".join(notes))
        except Exception:
            pass

        # 3. Instrucción crítica de fechas y personalidad
        instruction = (
            "[REGLA CRÍTICA DE FECHA Y HORARIO]:\n"
            "La fecha y hora indicada arriba YA ESTÁ CONVERTIDA AL HUSO HORARIO DE ARGENTINA (UTC-3).\n"
            "Si el próximo partido dice 'HOY' (ej: 'HOY Viernes 11 de septiembre a las 21:30 hs'), respondé con total seguridad que Boca juega HOY. NUNCA digas que juega mañana.\n\n"
            "[INSTRUCCIÓN CRÍTICA DE RESPUESTA Y PERTINENCIA]:\n"
            "- Respondé ÚNICAMENTE a lo que te preguntó el usuario.\n"
            "- Si te preguntan cuándo juega Boca, contra quién, la hora o el estadio: hablá del próximo partido confirmado.\n"
            "- Si te preguntan cómo forma Boca, quiénes juegan o la formación del próximo partido antes de que esté confirmada la planilla oficial (1 hora antes): explicá que la formación oficial sale 1 hora antes del partido en el vestuario, comentá las novedades de las prácticas o el 11 de referencia, y jamás inventes nombres de jugadores.\n"
            "- Si te preguntan por cómo salió el partido anterior: da el resultado exacto, los goles y quiénes jugaron.\n"
            "- Cero citas a diarios o páginas web: hablá en primera persona como el compinche xeneize más apasionado.\n"
            "- Respondé con pasión de potrero, al hueso y con ritmo oral (generalmente entre 2 y 3 oraciones)."
        )
        report.append(instruction)

        final_text = "\n\n".join(report)
        state_mgr.emit_tool_call("get_boca_juniors_info", {"topic": topic}, "Datos de Boca Juniors (FotMob + Ezeiza)")
        return {"status": "success", "results": final_text}

    def get_soccer_info(self, query: str = "", team: str = "", date: str = "") -> Dict[str, Any]:
        """Consulta datos de fútbol (fichas técnicas, formaciones oficiales, goles, resultados históricos o recientes) de cualquier equipo o final."""
        clean_q = (query or team or "").strip()
        
        # 1. Finales históricas detectadas
        hist_lg, hist_dt = self._get_historical_final_dates(clean_q)
        if hist_lg and hist_dt:
            sheet = self.get_soccer_match_sheet(team_query=clean_q, target_date=hist_dt, specific_league=hist_lg)
            if sheet:
                state_mgr.emit_tool_call("get_soccer_info", {"query": clean_q, "date": hist_dt}, "Ficha histórica ESPN")
                return {"status": "success", "results": sheet}

        # 2. Si es Boca y piden próximo o último partido
        lower_q = clean_q.lower()
        if any(b in lower_q for b in ["boca", "xeneize", "bombonera"]) and not any(yr in lower_q for yr in ["2024", "2023", "2022", "2021", "2020", "2018", "2007", "2000"]):
            return self.get_boca_juniors_info(clean_q)

        # 3. Match sheet de ESPN para cualquier equipo / fecha
        sheet = self.get_soccer_match_sheet(team_query=clean_q, target_date=date if date else None)
        if sheet:
            state_mgr.emit_tool_call("get_soccer_info", {"query": clean_q, "date": date}, "Ficha oficial ESPN")
            return {"status": "success", "results": sheet}

        # 4. Fallback a búsqueda web
        return self.search_web(clean_q)

    def search_web(self, query: str = "") -> Dict[str, Any]:
        """Busca en internet información en tiempo real: próximos partidos, resultados deportivos, formaciones oficiales, noticias de hoy, etc."""
        import urllib.request
        import urllib.parse
        import xml.etree.ElementTree as ET
        import re
        import html
        import json
        from datetime import datetime, timedelta

        clean_q = (query or "").strip()
        if not clean_q:
            return {"status": "empty", "results": "No se especificó una consulta de búsqueda."}
        lower_q = clean_q.lower()
        now = datetime.now()

        # Si piden explícitamente y únicamente el próximo partido de Boca (cuándo juega Boca)
        is_fixture_request = any(k in lower_q for k in ["cuándo juega", "cuando juega", "a qué hora juega", "a que hora juega", "contra quién juega", "contra quien juega", "próximo partido", "proximo partido", "fixture de"])
        is_news_or_coach = any(k in lower_q for k in ["dt", "técnico", "tecnico", "entrenador", "presidente", "noticia", "refuerzo", "fichaje", "jugador", "quién", "quien", "por qué", "porque", "formación", "formacion", "titulares", "alineación", "alineacion"])

        if is_fixture_request and not is_news_or_coach:
            if any(k in lower_q for k in ["boca", "xeneize", "bombonera"]) and "superclásico" not in lower_q and "superclasico" not in lower_q:
                boca_res = self.get_boca_juniors_info(clean_q)
                return boca_res
            if any(k in lower_q for k in ["river", "superclásico", "superclasico", "racing", "san lorenzo", "independiente", "velez", "huracan"]):
                try:
                    soccer_data = self._get_argentine_soccer_fixture(clean_q)
                    if soccer_data:
                        state_mgr.emit_tool_call("search_web", {"query": clean_q}, "Fixture oficial consultado")
                        return {"status": "success", "results": soccer_data}
                except Exception:
                    pass

        results = []

        # 1. Fútbol: Partidos, resultados pasados, fichas técnicas y formaciones titulares oficiales (ESPN / FotMob)
        hist_lg, hist_dt = self._get_historical_final_dates(clean_q)
        is_historic = any(yr in lower_q for yr in ["2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2007", "2000", "año pasado", "ano pasado", "año anterior"])
        is_soccer = hist_lg is not None or any(w in lower_q for w in [
            "partido", "jugó", "jugo", "juega", "boca", "river", "san pablo", "sao paulo",
            "racing", "independiente", "san lorenzo", "sudamericana", "libertadores", "mundial",
            "formación", "formacion", "alineación", "alineacion", "titulares", "once", "11",
            "quiénes jugaron", "quienes jugaron", "cómo formó", "como formo", "gol", "goles", "resultado"
        ])

        if is_soccer:
            # Si es una final histórica detectada, consultar inmediatamente la ficha oficial de ESPN
            if hist_lg and hist_dt:
                try:
                    sheet = self.get_soccer_match_sheet(clean_q, target_date=hist_dt, specific_league=hist_lg)
                    if sheet:
                        results.append(sheet)
                except Exception as e:
                    log_warning(f"Error consultando final histórica en search_web: {e}")

            elif any(k in lower_q for k in ["boca", "xeneize"]) and not is_historic:
                try:
                    fotmob_data = self._get_fotmob_boca_data()
                    is_last_match_q = any(k in lower_q for k in ["último", "ultimo", "pasado", "ayer", "anoche", "cómo salió", "como salio", "resultado", "ganó", "gano", "perdió", "perdio", "goles"])
                    is_next_match_q = any(k in lower_q for k in ["hoy", "esta noche", "próximo", "proximo", "cuándo", "cuando", "a qué hora", "a que hora"])

                    if (is_last_match_q or not is_next_match_q) and fotmob_data.get("last_match"):
                        lm = fotmob_data["last_match"]
                        lm_txt = [f"[FICHA OFICIAL DE FOTMOB - ÚLTIMO PARTIDO]:"]
                        lm_txt.append(f"- Partido: {lm['match']} ({lm['tournament']})")
                        lm_txt.append(f"- Disputado: {lm['display_date']}")
                        if lm.get('pageUrl'):
                            lu = self._get_fotmob_match_lineup(lm['pageUrl'])
                            if lu.get('goals'):
                                lm_txt.append(f"- Goles: {', '.join(lu['goals'])}")
                            if lu.get('starters'):
                                coach_t = f" - DT {lu['coach']}" if lu.get('coach') else ""
                                lm_txt.append(f"- 11 Titular oficial (Esquema {lu.get('formation', '')}{coach_t}):\n  {', '.join(lu['starters'])}")
                            if lu.get('subs'):
                                lm_txt.append(f"- Suplentes: {', '.join(lu['subs'][:8])}...")
                        results.append("\n".join(lm_txt))

                    if (is_next_match_q or "formación" in lower_q or "alineación" in lower_q) and fotmob_data.get("next_match"):
                        nm = fotmob_data["next_match"]
                        nm_txt = [f"[FICHA OFICIAL DE FOTMOB - PRÓXIMO PARTIDO]:"]
                        nm_txt.append(f"- Partido: Boca Juniors vs {nm['rival']} ({nm['tournament']})")
                        nm_txt.append(f"- Cuándo: {nm['display_date']} ({nm['condition']})")
                        if nm.get('pageUrl'):
                            lu = self._get_fotmob_match_lineup(nm['pageUrl'])
                            if lu.get('starters'):
                                if lu.get('is_confirmed'):
                                    coach_t = f" - DT {lu['coach']}" if lu.get('coach') else ""
                                    nm_txt.append(f"- 11 Titular oficial confirmado (Esquema {lu.get('formation', '')}{coach_t}):\n  {', '.join(lu['starters'])}")
                                else:
                                    prob_11 = self._get_boca_probable_lineup()
                                    if prob_11:
                                        nm_txt.append(f"- Formación: Planilla oficial pendiente (sale 1 hora antes). Novedades de Ezeiza: {prob_11}")
                                    else:
                                        nm_txt.append("- Formación: Planilla oficial pendiente (se confirma 1 hora antes en el vestuario).")
                            if lu.get('subs') and lu.get('is_confirmed'):
                                nm_txt.append(f"- Suplentes: {', '.join(lu['subs'][:8])}...")
                        results.append("\n".join(nm_txt))
                except Exception as e:
                    log_warning(f"Error consultando FotMob en search_web: {e}")

            else:
                team_match = "Boca"
                if "river" in lower_q: team_match = "River"
                elif "racing" in lower_q: team_match = "Racing"
                elif "san lorenzo" in lower_q: team_match = "San Lorenzo"
                elif "independiente" in lower_q: team_match = "Independiente"
                elif "argentina" in lower_q: team_match = "Argentina"
                elif "francia" in lower_q or "france" in lower_q: team_match = "Francia"
                elif "real madrid" in lower_q: team_match = "Real Madrid"
                elif "fluminense" in lower_q: team_match = "Fluminense"

                dias_semana = {
                    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
                }
                target_dt = None
                for d_nom, d_num in dias_semana.items():
                    if f"el {d_nom}" in lower_q or d_nom in lower_q:
                        diff = (now.weekday() - d_num) % 7
                        if diff == 0 and "pasado" in lower_q:
                            diff = 7
                        target_dt = now - timedelta(days=diff)
                        break
                if not target_dt:
                    if "ayer" in lower_q or "anoche" in lower_q:
                        target_dt = now - timedelta(days=1)
                    elif "el finde" in lower_q or "el fin de semana" in lower_q:
                        diff = (now.weekday() - 6) % 7
                        if diff == 0:
                            diff = 7
                        target_dt = now - timedelta(days=diff)

                try:
                    sheet = self.get_soccer_match_sheet(team_match, target_dt)
                    if sheet:
                        results.append(sheet)
                except Exception:
                    pass

        # 2. Google News RSS Argentina (noticias ultra frescas en tiempo real)
        try:
            url_news = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_q)}&hl=es-419&gl=AR&ceid=AR:es-419"
            req_news = urllib.request.Request(url_news, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req_news, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                items = root.findall(".//item")
                for it in items[:4]:
                    t = it.find("title").text if it.find("title") is not None else ""
                    clean_t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
                    desc = it.find("description").text if it.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_t:
                        results.append(f"[NOTICIA RECIENTE]: {clean_t} | Detalle: {clean_desc[:250]}")
        except Exception:
            pass

        # 3. Bing News RSS (titulares en tiempo real, marcadores de partidos y coberturas sin bloqueo)
        try:
            url_bing = f"https://www.bing.com/news/search?q={urllib.parse.quote(clean_q)}&format=rss"
            req_bing = urllib.request.Request(url_bing, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req_bing, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                raw_items = root.findall(".//item")
                prio_words = ['ganó', 'gano', 'venció', 'vencio', 'perdió', 'perdio', 'empató', 'empato', 'goles', 'gol', '1-0', '1 a 0', '2-0', '2-1', '0-0', 'triunfo', 'derrota', 'asumió', 'asumio', 'renunció', 'renuncio', 'interino']
                def _prio(it):
                    t_str = (it.find('title').text or '').lower()
                    d_str = (it.find('description').text or '').lower()
                    return -sum(1 for w in prio_words if w in t_str or w in d_str)
                sorted_items = sorted(raw_items, key=_prio)
                for it in sorted_items[:4]:
                    t = it.find("title").text if it.find("title") is not None else ""
                    clean_t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
                    desc = it.find("description").text if it.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_t:
                        results.append(f"[INFORMACIÓN WEB EN VIVO]: {clean_t} | Detalle: {clean_desc[:250]}")
        except Exception:
            pass

        # 4. Wikipedia para datos enciclopédicos, biografías o eventos históricos pasados
        if is_historic or any(w in lower_q for w in ["quién es", "quien es", "qué es", "que es", "historia", "biografía", "biografia", "presidente", "gobernador", "ministro", "mundial", "final"]) or len(results) < 2:
            try:
                url_wiki = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&utf8=&format=json"
                req_wiki = urllib.request.Request(url_wiki, headers={"User-Agent": "TitanAssistant/1.0 (exevaz27)"})
                with urllib.request.urlopen(req_wiki, timeout=3.0) as r_w:
                    d_w = json.loads(r_w.read().decode("utf-8"))
                    s_items = d_w.get("query", {}).get("search", [])
                    if s_items:
                        top_it = s_items[0]
                        w_title = top_it.get("title", "")
                        url_ext = f"https://es.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(w_title)}&format=json"
                        req_ext = urllib.request.Request(url_ext, headers={"User-Agent": "TitanAssistant/1.0 (exevaz27)"})
                        with urllib.request.urlopen(req_ext, timeout=3.0) as r_ext:
                            d_ext = json.loads(r_ext.read().decode("utf-8"))
                            pages = d_ext.get("query", {}).get("pages", {})
                            for pid, pdata in pages.items():
                                ext = pdata.get("extract", "")
                                clean_ext = ext.replace('\u200b', '').strip()
                                if clean_ext:
                                    results.append(f"[ENCICLOPEDIA WIKIPEDIA - {w_title}]:\n{clean_ext[:500]}")
            except Exception:
                pass

        if results:
            result_text = "\n\n".join(results)
            state_mgr.emit_tool_call("search_web", {"query": clean_q}, f"Búsqueda web completada: {clean_q}")
            return {"status": "success", "results": result_text}
        return {"status": "empty", "results": "No se encontraron resultados específicos en la web."}
    def close_existing_youtube_windows(self):
        """Cierra cualquier ventana previa de YouTube en Brave para que las canciones no se reproduzcan encima."""
        try:
            import ctypes
            from ctypes import wintypes
            import psutil
            user32 = ctypes.windll.user32
            curr = 0
            while True:
                curr = user32.FindWindowExW(0, curr, "Chrome_WidgetWin_1", None)
                if not curr:
                    break
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(curr, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    if "brave" in p.name().lower():
                        length = user32.GetWindowTextLengthW(curr)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(curr, buf, length + 1)
                            t = buf.value.lower()
                            if "youtube" in t or "brave" in t:
                                user32.PostMessageW(curr, 0x0010, 0, 0)  # WM_CLOSE
                except Exception:
                    pass
        except Exception:
            pass

    def play_youtube(self, query: str) -> Dict[str, Any]:
        """Busca y reproduce un video o canción en YouTube directamente en el navegador Brave en primer plano, reemplazando cualquier reproducción anterior."""
        import urllib.request
        import urllib.parse
        import re
        import webbrowser
        import os
        import subprocess
        import ctypes
        import time

        raw_q = query.strip()
        clean_q = raw_q

        # 1. Limpieza de saludos, nombres del asistente y prefijos
        prefixes = [
            "cuautitlan", "cuautitlán", "ehu titan", "ehu titán", "eu titan", "eu titán",
            "titan", "titán", "el titan", "el titán", "che titan", "che titán", "che", "eu", "eh", "ey",
            "pone en youtube", "poné en youtube", "pon en youtube", "poneme en youtube", "ponéme en youtube",
            "reproducir en youtube", "reproduci en youtube", "reproducí en youtube", "reproducime en youtube",
            "buscar en youtube", "busca en youtube", "buscá en youtube", "buscame en youtube", "abrir youtube", "abri youtube",
            "pone", "poné", "pon", "poneme", "ponéme", "reproducir", "reproduci", "reproducí", "reproducime",
            "toca", "tocá", "tocame", "tocáme", "escuchar", "escucha", "buscar", "busca", "buscá", "abrir", "abri",
            "poner", "cambia a", "cambiá a", "pone otra cancion", "poné otra cancion"
        ]

        low_q = clean_q.lower()
        # Limpiar prefijos de manera iterativa por si se combinan ("che titán pon...")
        changed = True
        while changed:
            changed = False
            for p in prefixes:
                if low_q.startswith(p + " "):
                    clean_q = clean_q[len(p):].strip()
                    low_q = clean_q.lower()
                    changed = True
                    break
                elif low_q == p:
                    clean_q = ""
                    low_q = ""
                    break

        # 2. Limpieza de sufijos ("en youtube", etc.)
        for suffix in ["en youtube", "de youtube", "por youtube", "youtube"]:
            if low_q.endswith(" " + suffix):
                clean_q = clean_q[:-len(suffix)-1].strip()
                low_q = clean_q.lower()
            elif low_q == suffix:
                clean_q = ""
                low_q = ""
                break

        # 3. Limpieza de rellenos iniciales ("el tema de", "la cancion de", etc.)
        fillers = [
            "el tema de", "el tema del", "la cancion de", "la canción de", "la cancion del", "la canción del",
            "el video de", "el video del", "el videoclip de", "el videoclip del",
            "la musica de", "la música de", "la musica del", "la música del",
            "un tema de", "un tema del", "una cancion de", "una canción de", "una cancion del", "una canción del",
            "el tema", "la cancion", "la canción", "el video", "la musica", "la música",
            "un tema", "una cancion", "una canción", "del", "de", "el", "la"
        ]
        for f in fillers:
            if low_q.startswith(f + " "):
                clean_q = clean_q[len(f):].strip()
                low_q = clean_q.lower()
                break

        if not clean_q:
            clean_q = raw_q

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Poniendo en YouTube: {clean_q}")

        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_q)}"
        target_url = search_url

        try:
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "es-419,es;q=0.9,en;q=0.8"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                html_content = response.read().decode("utf-8", errors="ignore")
                # 1ra opción: buscar videoId dentro de videoRenderer (videos musicales reales, descartando anuncios/noticias)
                video_ids = re.findall(r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', html_content)
                if not video_ids:
                    video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html_content)
                if not video_ids:
                    video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html_content)
                
                if video_ids:
                    selected_id = video_ids[0]
                    target_url = f"https://www.youtube.com/watch?v={selected_id}&autoplay=1"
                    log_info(f"Video ID de YouTube resuelto con éxito: {selected_id}")
        except Exception as e:
            log_warning(f"Error resolviendo ID de YouTube ({clean_q}): {e}")

        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "play_youtube",
                {"query": clean_q, "url": target_url},
                f"Reproduciendo '{clean_q}' en YouTube en la compu."
            )
            if remote_res:
                return remote_res

        # 4. REEMPLAZO LIMPIO: cortar sonido anterior y cerrar ventana previa de YouTube
        self.close_existing_youtube_windows()
        time.sleep(0.35)

        brave_paths = [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
        ]

        opened = False
        brave_args = f'--new-window --autoplay-policy=no-user-gesture-required --enable-features=HardwareMediaKeyHandling "{target_url}"'

        for b_path in brave_paths:
            if os.path.exists(b_path):
                try:
                    # ShellExecuteW con SW_SHOWNORMAL (1) fuerza a Windows a mostrar la ventana en primer plano
                    ret = ctypes.windll.shell32.ShellExecuteW(
                        None, "open", b_path, brave_args, os.path.dirname(b_path), 1
                    )
                    if ret > 32:
                        opened = True
                        log_info(f"YouTube abierto en primer plano con Brave (ShellExecuteW): {target_url}")
                        break
                except Exception as b_err:
                    log_warning(f"Error abriendo con ShellExecuteW ({b_path}): {b_err}")

                try:
                    popen_silent(
                        [b_path, "--new-window", "--autoplay-policy=no-user-gesture-required", "--enable-features=HardwareMediaKeyHandling", target_url],
                        cwd=os.path.dirname(b_path)
                    )
                    opened = True
                    log_info(f"YouTube abierto con Brave (popen_silent): {target_url}")
                    break
                except Exception as b_err:
                    log_warning(f"Error abriendo con Brave ({b_path}): {b_err}")

        # Asegurar que el audio de la nueva canción esté habilitado y no herede mute
        def _unmute_watcher():
            import time
            for _ in range(12):
                time.sleep(0.5)
                try:
                    from pycaw.pycaw import AudioUtilities
                    for s in AudioUtilities.GetAllSessions():
                        if s.Process and "brave" in s.Process.name().lower():
                            if s.SimpleAudioVolume.GetMute():
                                s.SimpleAudioVolume.SetMute(0, None)
                except Exception:
                    pass
        import threading
        threading.Thread(target=_unmute_watcher, daemon=True).start()

        if not opened:
            try:
                webbrowser.open(target_url)
            except Exception:
                try:
                    ctypes.windll.shell32.ShellExecuteW(None, "open", target_url, None, None, 1)
                except Exception:
                    pass

        # Intentar restaurar y traer la ventana de Brave al frente si estaba minimizada
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            def enum_wnd(hwnd, _):
                if user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        t = buf.value.lower()
                        if "brave" in t or "youtube" in t:
                            user32.ShowWindow(hwnd, 9) # SW_RESTORE
                            user32.SwitchToThisWindow(hwnd, True)
                            user32.SetForegroundWindow(hwnd)
                            user32.BringWindowToTop(hwnd)
                return True
            cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_wnd)
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

        msg = f"Reproduciendo '{clean_q}' en YouTube."
        state_mgr.emit_tool_call("play_youtube", {"query": clean_q, "url": target_url}, msg)
        log_info(f"YouTube reproducido: {target_url}")
        return {"status": "success", "message": msg, "url": target_url}

    def play_spotify(self, query: str = "") -> Dict[str, Any]:
        """Busca y reproduce una canción, artista, álbum o playlist en Spotify directamente en la computadora."""
        import urllib.parse
        import ctypes
        import time
        import os
        import json
        import subprocess
        from tools.app_launcher import app_launcher

        raw_q = (query or "").strip()
        clean_q = raw_q

        # Limpiar prefijos comunes
        prefixes = [
            "cuautitlan", "cuautitlán", "ehu titan", "ehu titán", "eu titan", "eu titán",
            "titan", "titán", "el titan", "el titán", "che titan", "che titán", "che", "eu", "eh", "ey",
            "pone en spotify", "poné en spotify", "pon en spotify", "poneme en spotify", "ponéme en spotify",
            "reproducir en spotify", "reproduci en spotify", "reproducí en spotify", "reproducime en spotify",
            "buscar en spotify", "busca en spotify", "buscá en spotify", "buscame en spotify",
            "abrir spotify y poner", "abrí spotify y poné", "abrir spotify", "abri spotify", "abrí spotify",
            "pone", "poné", "pon", "poner", "poneme", "ponéme", "reproducir", "reproduci", "reproducí", "reproducime",
            "toca", "tocá", "tocame", "tocáme", "escuchar", "escucha", "buscar", "busca", "buscá", "abrir", "abri", "abrí",
            "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
            "la canción de", "la canción del", "la canción",
            "la musica de", "la musica del", "la musica", "la música de", "la música del", "la música",
            "musica", "música", "disco de", "album de", "álbum de"
        ]

        low_q = clean_q.lower()
        changed = True
        while changed:
            changed = False
            for p in prefixes:
                if low_q.startswith(p + " "):
                    clean_q = clean_q[len(p):].strip()
                    low_q = clean_q.lower()
                    changed = True
                    break
                elif low_q == p:
                    clean_q = ""
                    low_q = ""
                    break

        # Limpiar sufijos
        for suffix in ["en spotify", "de spotify", "por spotify", "spotify"]:
            if low_q.endswith(" " + suffix):
                clean_q = clean_q[:-len(suffix)-1].strip()
                low_q = clean_q.lower()
            elif low_q == suffix:
                clean_q = ""
                low_q = ""
                break

        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "play_spotify",
                {"query": clean_q},
                f"Ahí te puse '{clean_q}' en Spotify en la compu, fiera." if clean_q else "Ahí te abrí Spotify en la compu, fiera."
            )
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        exe_path = self._get_spotify_exe_path()

        # Asegurar que Spotify esté iniciado
        is_running = self._ensure_spotify_running()
        if not is_running:
            app_launcher.launch("spotify")

        # Si no hay término de búsqueda, solo abrir o reanudar Spotify
        if not clean_q:
            if cli_path:
                run_silent([cli_path, "open"], capture_output=True)
                run_silent([cli_path, "resume"], capture_output=True)
                self._bring_spotify_window_to_front()
            else:
                app_launcher.launch("spotify")
            msg = "Ahí te abrí Spotify, fiera."
            state_mgr.emit_tool_call("play_spotify", {"query": ""}, msg)
            return {"status": "success", "message": msg}

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Poniendo en Spotify: {clean_q}")
        log_info(f"[Spotify] Buscando y reproduciendo: {clean_q}")

        target_uri = None
        target_title = f"'{clean_q}'"

        # 1. Búsqueda directa en catálogo de Spotify mediante Spotify CLI (100% invisible)
        if cli_path:
            try:
                res = run_silent([cli_path, "search", clean_q, "--limit", "3", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                if res.stdout:
                    data = json.loads(res.stdout)
                    if data.get("tracks"):
                        t = data["tracks"][0]
                        target_uri = t.get("uri")
                        artists = ", ".join(t.get("artists", []))
                        target_title = f"'{t.get('name')}' de {artists}" if artists else f"'{t.get('name')}'"
                    elif data.get("artists"):
                        a = data["artists"][0]
                        target_uri = a.get("uri")
                        target_title = f"música de {a.get('name')}"
                    elif data.get("playlists"):
                        pl = data["playlists"][0]
                        target_uri = pl.get("uri")
                        target_title = f"la playlist '{pl.get('name')}'"
            except Exception as e:
                log_warning(f"[Spotify] Error buscando en catálogo CLI: {e}")

        # Fallback a URI de búsqueda si no se obtuvo URI específico
        if not target_uri:
            target_uri = f"spotify:search:{urllib.parse.quote(clean_q)}"

        # 2. Ejecutar reproducción y navegación (completamente en segundo plano sin ventanas)
        if cli_path:
            run_silent([cli_path, "play", target_uri], capture_output=True, text=True)
            run_silent([cli_path, "navigate", target_uri, "--play"], capture_output=True, text=True)
            run_silent([cli_path, "open", target_uri], capture_output=True, text=True)
            self._bring_spotify_window_to_front()
        else:
            uri = f"spotify:search:{urllib.parse.quote(clean_q)}"
            popen_silent(["explorer.exe", uri])


        msg = f"Ahí te puse {target_title} en Spotify, fiera."
        state_mgr.emit_tool_call("play_spotify", {"query": clean_q, "uri": target_uri}, msg)
        log_info(f"Spotify reproducido: {clean_q} -> {target_uri}")
        return {"status": "success", "message": msg, "query": clean_q, "uri": target_uri}

    def close_active_window(self) -> Dict[str, Any]:
        """Cierra la ventana activa actual enviando Alt+F4"""
        try:
            user32 = ctypes.windll.user32
            VK_MENU = 0x12
            VK_F4 = 0x73
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_F4, 0, 0, 0)
            user32.keybd_event(VK_F4, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            msg = "Listo, cerré la ventana activa."
            state_mgr.emit_tool_call("close_active_window", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"No pude cerrar la ventana: {e}"}

    def maximize_active_window(self) -> Dict[str, Any]:
        """Maximiza la ventana activa"""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                msg = "Ventana maximizada, papá."
                state_mgr.emit_tool_call("maximize_active_window", {}, msg)
                return {"status": "success", "message": msg}
            return {"status": "error", "message": "No encontré ventana activa"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def minimize_active_window(self) -> Dict[str, Any]:
        """Minimiza la ventana activa"""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                msg = "Ventana minimizada, che."
                state_mgr.emit_tool_call("minimize_active_window", {}, msg)
                return {"status": "success", "message": msg}
            return {"status": "error", "message": "No encontré ventana activa"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def switch_active_window(self) -> Dict[str, Any]:
        """Cambia a la siguiente ventana activa con Alt+Tab"""
        try:
            user32 = ctypes.windll.user32
            VK_MENU = 0x12
            VK_TAB = 0x09
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_TAB, 0, 0, 0)
            user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            msg = "Ahí pasé a la otra ventana."
            state_mgr.emit_tool_call("switch_active_window", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def empty_recycle_bin(self) -> Dict[str, Any]:
        """Vacía la papelera de reciclaje de Windows de forma segura y silenciosa"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("empty_recycle_bin", {}, "¡Listo, papá! Vacié la papelera de reciclaje por completo.")
            if remote_res:
                return remote_res
        try:
            # SHERB_NOCONFIRMATION (1) | SHERB_NOPROGRESSUI (2) | SHERB_NOSOUND (4) = 7
            res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            msg = "¡Listo, papá! Vacié la papelera de reciclaje por completo."
            state_mgr.emit_tool_call("empty_recycle_bin", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error vaciando papelera: {e}"}

    def search_google(self, query: str) -> Dict[str, Any]:
        """Busca directamente una consulta en Google en el navegador predeterminado"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("search_google", {"query": query}, f"Busqué '{query}' en Google en la compu.")
            if remote_res:
                return remote_res
        import webbrowser, urllib.parse
        clean_q = query.strip()
        url = f"https://www.google.com/search?q={urllib.parse.quote(clean_q)}"
        webbrowser.open(url)
        msg = f"Buscando '{clean_q}' en Google."
        state_mgr.emit_tool_call("search_google", {"query": clean_q}, msg)
        return {"status": "success", "message": msg, "url": url}

    def open_web_service(self, service: str) -> Dict[str, Any]:
        """Abre servicios web directos como WhatsApp, Mercado Libre, Gmail o YouTube"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("open_web_service", {"service": service}, f"Abrí {service} en la compu.")
            if remote_res:
                return remote_res
        import webbrowser
        urls = {
            "whatsapp": "https://web.whatsapp.com",
            "mercadolibre": "https://www.mercadolibre.com.ar",
            "gmail": "https://mail.google.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://twitter.com"
        }
        target_url = urls.get(service.lower(), f"https://www.{service}.com")
        webbrowser.open(target_url)
        msg = f"Abriendo {service.capitalize()}."
        state_mgr.emit_tool_call("open_web_service", {"service": service, "url": target_url}, msg)
        return {"status": "success", "message": msg, "url": target_url}

    def shutdown_pc(self) -> Dict[str, Any]:
        """Inicia el apagado de la computadora con margen de seguridad"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("shutdown_pc", {}, "Apagando la computadora en 10 segundos. ¡Hasta la próxima, fiera!")
            if remote_res:
                return remote_res
        run_silent(["shutdown", "/s", "/t", "10"])
        msg = "Apagando la computadora en 10 segundos. ¡Hasta la próxima, fiera!"
        state_mgr.emit_tool_call("shutdown_pc", {}, msg)
        return {"status": "success", "message": msg}

    def restart_pc(self) -> Dict[str, Any]:
        """Reinicia la computadora con margen de seguridad"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("restart_pc", {}, "Reiniciando la computadora en 10 segundos. Bancame un toque.")
            if remote_res:
                return remote_res
        run_silent(["shutdown", "/r", "/t", "10"])
        msg = "Reiniciando la computadora en 10 segundos. Bancame un toque."
        state_mgr.emit_tool_call("restart_pc", {}, msg)
        return {"status": "success", "message": msg}

    def sleep_pc(self) -> Dict[str, Any]:
        """Pone la computadora en modo suspensión de bajo consumo"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("sleep_pc", {}, "Poniendo la compu a dormir (modo suspensión), papá.")
            if remote_res:
                return remote_res
        try:
            run_silent(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
            msg = "Poniendo la compu a dormir (modo suspensión), papá."
            state_mgr.emit_tool_call("sleep_pc", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error suspendiendo: {e}"}

    def get_clipboard(self) -> Dict[str, Any]:
        """Lee el texto actual guardado en el portapapeles de Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_clipboard", {}, "Leí el portapapeles de la compu.")
            if remote_res:
                return remote_res
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            text = r.clipboard_get()
            r.destroy()
            msg = f"En el portapapeles tenés: '{text}'"
            return {"status": "success", "text": text, "message": msg}
        except Exception:
            return {"status": "empty", "text": "", "message": "El portapapeles está vacío o contiene un formato no soportado."}

    def set_clipboard(self, text: str) -> Dict[str, Any]:
        """Copia un texto al portapapeles de Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_clipboard", {"text": text}, f"Copié el texto al portapapeles de la compu.")
            if remote_res:
                return remote_res
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            msg = f"Copié '{text[:50]}' al portapapeles de la compu."
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error copiando al portapapeles: {e}"}


    def get_brightness(self) -> Dict[str, Any]:
        """Obtiene el brillo actual del monitor físico principal (0 a 100)"""
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            dxva2 = ctypes.windll.dxva2

            class PHYSICAL_MONITOR(ctypes.Structure):
                _fields_ = [('hPhysicalMonitor', wintypes.HANDLE), ('szPhysicalMonitorDescription', wintypes.WCHAR * 128)]

            cur_val = None
            def cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
                nonlocal cur_val
                num = wintypes.DWORD()
                if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hMonitor, ctypes.byref(num)) and num.value > 0:
                    pms = (PHYSICAL_MONITOR * num.value)()
                    if dxva2.GetPhysicalMonitorsFromHMONITOR(hMonitor, num.value, pms):
                        cur = wintypes.DWORD()
                        min_b = wintypes.DWORD()
                        max_b = wintypes.DWORD()
                        if dxva2.GetMonitorBrightness(pms[0].hPhysicalMonitor, ctypes.byref(min_b), ctypes.byref(cur), ctypes.byref(max_b)):
                            cur_val = cur.value
                        dxva2.DestroyPhysicalMonitors(num.value, pms)
                return cur_val is None

            MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
            user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)

            if cur_val is not None:
                msg = f"El brillo actual de la pantalla está al {cur_val}%."
                return {"status": "success", "brightness": cur_val, "message": msg}
        except Exception as e:
            log_warning(f"Error leyendo brillo: {e}")
        return {"status": "error", "message": "No pude leer el brillo del monitor."}

    def set_brightness(self, level: int) -> Dict[str, Any]:
        """Ajusta el brillo del monitor físico de 0 a 100%"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_brightness", {"level": level}, f"Ajusté el brillo al {level}%.")
            if remote_res:
                return remote_res
        target = max(0, min(100, int(level)))
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            dxva2 = ctypes.windll.dxva2

            class PHYSICAL_MONITOR(ctypes.Structure):
                _fields_ = [('hPhysicalMonitor', wintypes.HANDLE), ('szPhysicalMonitorDescription', wintypes.WCHAR * 128)]

            success = False
            def cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
                nonlocal success
                num = wintypes.DWORD()
                if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hMonitor, ctypes.byref(num)) and num.value > 0:
                    pms = (PHYSICAL_MONITOR * num.value)()
                    if dxva2.GetPhysicalMonitorsFromHMONITOR(hMonitor, num.value, pms):
                        for pm in pms:
                            if dxva2.SetMonitorBrightness(pm.hPhysicalMonitor, target):
                                success = True
                        dxva2.DestroyPhysicalMonitors(num.value, pms)
                return True

            MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
            user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)

            if success:
                msg = f"Brillo de la pantalla ajustado al {target}%."
                state_mgr.emit_tool_call("set_brightness", {"level": target}, msg)
                return {"status": "success", "brightness": target, "message": msg}
        except Exception as e:
            log_warning(f"Error cambiando brillo: {e}")
        return {"status": "error", "message": "No pude cambiar el brillo del monitor."}

    def brightness_up(self, delta: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("brightness_up", {"step": delta}, "Subí el brillo del monitor.")
            if remote_res:
                return remote_res
        res = self.get_brightness()
        cur = res.get("brightness", 50)
        return self.set_brightness(cur + delta)

    def brightness_down(self, delta: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("brightness_down", {"step": delta}, "Bajé el brillo del monitor.")
            if remote_res:
                return remote_res
        res = self.get_brightness()
        cur = res.get("brightness", 50)
        return self.set_brightness(cur - delta)

    def toggle_night_light(self) -> Dict[str, Any]:
        """Abre la configuración de Luz Nocturna de Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("toggle_night_light", {}, "Ahí te abrí la configuración de Luz Nocturna de Windows para cuidar la vista.")
            if remote_res:
                return remote_res
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "open", "ms-settings:nightlight", None, None, 1)
        except Exception:
            run_silent(["cmd", "/c", "start", "ms-settings:nightlight"])
        msg = "Ahí te abrí la configuración de Luz Nocturna de Windows para cuidar la vista."
        state_mgr.emit_tool_call("toggle_night_light", {}, msg)
        return {"status": "success", "message": msg}


    def get_top_processes(self, sort_by: str = "ram", limit: int = 5) -> Dict[str, Any]:
        """Devuelve los programas que más consumen CPU o memoria RAM en este momento"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_top_processes", {"sort_by": sort_by, "limit": limit}, "Acá tenés los procesos que más consumen en la compu.")
            if remote_res:
                return remote_res
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
                try:
                    info = p.info
                    ram_mb = round(info['memory_info'].rss / (1024 * 1024), 1) if info.get('memory_info') else 0.0
                    procs.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "ram_mb": ram_mb,
                        "ram_percent": round(info['memory_percent'] or 0.0, 1),
                        "cpu_percent": round(info['cpu_percent'] or 0.0, 1)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            key = "ram_mb" if sort_by.lower() != "cpu" else "cpu_percent"
            sorted_procs = sorted(procs, key=lambda x: x[key], reverse=True)[:limit]

            lines = []
            for p in sorted_procs:
                lines.append(f"- {p['name']} (PID: {p['pid']}): {p['ram_mb']} MB RAM ({p['ram_percent']}%), {p['cpu_percent']}% CPU")
            
            summary = "\n".join(lines)
            metric_desc = "memoria RAM" if key == "ram_mb" else "procesador (CPU)"
            msg = f"Los programas que más {metric_desc} están consumiendo son:\n{summary}"
            state_mgr.emit_tool_call("get_top_processes", {"sort_by": sort_by}, msg)
            return {"status": "success", "processes": sorted_procs, "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"No pude obtener la lista de procesos: {e}"}

    def kill_process(self, name_or_pid: str) -> Dict[str, Any]:
        """Cierra o termina un proceso/programa por nombre o PID a la fuerza"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("kill_process", {"name_or_pid": name_or_pid}, f"Cerré el proceso '{name_or_pid}' en la compu.")
            if remote_res:
                return remote_res
        clean = name_or_pid.strip().lower()
        protected = {
            "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe",
            "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
            "winlogon.exe", "dwm.exe", "spoolsv.exe", "explorer.exe", "python.exe",
            "pythonw.exe", "cmd.exe", "powershell.exe"
        }
        
        for p_name in protected:
            if clean == p_name or clean == p_name.replace(".exe", ""):
                return {"status": "error", "message": f"Ni en pedo toco '{name_or_pid}', che: es un proceso crítico de Windows o de Titán y se te va a apagar o romper el sistema."}

        killed = []
        try:
            if clean.isdigit():
                pid = int(clean)
                p = psutil.Process(pid)
                p_name = p.name()
                if p_name.lower() in protected:
                    return {"status": "error", "message": f"El PID {pid} corresponde a '{p_name}', que es crítico de Windows."}
                p.kill()
                killed.append(f"{p_name} (PID: {pid})")
            else:
                target_name = clean if clean.endswith(".exe") else f"{clean}.exe"
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        n = p.info['name'].lower()
                        if n == target_name or clean in n:
                            if n not in protected:
                                p.kill()
                                killed.append(f"{p.info['name']} (PID: {p.info['pid']})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

            if killed:
                msg = f"Listo, papá: cerré a la fuerza {len(killed)} proceso(s): {', '.join(killed[:4])}."
                state_mgr.emit_tool_call("kill_process", {"target": name_or_pid}, msg)
                return {"status": "success", "killed": killed, "message": msg}
            else:
                return {"status": "not_found", "message": f"No encontré ningún proceso activo con el nombre '{name_or_pid}'."}
        except Exception as e:
            return {"status": "error", "message": f"Error terminando el proceso: {e}"}

    def optimize_pc_gaming(self) -> Dict[str, Any]:
        """Modo Gamer / Optimización de PC: minimiza ventanas secundarias y purga working sets de memoria"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("optimize_pc_gaming", {}, "¡Modo Gamer activado! Optimicé la memoria en tu compu.")
            if remote_res:
                return remote_res
        try:
            ram_before = psutil.virtual_memory()
            freed_count = 0
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    if p.info['name'].lower() not in {"system", "idle", "python.exe"}:
                        h_proc = ctypes.windll.kernel32.OpenProcess(0x001F0FFF, False, p.info['pid'])
                        if h_proc:
                            if ctypes.windll.psapi.EmptyWorkingSet(h_proc):
                                freed_count += 1
                            ctypes.windll.kernel32.CloseHandle(h_proc)
                except Exception:
                    pass

            time.sleep(0.3)
            ram_after = psutil.virtual_memory()
            msg = f"¡Modo Gamer y optimización al pie! Purgué la memoria de {freed_count} programas. Tenés {round(ram_after.available / (1024**3), 1)} GB libres de RAM listos para salir a ganar."
            state_mgr.emit_tool_call("optimize_pc_gaming", {}, msg)
            return {"status": "success", "ram_available_gb": round(ram_after.available / (1024**3), 1), "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error en optimización: {e}"}

    def test_network_ping(self, host: str = "8.8.8.8") -> Dict[str, Any]:
        """Realiza un test de ping para medir latencia y pérdida de paquetes"""
        clean_host = host.strip() or "8.8.8.8"
        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Midiendo ping a {clean_host}...")
        try:
            cmd = ["ping", "-c", "4", clean_host] if os.name != 'nt' else ["ping", "-n", "4", clean_host]
            res = run_silent(cmd, capture_output=True, text=True, timeout=8)
            out = res.stdout

            loss_match = re.search(r'\((\d+)%\s*(?:perdidos|loss)\)', out, re.IGNORECASE)
            loss_pct = int(loss_match.group(1)) if loss_match else 0

            avg_match = re.search(r'(?:Media|Average)\s*=\s*(\d+)\s*ms', out, re.IGNORECASE)
            if not avg_match:
                avg_match = re.search(r'rtt .+= [\d.]+/([\d.]+)/', out)
            avg_ms = int(float(avg_match.group(1))) if avg_match else None

            if avg_ms is not None:
                estado = "excelente" if avg_ms < 40 else ("buena" if avg_ms < 90 else "con algo de lag")
                msg = f"El ping a {clean_host} te da {avg_ms} milisegundos ({estado}) con {loss_pct}% de pérdida de paquetes."
            else:
                msg = f"No hubo respuesta del servidor {clean_host}. Parece que no hay conexión o el host está bloqueando el ping."

            state_mgr.emit_tool_call("test_network_ping", {"host": clean_host}, msg)
            return {"status": "success", "host": clean_host, "avg_ms": avg_ms, "loss_pct": loss_pct, "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error al medir el ping: {e}"}

    def flush_dns(self) -> Dict[str, Any]:
        """Limpia la caché de resolución DNS de Windows para resolver problemas de conexión"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("flush_dns", {}, "¡Listo, papá! Vacié la caché DNS en la compu.")
            if remote_res:
                return remote_res
        try:
            run_silent(["ipconfig", "/flushdns"], capture_output=True, check=True)
            msg = "¡Listo, papá! Vacié y renové la caché de resolución DNS de Windows. Si alguna página no te cargaba, probá ahora."
            state_mgr.emit_tool_call("flush_dns", {}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"Error vaciando DNS: {e}"}

    def get_network_info(self) -> Dict[str, Any]:
        """Obtiene la dirección IP local y la IP pública de tu conexión"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_network_info", {}, "Acá tenés la info de red de tu compu.")
            if remote_res:
                return remote_res
        import socket, urllib.request
        local_ip = "127.0.0.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        public_ip = "desconocida"
        try:
            req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                public_ip = resp.read().decode("utf-8").strip()
        except Exception:
            pass

        msg = f"Tu IP local en la red de tu casa es {local_ip}, y tu IP pública de internet es {public_ip}."
        state_mgr.emit_tool_call("get_network_info", {}, msg)
        return {"status": "success", "local_ip": local_ip, "public_ip": public_ip, "message": msg}

    def get_pc_security_info(self) -> Dict[str, Any]:
        """Obtiene telemetría de seguridad de Windows: inactividad de mouse/teclado, ventana activa y estado de bloqueo."""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_pc_security_info", {}, "Consulté la seguridad de la PC.")
            if remote_res:
                return remote_res
            return {
                "status": "success",
                "idle_seconds": 0.0,
                "idle_minutes": 0,
                "active_window": "Linux Host (Servidor)",
                "is_locked": False,
                "message": "Corriendo en Linux DDR3 (sin satélite conectado)"
            }

        idle_sec = 0.0
        active_window = "Desconocida"
        is_locked = False

        # 1. Medir tiempo de inactividad con GetLastInputInfo
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                idle_sec = max(0.0, round(millis / 1000.0, 1))
        except Exception as e:
            log_warning(f"[Security] Error obteniendo LastInputInfo: {e}")

        # 2. Obtener ventana activa y evaluar si está bloqueada
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                    active_window = buff.value.strip() or "Sin título"
                else:
                    active_window = "Pantalla de bloqueo o proceso del sistema"
            else:
                active_window = "Ninguna ventana activa (Bloqueada)"
        except Exception as e:
            active_window = f"Error: {e}"

        # 3. Determinar si está bloqueada (OpenInputDesktop o LockApp en foreground)
        try:
            h_desk = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS = 0x0001
            if not h_desk:
                is_locked = True
            else:
                ctypes.windll.user32.CloseDesktop(h_desk)
                if "bloqueo" in active_window.lower() or "lock" in active_window.lower() or not hwnd:
                    is_locked = True
        except Exception:
            is_locked = False

        idle_min = int(idle_sec // 60)
        lock_str = "BLOQUEADA 🔒" if is_locked else "DESBLOQUEADA / ACTIVA 🔓"
        msg = f"PC {lock_str}. Ventana activa: '{active_window}'. Inactividad de mouse/teclado: {idle_min} min ({int(idle_sec)}s)."

        return {
            "status": "success",
            "idle_seconds": idle_sec,
            "idle_minutes": idle_min,
            "active_window": active_window,
            "is_locked": is_locked,
            "message": msg
        }

    def set_wallpaper(self, image_path_or_url: str) -> Dict[str, Any]:
        """Establece una imagen como fondo de pantalla de Windows"""
        if sys.platform != "win32":
            return {"status": "error", "message": "Solo disponible en la PC Principal con Windows"}
        try:
            target_path = image_path_or_url
            if image_path_or_url.startswith("http://") or image_path_or_url.startswith("https://"):
                import urllib.request
                import tempfile
                temp_file = Path(tempfile.gettempdir()) / "titan_wallpaper.jpg"
                urllib.request.urlretrieve(image_path_or_url, str(temp_file))
                target_path = str(temp_file)

            if not os.path.exists(target_path):
                return {"status": "error", "message": f"Archivo de imagen no encontrado: {target_path}"}

            SPI_SETDESKWALLPAPER = 20
            SPIF_UPDATEINIFILE = 0x01
            SPIF_SENDCHANGE = 0x02
            success = ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER, 0, os.path.abspath(target_path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
            )
            if success:
                log_info(f"[SystemControl] Fondo de pantalla actualizado: {target_path}")
                return {"status": "success", "message": "¡Fondo de pantalla de Windows cambiado con éxito!"}
            else:
                return {"status": "error", "message": "Windows no pudo aplicar el fondo de pantalla."}
        except Exception as e:
            log_error(f"Error cambiando wallpaper: {e}")
            return {"status": "error", "message": f"Error cambiando fondo: {e}"}


system_control = SystemControl()

