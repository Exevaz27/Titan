"""Mixin de administración: procesos, red y seguridad."""

from core.logger import log_warning

import ctypes

import os

from core.process_utils import run_silent

import re


from core.state_manager import state_mgr, AssistantState

import time

import psutil

from typing import Any, Dict


class SysAdminMixin:

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
                # S-2: match EXACTO, sin subcadena. Antes `clean in n` hacía
                # que "mata chrome" matara también chrome_updater.exe,
                # chrome_installer, etc. Solo el nombre exacto (con o sin .exe).
                wanted = {clean, f"{clean}.exe"} if not clean.endswith(".exe") else {clean, clean[:-4]}
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        n = p.info['name'].lower()
                        if n in wanted:
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

            # B-18: la pérdida venía solo en formato Windows "(0% perdidos)".
            # En Linux el formato es "0% packet loss" sin paréntesis y nunca
            # matcheaba: siempre informaba 0% aunque hubiera pérdida real.
            loss_match = (
                re.search(r'\((\d+)%\s*(?:perdidos|pérdida|loss)\)', out, re.IGNORECASE)
                or re.search(r'(\d+)%\s*(?:packet loss|paquetes perdidos|pérdida de paquetes)', out, re.IGNORECASE)
            )
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

    # P0-4 — Límites para la descarga de imágenes de fondo de pantalla.
    # Antes se usaba urlretrieve sin timeout, sin límite de tamaño y sin
    # verificar que lo descargado fuera realmente una imagen.
    WALLPAPER_MAX_BYTES = 25 * 1024 * 1024  # 25 MB
    WALLPAPER_TIMEOUT = 15  # segundos
