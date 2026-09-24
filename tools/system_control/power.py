"""Mixin de energía: planes, temperatura, métricas y apagado."""

from core.logger import log_warning

import ctypes

import os

from core.process_utils import run_silent

import socket

from core.state_manager import state_mgr

import subprocess

import sys

import time

import psutil

from typing import Any, Dict

POWER_PLANS = {
    "eco": {"guid": "a1841308-3541-4fab-bc81-f71556f20b4a", "name": "Economizador / Modo Frío", "desc": "Reduce voltaje y reloj de la CPU para enfriar la máquina rápidamente"},
    "balanced": {"guid": "381b4222-f694-41f0-9685-ff5bb260df2e", "name": "Equilibrado", "desc": "Rendimiento balanceado según demanda del sistema"},
    "performance": {"guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "name": "Alto rendimiento", "desc": "Máxima potencia para juegos y edición"}
}


class PowerMixin:

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
            # B-31: antes se iteraba en orden de dict y cualquier sensor
            # posterior cuyo nombre matcheaba una keyword pisaba al anterior
            # (el break solo salía del loop interno), así un sensor erróneo
            # podía quedar como temperatura definitiva. Ahora: dos pasadas,
            # primero sensores de CPU reales (k10temp/coretemp/...), después
            # cualquier otro válido como último recurso.
            def _temp_ok(entry):
                return bool(entry.current) and 0 < entry.current < 125

            def _is_cpu_sensor(name):
                n = (name or "").lower()
                return any(k in n for k in ("k10temp", "coretemp", "cpu", "package"))

            try:
                st = getattr(psutil, "sensors_temperatures", lambda: {})() or {}
                for prefer_cpu in (True, False):
                    for sname, slist in st.items():
                        if _is_cpu_sensor(sname) != prefer_cpu:
                            continue
                        for entry in slist:
                            if _temp_ok(entry):
                                res["cpu"] = round(entry.current, 1)
                                break
                        if res["cpu"] is not None:
                            break
                    if res["cpu"] is not None:
                        break
            except Exception:
                pass

            if res["cpu"] is None:
                try:
                    import glob
                    cands = []
                    for f in glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
                        name = ""
                        try:
                            with open(os.path.join(os.path.dirname(f), "name")) as fp:
                                name = fp.read().strip()
                        except Exception:
                            pass
                        cands.append((_is_cpu_sensor(name), f))
                    # Primero drivers de CPU, después el resto (orden estable)
                    for _, f in sorted(cands, key=lambda x: (not x[0], x[1])):
                        try:
                            with open(f, "r") as fp:
                                raw = fp.read().strip()
                            if raw.isdigit():
                                val = round(float(raw) / 1000.0, 1)
                                if 0 < val < 125:
                                    res["cpu"] = val
                                    break
                        except Exception:
                            continue
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
        """Obtiene métricas completas de CPU, núcleos, RAM, discos, red y temperatura para telemetría.

        B-17: nunca revienta. Si alguna sub-llamada falla (WMI/servicio caído,
        psutil sin permiso, etc.), devuelve un dict degradado con status=error
        en vez de propagar la excepción: antes eso mataba el loop de telemetría
        del satélite y dejaba de reportar por completo.
        """
        try:
            return self._get_system_metrics_inner()
        except Exception as e:
            return {
                "status": "error",
                "hostname": os.getenv("COMPUTERNAME") or socket.gethostname(),
                "platform": "windows" if sys.platform == "win32" else "linux",
                "error": f"get_system_metrics falló: {e}",
            }

    def _get_system_metrics_inner(self) -> Dict[str, Any]:
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
        # B-17: uptime del sistema (segundos desde el arranque), con guardia.
        try:
            uptime_s = int(time.time() - psutil.boot_time())
        except Exception:
            uptime_s = 0
        return {
            "status": "success",
            "hostname": hostname,
            "platform": "windows" if sys.platform == "win32" else "linux",
            "uptime_s": uptime_s,
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
