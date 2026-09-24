"""Hardware de la PC, doctor y red.."""

from ._common import _mip
import re
from core.state_manager import state_mgr
from tools.system_control import system_control

from typing import Optional

def handle_hardware(engine, text, clean, norm) -> "Optional[str]":
    """3. RECURSOS DE LA PC (HARDWARE) Y CONTROL DE TEMPERATURA."""
    is_hw_query = any(_mip(norm, p) for p in [
        "como viene la compu", "como va la compu", "como esta la pc", "cómo está la pc",
        "como esta la compu", "cómo está la compu", "recursos", "telemetria", "hardware",
        "temperatura de la pc", "temperatura de la compu", "temperatura del cpu", "temperatura de la cpu",
        "temperatura del procesador", "temperatura de la placa", "temperatura de los componentes", "a cuanto esta la cpu",
        "cuanta ram", "cuánta ram", "uso de cpu", "uso de ram", "estado de la pc", "estado de la compu",
        "como viene el servidor", "como esta el servidor", "recursos del servidor", "recursos de la ddr3",
        "temperatura del servidor", "servidor titan", "servidor titán", "ddr3"
    ])
    if is_hw_query:
        is_ddr3_query = any(_mip(norm, w) for w in ["servidor", "ddr3", "la ddr", "maquina secundaria", "máquina secundaria", "server"])

        if is_ddr3_query:
            # Consulta explícita sobre el servidor Titán (DDR3)
            metrics = system_control.get_system_metrics()
            cpu = metrics.get("cpu_percent", 0)
            ram = metrics.get("ram_percent", 0)
            temp = metrics.get("temp_c")
            temp_str = f" a {temp}°C" if temp else ""
            msg = f"El servidor Titán (DDR3) viene joya: la CPU está al {cpu}%{temp_str}, la memoria RAM al {ram}% y el sistema estable. Ahí te abro la telemetría."
        else:
            # Consulta por defecto: PC PRINCIPAL (Windows)
            try:
                from server.websocket_hub import ws_hub
                sat = ws_hub.get_satellite_metrics()
            except Exception:
                sat = {}

            if sat.get("connected"):
                cpu = sat.get("cpu_percent", 0)
                ram = sat.get("ram_percent", 0)
                temp = sat.get("temp_c")
                disks = sat.get("disks", {})
                free_c = disks.get("C", {}).get("free_gb", "")
                temp_str = f" a {temp}°C de temperatura" if temp else ""
                disk_str = f" y el disco C con {free_c} GB libres" if free_c else ""
                msg = f"La PC principal viene diez puntos: la CPU está al {cpu}%{temp_str}, la memoria RAM al {ram}%{disk_str}. Ahí te puse los recursos en pantalla."
            else:
                # Si el entorno actual ya es Windows directo (por ejemplo desarrollo local o satélite integrado)
                local_m = system_control.get_system_metrics()
                if local_m.get("platform") == "windows":
                    cpu = local_m.get("cpu_percent", 0)
                    ram = local_m.get("ram_percent", 0)
                    temp = local_m.get("temp_c")
                    disks = local_m.get("disks", {})
                    free_c = disks.get("C", {}).get("free_gb", "")
                    temp_str = f" a {temp}°C de temperatura" if temp else ""
                    disk_str = f" y el disco C con {free_c} GB libres" if free_c else ""
                    msg = f"La PC principal viene diez puntos: la CPU está al {cpu}%{temp_str}, la memoria RAM al {ram}%{disk_str}. Ahí te puse los recursos en pantalla."
                else:
                    cpu_ddr3 = local_m.get("cpu_percent", 0)
                    temp_ddr3 = local_m.get("temp_c")
                    temp_str = f" a {temp_ddr3}°C" if temp_ddr3 else ""
                    msg = f"Che, la PC principal parece estar apagada o con el satélite cerrado. Pero el servidor Titán acá en la DDR3 está activo con la CPU al {cpu_ddr3}%{temp_str}. Ahí te abro la telemetría."

        system_control.switch_screen_view("telemetry")
        state_mgr.emit_tool_call("get_system_metrics", {"target": "ddr3" if is_ddr3_query else "primary"}, msg)
        return msg

    # 3b. REFRIGERACIÓN ACTIVA Y PERFILES TÉRMICOS / ENERGÍA
    is_cool_cmd = any(_mip(norm, p) for p in [
        "enfria la pc", "enfriar la pc", "enfriar pc", "enfria la compu", "enfriar la compu",
        "refrigera la pc", "refrigerar la pc", "refrigera la compu", "refrigerar la compu",
        "bajar la temperatura", "baja la temperatura", "bajar temperatura",
        "modo frio", "modo frío", "modo enfriamiento", "activa modo frio", "activar modo frio",
        "pone modo frio", "poné modo frío", "modo refrigeracion", "modo economizador", "modo eco"
    ])
    if is_cool_cmd:
        # S-6: cierra procesos -> pide confirmación (el freno vive en
        # core.confirmation; al confirmar se ejecuta vía execute_action).
        return engine.request_confirmation("cool_down_pc")

    is_plan_balanced = any(_mip(norm, p) for p in [
        "modo equilibrado", "plan equilibrado", "energia equilibrada", "poner en equilibrado",
        "modo normal de energia", "modo balanceado", "rendimiento equilibrado"
    ])
    if is_plan_balanced:
        res = system_control.set_power_plan("balanced")
        system_control.switch_screen_view("telemetry")
        return res.get("message", "Puse la compu en Modo Equilibrado, papá. Balance ideal de rendimiento y temperatura.")

    is_plan_perf = any(_mip(norm, p) for p in [
        "modo alto rendimiento", "alto rendimiento", "modo turbo", "modo potencia",
        "maximo rendimiento", "máximo rendimiento", "modo gamer de energia"
    ])
    if is_plan_perf:
        res = system_control.set_power_plan("performance")
        system_control.switch_screen_view("telemetry")
        return res.get("message", "¡Activé el modo Alto Rendimiento! Preparate que desata toda la potencia del procesador.")

    # 3b. CONTROL DE VOZ DE TITÁN EN LA PC PRINCIPAL (POR DEFECTO SALE POR DDR3)
    is_pc_voice_off = any(_mip(norm, p) for p in [
        "desactivar voz en la pc", "desactiva la voz en la pc", "desactivar la voz en la pc", "desactiva voz en la pc",
        "desactivar voz de la pc", "desactiva la voz de la pc", "desactivar la voz de la pc",
        "silenciar voz en la pc", "silencia la voz en la pc", "silenciar la voz en la pc", "silencia voz en la pc",
        "sacar voz de la compu", "saca la voz de la compu", "sacar la voz de la compu", "saca voz de la compu",
        "sacar voz de la pc", "saca la voz de la pc", "sacar la voz de la pc",
        "desactivar voz en la compu", "desactiva la voz en la compu", "desactivar la voz en la compu", "desactiva voz en la compu",
        "silenciar en la compu", "silencia en la compu", "silenciar la compu", "silencia la compu",
        "apagar voz en la compu", "apagar voz en la pc", "apaga la voz en la compu", "apaga la voz en la pc",
        "mutear la pc", "mutear pc", "muta la pc", "silenciar voz de titan en la pc", "desactivar voz de titan en la pc"
    ])
    if is_pc_voice_off:
        res = system_control.set_pc_voice(False)
        return "Desactivé la voz en la PC Principal, fiera. Vuelve a salir únicamente por el Servidor Titán DDR3."

    is_pc_voice_on = (
        not any(_mip(norm, neg) for neg in ["desactiv", "silenci", "sacar", "saca", "apagar", "apaga", "mute"]) and
        any(_mip(norm, p) for p in [
            "activar voz en la pc", "activa la voz en la pc", "activar la voz en la pc", "activa voz en la pc",
            "activar voz de la pc", "activa la voz de la pc", "activar la voz de la pc",
            "activar voz en la compu", "activa la voz en la compu", "activar la voz en la compu", "activa voz en la compu",
            "escuchar a titan en la pc", "escuchar a titan en la compu", "escuchar en la compu", "escuchar en la pc",
            "pone la voz en la pc", "pone voz en la pc", "poner voz en la pc", "poner la voz en la pc",
            "pone la voz en la compu", "pone voz en la compu", "poner voz en la compu",
            "activar parlantes de la pc", "activa los parlantes de la pc", "activar los parlantes de la pc",
            "prender voz en la pc", "prende la voz en la pc", "prender voz en la compu", "prende la voz en la compu"
        ])
    )
    if is_pc_voice_on:
        res = system_control.set_pc_voice(True)
        return "Activé la voz en la PC Principal, papá. Ahora también salgo por los parlantes de tu compu."


def handle_doctor(engine, text, clean, norm) -> "Optional[str]":
    """18. DOCTOR DE PC Y PROCESOS."""
    if any(_mip(norm, p) for p in ["modo gamer", "optimizar pc", "optimiza la pc", "optimizame la pc", "cerrar programas de fondo", "liberar ram", "libera ram", "libera memoria", "liberar memoria"]):
        # S-6: cierra procesos -> pide confirmación.
        return engine.request_confirmation("optimize_pc_gaming")

    if any(_mip(norm, p) for p in [
        "que procesos consumen mas ram", "quien consume mas ram", "top procesos", "quien gasta mas memoria",
        "que programas estan consumiendo", "procesos que mas gastan", "que consume tanta ram"
    ]):
        from brain.tool_registry import get_top_processes
        return get_top_processes(sort_by="ram", limit=5)

    match_kill = re.search(r"(?:mata a|matar a|cerra el proceso|cerrar el proceso|mata el proceso|matar proceso)\s+([a-zA-Z0-9_\-\.]+)", norm)
    if match_kill:
        proc_target = match_kill.group(1).strip()
        if proc_target:
            # S-3: la vía voz mataba el proceso directo, sin pasar por la
            # política de confirmaciones (P0 cambio 3). Ahora pide
            # confirmación igual que la vía registry/Gemini.
            return engine.request_confirmation("kill_process", name_or_pid=proc_target)


def handle_network(engine, text, clean, norm) -> "Optional[str]":
    """19. DIAGNÓSTICO DE RED Y CONECTIVIDAD."""
    if any(_mip(norm, p) for p in ["limpia el dns", "limpiar dns", "flush dns", "purga el dns", "borra la cache de dns", "limpia la cache de dns"]):
        res = system_control.flush_dns()
        return res.get("message", "Caché DNS purgada con éxito.")

    if any(_mip(norm, p) for p in ["hace un ping", "hacer ping", "probar conexion", "proba la conexion", "test de red", "test de ping", "como esta el internet"]):
        res = system_control.test_network_ping()
        return res.get("message", "Prueba de ping realizada.")

    if any(_mip(norm, p) for p in ["cual es mi ip", "mi direccion ip", "info de red", "informacion de red", "como se llama mi compu en red"]):
        res = system_control.get_network_info()
        return res.get("message", "Información de red obtenida.")
