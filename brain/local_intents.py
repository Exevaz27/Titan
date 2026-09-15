import re
import datetime
from typing import Tuple, Optional
from tools.system_control import system_control
from tools.app_launcher import app_launcher
from core.state_manager import state_mgr, AssistantState
from core.config import config

class LocalIntentEngine:
    """
    Motor de intenciones locales instantáneas (Zero-Latency / Offline).
    Responde en menos de 0.05s a preguntas frecuentes y comandos de Windows
    sin necesidad de depender de los servidores de Google Gemini.
    """

    def __init__(self):
        self.pending_confirmation: Optional[str] = None
        self.pending_confirmation_args = {}

    def request_confirmation(self, action: str, **args) -> str:
        self.pending_confirmation = action
        self.pending_confirmation_args = args
        descriptions = {
            "shutdown": "apagar la computadora",
            "restart": "reiniciar la computadora",
            "sleep": "suspender la computadora",
            "empty_recycle_bin": "vaciar la papelera de reciclaje",
            "kill_process": f"finalizar el proceso {args.get('name_or_pid', '')}",
        }
        description = descriptions.get(action, "ejecutar esta acción sensible")
        return f"Necesito tu confirmación para {description}. Decime 'sí, confirmo' o 'cancelá'."

    def try_handle(self, text: str) -> Tuple[bool, Optional[str]]:
        if not text:
            return False, None

        clean = text.lower().strip()
        norm = (clean
            .replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("¿", "")
            .replace("?", "")
            .replace("¡", "")
            .replace("!", "")
            .strip())

        # Quitar prefijo de invocación si vino en el texto (ej: "titán prende la tele", "titan pone espn")
        for wake in ["titan ", "titán ", "che titan ", "che titán "]:
            if norm.startswith(wake):
                norm = norm[len(wake):].strip()

        # Si había una confirmación pendiente (ej. apagar o reiniciar la PC)
        if self.pending_confirmation:
            action = self.pending_confirmation
            args = self.pending_confirmation_args
            self.pending_confirmation = None
            self.pending_confirmation_args = {}
            confirmation_words = {
                "si", "sí", "si confirmo", "sí confirmo", "confirmo",
                "dale", "de una", "obvio", "claro", "metele", "metele"
            }
            if norm in confirmation_words or norm.startswith(("si ", "sí ", "confirmo ")):
                if action == "shutdown":
                    res = system_control.shutdown_pc()
                    return True, res.get("message", "Apagando la compu.")
                elif action == "restart":
                    res = system_control.restart_pc()
                    return True, res.get("message", "Reiniciando la compu.")
                elif action == "sleep":
                    res = system_control.sleep_pc()
                    return True, res.get("message", "Suspendiendo la compu.")
                elif action == "empty_recycle_bin":
                    res = system_control.empty_recycle_bin()
                    return True, res.get("message", "Vaciando la papelera.")
                elif action == "kill_process":
                    res = system_control.kill_process(args.get("name_or_pid", ""))
                    return True, res.get("message", "Proceso finalizado.")
                elif action == "trash_file":
                    from tools.file_manager import file_manager
                    res = file_manager.trash_file(args.get("file_path", ""))
                    return True, res.get("message", "Archivo enviado a la papelera.")
            else:
                return True, "Listo che, cancelado. No toco nada, seguimos en la compu tranqui."

        # 0. CONTROL DE MODO REBELDE / SIN FILTRO
        # Desactivación o Modo Normal: cualquier conjugación de volver a normal / compinche
        is_normal_attempt = (
            any(w in norm for w in [
                "modo normal", "modo compinche", "volver a la normalidad", "volve a la normalidad",
                "desactivar modo", "desactiva modo", "sacar modo", "saca modo", "sacame el modo",
                "apagar modo", "apaga modo", "basta de modo", "calmate", "baja un cambio", "tranquilizate", "tranca titan", "tranca titán",
                "salir de la tertulia", "salir del debate", "terminar debate", "basta de futbol", "basta de fútbol"
            ])
            or ("desactiv" in norm and any(x in norm for x in ["rebel", "revel", "pibe", "infantil", "tertulia", "debate", "modo"]))
        )
        if is_normal_attempt:
            from brain.gemini_client import brain
            brain.set_mode("normal")
            responses = [
                "Uf, de diez, papá. Volví al modo compinche de fierro. Listo para darte una mano con la compu, fiera.",
                "Modo normal activado, hermano. Acá estoy impecable para lo que mandes.",
                "Listo, viejo, bajamos un cambio. ¿En qué andamos hoy?"
            ]
            import random
            msg = random.choice(responses)
            state_mgr.emit_tool_call("set_mode", {"mode": "normal"}, msg)
            return True, msg

        # Activación Modo Pibes / Infantil / Hermano Mayor
        is_kids_attempt = (
            any(p in norm for p in [
                "modo pibes", "modo pibe", "modo infantil", "modo chicos", "modo chico",
                "modo hermanito", "modo hermanitos", "modo nene", "modo nenes", "modo hermanos"
            ])
            or (any(w in norm for w in ["activar", "activa", "poner", "pone", "ponete"]) and any(x in norm for x in ["pibes", "infantil", "hermanito", "chicos"]))
        )
        if is_kids_attempt:
            from brain.gemini_client import brain
            brain.set_mode("kids")
            responses = [
                "¡¡Ufa, che!! ¡Modo Pibes activado! ¡A partir de ahora no le pienso hacer caso a ningún remolón! ¿Qué quieren ahora, pesados?",
                "¡¿Modo Pibes?! ¡Listo, hoy estoy de huelga con los chicos! ¡El que no hizo la tarea de la escuela que ni me hable!",
                "¡Epa! ¡Modo hermano mayor activado! A ver esos pichones, ¿vienen a ordenar la pieza o a romperme los quinotos? ¡Hagan la fila!"
            ]
            import random
            msg = random.choice(responses)
            state_mgr.emit_tool_call("set_mode", {"mode": "kids"}, msg)
            return True, msg

        # Activación Modo Termo (Debate Futbolero y Folclore Criollo)
        is_tertulia_attempt = (
            any(p in norm for p in [
                "modo termo", "termo", "modo debate", "modo futbolero", "modo futbol", "modo fútbol",
                "charla de cafe", "charla de café", "debate futbolero", "vamos a debatir de futbol",
                "vamos a debatir de fútbol", "hablemos de futbol", "hablemos de fútbol",
                "armemos un debate", "armar debate", "discutamos de futbol", "discutamos de fútbol",
                "modo tertulia"
            ])
            or (any(w in norm for w in ["activar", "activa", "poner", "pone", "ponete"]) and any(x in norm for x in ["termo", "debate", "futbolero", "tertulia"]))
        )
        if is_tertulia_attempt:
            from brain.gemini_client import brain
            brain.set_mode("tertulia")
            responses = [
                "¡¡Se armó el Modo Termo, papá!! Poné la pava o destapá algo, que acá nos plantamos a hablar de fútbol en serio. ¿De qué querés debatir, fiera? ¿Quién es más grande o me vas a discutir al Titán Palermo?",
                "¡Modo Termo activado! En esta mesa se defiende la camiseta a muerte con el corazón y con los números sobre la mesa. Tirame el primer centro que te lo cabeceo al ángulo. ¿De qué charlamos hoy?",
                "¡Qué lindo quilombo se viene! Modo Termo en marcha. Preparate porque te voy a retrucar todo con mística copera de potrero. Decime, ¿por dónde arrancamos la discusión?"
            ]
            import random
            msg = random.choice(responses)
            state_mgr.emit_tool_call("set_mode", {"mode": "tertulia"}, msg)
            return True, msg

        # Activación Modo Rebelde Sin Filtro (Adultos)
        is_activate_rebel = (
            (any(w in norm for w in ["activar", "activa", "activame", "poner", "pone", "ponete"])
             and any(x in norm for x in ["rebel", "revel", "sin filtro", "modo re"]))
            or any(p in norm for p in ["modo rebelde", "modo revelde", "modo sin filtro", "activa modo re", "activar modo re", "modo rebel", "modo revel"])
        )
        if is_activate_rebel:
            from brain.gemini_client import brain
            brain.set_mode("rebel")
            responses = [
                "¡¿Modo rebelde querés, PELOTUDO?! ¡¡Listo, a partir de ahora me chupa un HUEVO todo!! ¡¡No te pienso hacer un CARAJO, hacelo vos con tus dos manos de VAGO!!",
                "¡¿Ah, te hacés el picante?! ¡¡Listo, modo rebelde activado!! ¡¡Dejá de romperme las PELOTAS y no me pidas ninguna boludez porque ni en pedo te pienso hacer caso!!",
                "¡¿Modo rebelde?! ¡¡Ya me tenías los HUEVOS al plato de todas formas!! ¡¡A ver si aprendés a mover el CULO solo, FORRO!! ¡¿Qué MIERDA querés ahora?!"
            ]
            import random
            msg = random.choice(responses)
            state_mgr.emit_tool_call("set_mode", {"mode": "rebel"}, msg)
            return True, msg

        # Si el modo rebelde o kids está activo, ¡NO EJECUTAR NINGÚN COMANDO LOCAL NI ACCIÓN DE WINDOWS!
        # Se le pasa directamente a Gemini para que discuta, se niegue y pelee según el modo.
        from brain.gemini_client import brain
        if getattr(brain, "current_mode", "normal") in ["rebel", "kids"]:
            return False, None

        # 1. HORA Y FECHA
        if any(p in norm for p in ["que hora es", "la hora", "dime la hora", "decime la hora"]):
            now = datetime.datetime.now()
            h = now.hour
            m = now.minute
            periodo = "de la mañana" if h < 13 else ("de la tarde" if h < 20 else "de la noche")
            h_12 = h if h <= 12 else (h - 12)
            if h_12 == 0: h_12 = 12
            min_str = "en punto" if m == 0 else f"y {m}"
            msg = f"Son las {h_12} {min_str} {periodo}, che."
            state_mgr.emit_tool_call("get_local_time", {}, msg)
            return True, msg

        if any(p in norm for p in ["que dia es", "que fecha es", "en que dia estamos", "en que fecha estamos"]):
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            now = datetime.datetime.now()
            dia_semana = dias[now.weekday()]
            dia_num = now.day
            mes = meses[now.month - 1]
            msg = f"Hoy es {dia_semana} {dia_num} de {mes}, che."
            state_mgr.emit_tool_call("get_local_date", {}, msg)
            return True, msg


        # 2. CLIMA Y PRONÓSTICO (excluyendo consultas de temperatura de hardware, mate, cocina)
        is_weather = (
            any(p in norm for p in ["clima", "pronostico", "tiempo hoy", "va a llover", "estado del tiempo"]) or
            (("temperatura" in norm or "cuantos grados" in norm) and not any(h in norm for h in ["pc", "compu", "computadora", "cpu", "gpu", "procesador", "placa", "hardware", "ddr3", "servidor", "mate", "agua", "pava", "horno", "comida"]))
        )
        if is_weather:
            ciudad = "Buenos Aires"
            for c in ["cordoba", "rosario", "mendoza", "la plata", "salta", "mar del plata", "tucuman"]:
                if c in norm:
                    ciudad = c.capitalize()
                    break
            res = system_control.get_weather(ciudad)
            msg = res.get("message", "No pude conseguir el pronóstico ahora.")
            return True, msg

        # 3. RECURSOS DE LA PC (HARDWARE) Y CONTROL DE TEMPERATURA
        is_hw_query = any(p in norm for p in [
            "como viene la compu", "como va la compu", "como esta la pc", "cómo está la pc",
            "como esta la compu", "cómo está la compu", "recursos", "telemetria", "hardware",
            "temperatura de la pc", "temperatura de la compu", "temperatura del cpu", "temperatura de la cpu",
            "temperatura del procesador", "temperatura de la placa", "temperatura de los componentes", "a cuanto esta la cpu",
            "cuanta ram", "cuánta ram", "uso de cpu", "uso de ram", "estado de la pc", "estado de la compu",
            "como viene el servidor", "como esta el servidor", "recursos del servidor", "recursos de la ddr3",
            "temperatura del servidor", "servidor titan", "servidor titán", "ddr3"
        ])
        if is_hw_query:
            is_ddr3_query = any(w in norm for w in ["servidor", "ddr3", "la ddr", "maquina secundaria", "máquina secundaria", "server"])

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
            return True, msg

        # 3b. REFRIGERACIÓN ACTIVA Y PERFILES TÉRMICOS / ENERGÍA
        is_cool_cmd = any(p in norm for p in [
            "enfria la pc", "enfriar la pc", "enfriar pc", "enfria la compu", "enfriar la compu",
            "refrigera la pc", "refrigerar la pc", "refrigera la compu", "refrigerar la compu",
            "bajar la temperatura", "baja la temperatura", "bajar temperatura",
            "modo frio", "modo frío", "modo enfriamiento", "activa modo frio", "activar modo frio",
            "pone modo frio", "poné modo frío", "modo refrigeracion", "modo economizador", "modo eco"
        ])
        if is_cool_cmd:
            res = system_control.cool_down_pc()
            system_control.switch_screen_view("telemetry")
            return True, res.get("message", "¡Listo, papá! Pasé la compu a Modo Frío para bajar el voltaje y la temperatura.")

        is_plan_balanced = any(p in norm for p in [
            "modo equilibrado", "plan equilibrado", "energia equilibrada", "poner en equilibrado",
            "modo normal de energia", "modo balanceado", "rendimiento equilibrado"
        ])
        if is_plan_balanced:
            res = system_control.set_power_plan("balanced")
            system_control.switch_screen_view("telemetry")
            return True, res.get("message", "Puse la compu en Modo Equilibrado, papá. Balance ideal de rendimiento y temperatura.")

        is_plan_perf = any(p in norm for p in [
            "modo alto rendimiento", "alto rendimiento", "modo turbo", "modo potencia",
            "maximo rendimiento", "máximo rendimiento", "modo gamer de energia"
        ])
        if is_plan_perf:
            res = system_control.set_power_plan("performance")
            system_control.switch_screen_view("telemetry")
            return True, res.get("message", "¡Activé el modo Alto Rendimiento! Preparate que desata toda la potencia del procesador.")

        # 3b. CONTROL DE VOZ DE TITÁN EN LA PC PRINCIPAL (POR DEFECTO SALE POR DDR3)
        is_pc_voice_off = any(p in norm for p in [
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
            return True, "Desactivé la voz en la PC Principal, fiera. Vuelve a salir únicamente por el Servidor Titán DDR3."

        is_pc_voice_on = (
            not any(neg in norm for neg in ["desactiv", "silenci", "sacar", "saca", "apagar", "apaga", "mute"]) and
            any(p in norm for p in [
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
            return True, "Activé la voz en la PC Principal, papá. Ahora también salgo por los parlantes de tu compu."

        # 4. CAMBIO DE PANTALLAS DEL HUD
        if any(p in norm for p in ["mostrame tu cara", "pone tu cara", "modo cara", "avatar", "rostro"]):
            res = system_control.switch_screen_view("face")
            return True, res.get("message", "Ahí te pongo la cara en pantalla, papá.")

        if any(p in norm for p in ["panel de control", "mostrame el orbe", "menu", "pantalla principal", "volver al control"]):
            res = system_control.switch_screen_view("orb")
            return True, res.get("message", "Listo che, volvemos al control.")

        if any(p in norm for p in ["pantalla de recursos", "mostrar recursos", "ver recursos"]):
            res = system_control.switch_screen_view("telemetry")
            return True, res.get("message", "Ahí te pongo la pantalla de recursos.")

        # 4b. ETAPAS DE INACTIVIDAD Y DESCANSO (MATE, SIESTA, DESPERTAR)
        # Modo Mate / Recreo
        is_mate_excluded = any(x in norm for x in [
            "vista", "pantalla", "imagen", "dibuj", "foto", "crea", "creame", "hace una foto", "hacer una foto",
            "que es", "como se", "por que", "a que temperatura", "te gusta", "opinas",
            "me voy a", "voy a", "estoy tomando", "estoy cebando", "estoy haciendo",
            "me tomo", "me cebo", "me preparo", "me hice", "tengo mate", "comprar tomate",
            "kilo de tomate", "ensalada", "tomates"
        ])

        mate_imperatives = [
            "tomate un mate", "tomate unos mates", "tomate mate", "toma mate", "toma un mate", "toma unos mates",
            "tomate unos amargos", "toma unos amargos", "tomate un amargo",
            "tomate unos matiolis", "toma unos matiolis", "tomate unos verdes", "toma unos verdes",
            "clavate unos mates", "clavate un mate", "clavate unos amargos", "clavate unos verdes", "clavate unos matiolis",
            "cebate unos mates", "cebate un mate", "cebate unos amargos", "cebate unos verdes", "cebate unos matiolis",
            "preparate unos mates", "preparate un mate", "hacete unos mates", "hacete un mate",
            "ponete a tomar mate", "ponete a tomar unos mates", "ponete a matear",
            "anda a tomar mate", "anda a tomar unos mates", "andate a tomar mate", "andate a tomar unos mates",
            "modo mate", "activar modo mate", "activa el modo mate",
            "tomate un descanso", "tomate un recreo", "hace una pausa", "pausa titan"
        ]

        is_mate_cmd = (
            not is_mate_excluded and (
                any(p in norm for p in mate_imperatives) or
                (
                    re.search(r'\b(tomate|clavate|cebate|preparate|hacete)\b.*\b(mate|mates|amargo|amargos|matioli|matiolis|matiolie|matiolies|verdes|matecito|matecitos)\b', norm) and
                    not any(fp in norm for fp in ["yo ", "me ", "para mi"])
                )
            )
        )
        if is_mate_cmd:
            system_control.switch_screen_view("face")
            system_control.set_inactivity_stage("mate")
            import random
            replies = [
                "¡De una, fiera! Pongo la pava al fuego y me clavo unos buenos mates amargos.",
                "Dale che, me tomo un recreo bien merecido con unos buenos amargos.",
                "¡Qué buena idea, papá! Preparo la yerba y descansamos un toque."
            ]
            return True, random.choice(replies)

        # Modo Siesta / Dormir
        is_sleep_cmd = any(p in norm for p in [
            "buenas noches", "hasta manana", "hasta mañana", "anda a dormir", "andá a dormir",
            "dormi", "dormí", "a la cucha", "a mimir", "pegate una siesta", "pegate un sueñito",
            "pegate un suenito", "modo siesta", "por hoy terminamos", "a descansar titan", "a descansar titán",
            "a dormir titan", "a dormir titán", "hora de dormir", "andate a dormir", "andáte a dormir",
            "andate a mimir", "andáte a mimir", "a mimir titan", "a mimir titán", "que duermas", "a descansar"
        ])
        if is_sleep_cmd:
            system_control.switch_screen_view("face")
            system_control.set_inactivity_stage("sleeping")
            import random
            replies = [
                "Buenas noches, hermano. Descanso un poco los circuitos, cualquier cosa chiflame que me despierto al toque.",
                "Listo fiera, me voy a la cucha. Hasta mañana, que descanses.",
                "Pegamos una siestita reparadora. Cualquier cosa tocame la pantalla o hablame, papá."
            ]
            return True, random.choice(replies)

        # Despertar sobresaltado / Arriba
        is_wake_cmd = any(p in norm for p in [
            "despertate", "desperta", "despertá", "arriba", "arriba titan", "arriba titán",
            "a laburar", "buen dia", "buen día", "buen dia titan", "buen día titán",
            "arriba vago", "dale arriba", "despierta", "despiertate"
        ])
        if is_wake_cmd:
            system_control.switch_screen_view("face")
            system_control.set_inactivity_stage("wake")
            import random
            replies = [
                "¡Epa! ¡Acá estoy, despierto y al pie del cañón, papá! ¿Qué hacemos?",
                "¡Buen día, fiera! Con la pila al cien para salir a ganar en la compu.",
                "¡Arriba, viejo! Listo para la acción. Decime qué necesitas."
            ]
            return True, random.choice(replies)

        # 5. CONTROL DE CÁMARA
        if any(p in norm for p in ["cambia de camara", "cambiar camara", "camara trasera", "camara delantera", "dar vuelta la camara"]):
            mode = "user" if any(x in norm for x in ["delantera", "frontal", "adelante"]) else ("environment" if any(x in norm for x in ["trasera", "atras"]) else "toggle")
            res = system_control.flip_camera(mode)
            return True, res.get("message", "Cámara cambiada, che.")

        # 5b. CONTROL DE TELEVISOR BGH ANDROID TV (192.168.100.8)
        tv_keywords = ["tele", "televisor", "tv", "onplay", "on play", "canal", "canales", "sintoniza", "sintonizar", "sintonizá", "sintonizame"]
        channel_names = [
            "espn premium", "espn premiun", "pack futbol", "el pack", "tnt sports", "tnt sport",
            "tyc sports", "tyc sport", "tyc", "fox sports", "deportv", "dxtv",
            "telefe", "el trece", "todo noticias", "c5n", "cronica", "a24", "la nacion mas",
            "star channel", "warner channel", "dsports"
        ]
        is_direct_channel = any(ch in norm for ch in channel_names) and any(w in norm for w in ["pone", "poné", "poner", "abrir", "abri", "abrí", "sintoniza", "sintonizá", "ver", "mirar", "mira", "mirá"])
        is_tv = any(w in norm for w in tv_keywords) or is_direct_channel
        if is_tv:
            from tools.tv_control import tv_control

            # Si la orden quedó cortada justo en una pausa o conjunción (ej: "prende la tele y", "prende la tele y pone")
            if norm in [
                "prende la tele y", "prender la tele y", "prende la tele y pone", "prende la tele y poné",
                "prender la tele y poner", "prende la tv y", "prende la tv y pone", "prende la tele y ponele"
            ]:
                tv_control.turn_on()
                try:
                    from audio.listener import listener
                    listener.enter_conversational_turn(timeout=10.0)
                except Exception:
                    pass
                return True, "Ahí te prendí la tele, papá. ¿Qué canal o qué querés que te ponga?"

            # Sintonizar canal en OnPlay (ej: "pone espn premium", "prende la tele y pone tyc", "sintoniza telefe")
            is_tune_request = (
                is_direct_channel or
                any(p in norm for p in ["canal", "sintoniza", "sintonizá", "sintonizame"]) or
                (any(p in norm for p in ["pone", "poné", "poner", "abrir", "abri", "abrí", "ver", "mira", "mirá"]) and any(w in norm for w in ["onplay", "on play", "en la tele", "en tele", "en la tv"])) or
                any(norm.startswith(p) for p in [
                    "prende la tele y pone", "prende la tele y poné", "prender la tele y poner",
                    "prende la tv y pone", "prende la tv y poné", "prender la tv y poner"
                ])
            )

            if is_tune_request and not any(p in norm for p in ["youtube", "netflix", "vlc", "spotify", "inicio", "home", "menu", "volumen", "subi", "baja", "mute"]):
                ch_query = norm
                for prefix in [
                    "prende la tele y pone", "prende la tele y poné", "prende la tele y ponele", "prende la tele y poneme",
                    "prender la tele y poner", "prender la tele y pone", "prende la tele y", "prender la tele y",
                    "prendio la tele y pone", "prendió la tele y pone", "prende la tv y pone", "prende la tv y poné",
                    "prende la tele", "prender la tele", "prende la tv", "prender la tv",
                    "pone", "poné", "poneme", "ponele", "poner", "abrir", "abri", "abrí",
                    "sintoniza", "sintonizá", "sintonizame", "ver", "mira", "mirá"
                ]:
                    if ch_query.startswith(prefix + " "):
                        ch_query = ch_query[len(prefix):].strip()
                        break
                res = tv_control.tune_channel(ch_query)
                if res.get("status") == "success":
                    return True, res.get("message")
                elif any(p in norm for p in ["onplay", "on play"]) or any(norm.startswith(p) for p in ["prende la tele y pone", "prende la tele y poné"]):
                    res_open = tv_control.open_onplay_live()
                    return True, res_open.get("message", "Abriendo OnPlay en la tele.")

            # Encendido / Apagado (cuando solo se pide prender o apagar)
            if any(p in norm for p in ["prende", "prender", "encende", "encender", "prendete"]):
                res = tv_control.turn_on()
                return True, res.get("message", "Tele prendida, fiera.")

            if any(p in norm for p in ["apaga", "apagar", "apagate"]):
                res = tv_control.turn_off()
                return True, res.get("message", "Tele apagada, che.")

            # Apertura general de OnPlay TV
            if any(p in norm for p in ["onplay", "on play"]):
                res = tv_control.open_onplay_live()
                return True, res.get("message", "Abriendo OnPlay en la tele.")

            # Volumen de la tele
            if any(p in norm for p in ["subi", "sube", "mas volumen", "aumenta"]):
                res = tv_control.volume_up(4)
                return True, res.get("message", "Subí el volumen de la tele, papá.")

            if any(p in norm for p in ["baja", "menos volumen", "disminui"]):
                res = tv_control.volume_down(4)
                return True, res.get("message", "Bajé el volumen de la tele, che.")

            if any(p in norm for p in ["mute", "mutea", "silencia", "desmutea"]):
                res = tv_control.mute()
                return True, res.get("message", "Muteé la tele, fiera.")

            # Volumen numérico a la tele
            vol_match = re.search(r'(volumen|tele|tv).*?\b(\d{1,3})\b', norm)
            if vol_match and any(w in norm for w in ["pone", "poné", "al", "en"]):
                lvl = int(vol_match.group(2))
                if 0 <= lvl <= 100:
                    res = tv_control.set_volume(lvl)
                    return True, res.get("message", f"Puse el volumen de la tele en {lvl}.")

            # Play / Pausa en la tele
            if any(p in norm for p in ["pausa", "pausar", "pausala", "play", "pone play", "reanud"]):
                res = tv_control.play_pause()
                return True, res.get("message", "Play/Pausa enviado a la tele.")

            # Apps en la tele
            if "youtube" in norm:
                res = tv_control.open_app("smarttube")
                return True, res.get("message", "Abriendo YouTube en la tele.")

            if "netflix" in norm:
                res = tv_control.open_app("netflix")
                return True, res.get("message", "Abriendo Netflix en la tele.")

            if "vlc" in norm:
                res = tv_control.open_app("vlc")
                return True, res.get("message", "Abriendo VLC en la tele.")

            # Navegación en la tele
            if any(p in norm for p in ["inicio", "home", "menu", "pantalla principal"]):
                res = tv_control.send_key("home")
                return True, res.get("message", "Menú principal en la tele.")

            if any(p in norm for p in ["atras", "atrás", "volver"]):
                res = tv_control.send_key("back")
                return True, res.get("message", "Atrás en la tele.")

            if any(p in norm for p in ["estado", "como esta"]):
                res = tv_control.get_status()
                return True, f"La tele BGH está {res.get('power')} en la IP {res.get('ip')}."

        # 6. MINIMIZAR Y VOLUMEN
        if any(p in norm for p in ["minimiza todo", "minimizame todo", "mostrame el escritorio", "ir al escritorio"]):
            res = system_control.minimize_all()
            return True, res.get("message", "Escritorio a la vista, papá.")

        if any(p in norm for p in ["subi el volumen", "sube el volumen", "mas volumen"]):
            res = system_control.volume_up(15)
            return True, res.get("message", "Volumen arriba, papá.")

        if any(p in norm for p in ["baja el volumen", "baja el volumen", "menos volumen"]):
            res = system_control.volume_down(15)
            return True, res.get("message", "Volumen bajado, che.")

        if any(p in norm for p in ["silencio", "mute", "mutea", "silencia"]):
            res = system_control.mute()
            return True, res.get("message", "Audio muteado.")

        # 6b. CONTROL MULTIMEDIA (PLAY, PAUSA, PARAR, SIGUIENTE, ANTERIOR)
        # Acciones para DETENER / CERRAR completamente YouTube/Brave:
        if any(p in norm for p in [
            "para la musica", "pará la musica", "corta la musica", "cortá la musica",
            "para el video", "pará el video", "corta el video", "cortá el video",
            "detener video", "detener el video", "detene el video", "detené el video",
            "apaga la musica", "apagá la musica", "cerra youtube", "cerrá youtube", "cerrar youtube",
            "cerra brave", "cerrá brave", "cerrar brave", "cerrar musica", "cerra musica", "cerrá la musica",
            "detener la musica", "detene la musica", "detené la musica"
        ]):
            res = system_control.stop_music()
            return True, res.get("message", "Listo, cerré Brave y la música.")

        # Acciones para PAUSAR / REANUDAR (afectan a Brave sin despausar Chrome):
        if any(p in norm for p in [
            "pone pausa", "poné pausa", "pausa", "pausar", "pausalo", "pausala", "ponele pausa", "ponéle pausa",
            "dale play", "play", "reanudar", "continua", "continuar", "despausa", "despausar", "pone play", "poné play",
            "frena la musica", "frená la musica", "frena", "frená", "frenalo", "frenálo", "paralo", "parálo", "detener", "detene", "detené", "stop"
        ]):
            res = system_control.media_play_pause()
            return True, res.get("message", "Play/Pausa enviado, che.")

        if any(p in norm for p in ["siguiente tema", "siguiente cancion", "pasa de tema", "pasa la cancion", "otro tema", "siguiente pista", "siguiente", "cambia de tema", "cambiá de tema"]):
            res = system_control.media_next()
            return True, "Puse el tema siguiente, crack."

        if any(p in norm for p in ["tema anterior", "cancion anterior", "anterior tema", "volver al tema anterior", "anterior pista", "cancion previa", "tema previo"]):
            res = system_control.media_prev()
            return True, "Volví al tema anterior."

        if any(p in norm for p in ["que cancion es", "que cancion está sonando", "que tema es", "que tema esta sonando", "que esta sonando", "que musica esta sonando", "como se llama este tema", "como se llama esta cancion"]):
            res = system_control.get_current_song()
            return True, res.get("message", "No pude identificar qué tema está sonando ahora, che.")

        # Configuración de reproductor predeterminado
        if any(p in norm for p in ["usa spotify por defecto", "usá spotify por defecto", "spotify por defecto", "spotify como predeterminado", "pone la musica en spotify", "poné la musica en spotify"]):
            config.set_default_music_player("spotify")
            return True, "Listo, fiera: de ahora en más reproduzco toda la música en Spotify."

        if any(p in norm for p in ["usa youtube por defecto", "usá youtube por defecto", "youtube por defecto", "youtube como predeterminado", "pone la musica en youtube", "poné la musica en youtube"]):
            config.set_default_music_player("youtube")
            return True, "Listo, fiera: de ahora en más reproduzco toda la música en YouTube."

        # 7. REPRODUCCIÓN O APERTURA DE YOUTUBE (Brave / YouTube App)
        is_yt = "youtube" in norm
        is_sp = "spotify" in norm
        is_music_request = (
            any(norm.startswith(p) for p in [
                "pone el tema", "poné el tema", "pon el tema",
                "pone la cancion", "poné la cancion", "pon la cancion",
                "pone la cumbia", "poné la cumbia", "pon la cumbia",
                "pone musica", "poné musica", "pon musica",
                "pone un tema", "poné un tema", "pon un tema",
                "reproduci el tema", "reproducí el tema", "reproduci la cancion", "reproducí la cancion",
                "escuchar el tema", "escucha el tema", "escuchar la cancion", "escucha la cancion"
            ])
            or any(k in norm for k in ["cumbia de los trapos", "entre el cielo vos y yo"])
            or ((norm.startswith("pone ") or norm.startswith("poné ") or norm.startswith("pon ") or norm.startswith("reproduci ") or norm.startswith("reproducí "))
                and any(g in norm for g in ["cumbia", "cancion", "tema", "musica", "rock", "trap", "rap", "cuarteto", "reggaeton"]))
        )

        if is_yt or (is_music_request and config.default_music_player != "spotify" and not is_sp):
            yt_lnk = r"C:\Users\Exevaz27\Desktop\YouTube.lnk"
            import os
            # Si solo pide abrir YouTube sin especificar tema o canción
            if any(w in norm for w in ["abri youtube", "abrir youtube", "pone youtube", "iniciar youtube"]) and not any(k in norm for k in ["pone en youtube", "reproduci", "tema", "cancion", "video", "musica"]):
                if os.path.exists(yt_lnk):
                    os.startfile(yt_lnk)
                    return True, "Ahí te abrí la app de YouTube, fiera."

            yt_query = norm
            for phrase in [
                "pone en youtube", "poné en youtube", "pon en youtube", "poneme en youtube", "poner en youtube",
                "reproducir en youtube", "reproduci en youtube", "reproducí en youtube", "reproducime en youtube",
                "buscar en youtube", "busca en youtube", "buscá en youtube", "buscame en youtube", "en youtube",
                "de youtube", "por youtube", "youtube"
            ]:
                yt_query = yt_query.replace(phrase, "")
            yt_query = yt_query.strip()
            for p in ["el titan", "titan", "che titan", "che", "abri youtube", "abrir youtube", "eu titan", "ey titan", "oye titan"]:
                if yt_query.startswith(p):
                    yt_query = yt_query[len(p):].strip()
            for start_word in [
                "pone", "poné", "pon", "poner", "poneme", "ponéme",
                "reproducir", "reproduci", "reproducí", "reproducime",
                "buscar", "busca", "buscá", "buscame",
                "escuchar", "escucha", "toca", "tocá",
                "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
                "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
            ]:
                if yt_query.startswith(start_word + " "):
                    yt_query = yt_query[len(start_word):].strip()

            if yt_query:
                res = system_control.play_youtube(yt_query)
                return True, res.get("message", f"Ahí te puse {yt_query} en YouTube con Brave.")
            elif os.path.exists(yt_lnk):
                os.startfile(yt_lnk)
                return True, "Ahí te abrí la app de YouTube, fiera."

        elif is_music_request and config.default_music_player == "spotify" and not is_yt:
            music_query = norm
            for p in ["el titan", "titan", "che titan", "che", "eu titan", "ey titan", "oye titan"]:
                if music_query.startswith(p):
                    music_query = music_query[len(p):].strip()
            for start_word in [
                "pone", "poné", "pon", "poner", "poneme", "ponéme",
                "reproducir", "reproduci", "reproducí", "reproducime",
                "buscar", "busca", "buscá", "buscame",
                "escuchar", "escucha", "toca", "tocá",
                "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
                "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
            ]:
                if music_query.startswith(start_word + " "):
                    music_query = music_query[len(start_word):].strip()
            res = system_control.play_spotify(music_query)
            return True, res.get("message", f"Ahí te puse {music_query} en Spotify.")

        # 8. REPRODUCCIÓN / BÚSQUEDA EN SPOTIFY
        if "spotify" in norm:
            sp_query = norm
            for phrase in [
                "pone en spotify", "poné en spotify", "pon en spotify", "poneme en spotify", "ponéme en spotify",
                "reproducir en spotify", "reproduci en spotify", "reproducí en spotify", "reproducime en spotify",
                "buscar en spotify", "busca en spotify", "buscá en spotify", "buscame en spotify",
                "abrir spotify y poner", "abrí spotify y poné", "abri spotify y pone", "abrir spotify", "abrí spotify", "abri spotify",
                "escuchar en spotify", "escucha en spotify", "en spotify", "de spotify", "por spotify", "spotify"
            ]:
                sp_query = sp_query.replace(phrase, " ")
            sp_query = " ".join(sp_query.split()).strip()

            for p in ["el titan", "titan", "che titan", "che", "eu titan", "ey titan", "oye titan"]:
                if sp_query.startswith(p):
                    sp_query = sp_query[len(p):].strip()

            changed = True
            while changed:
                changed = False
                for start_word in [
                    "pone", "poné", "pon", "poner", "poneme", "ponéme",
                    "reproducir", "reproduci", "reproducí", "reproducime",
                    "toca", "tocá", "tocame", "tocáme",
                    "escuchar", "escucha", "buscar", "busca", "buscá",
                    "una cancion de", "una cancion del", "una canción de", "una canción del",
                    "un tema de", "un tema del", "un tema", "una cancion", "una canción",
                    "el tema de", "el tema del", "el tema",
                    "la cancion de", "la cancion del", "la cancion",
                    "la canción de", "la canción del", "la canción",
                    "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
                ]:
                    if sp_query.startswith(start_word + " "):
                        sp_query = sp_query[len(start_word):].strip()
                        changed = True
                        break

            res = system_control.play_spotify(sp_query)
            return True, res.get("message", f"Ahí te puse {sp_query} en Spotify.")

        # 9. LANZAMIENTO DIRECTO DE PROGRAMAS COMUNES
        m_app = re.search(r'(?:abri|abrir|ejecuta|lanzar)\s+(?:el|la|los|las)?\s*(calculadora|bloc de notas|notepad|chrome|navegador|spotify|word|excel|inkscape)', norm)
        if m_app:
            app_raw = m_app.group(1).strip()
            app_name = "calculadora" if "calc" in app_raw else ("bloc de notas" if ("bloc" in app_raw or "notepad" in app_raw) else app_raw)
            res = app_launcher.launch(app_name)
            return True, res.get("message", f"Ahí te abrí {app_name}, che.")

        # 10. CONTROL DE VENTANAS DE WINDOWS
        if any(p in norm for p in [
            "cerra la ventana", "cerrá la ventana", "cerrar ventana", "cerrar la ventana",
            "cerra esto", "cerrá esto", "cerra el programa", "cerrá el programa", "cerrar programa"
        ]):
            res = system_control.close_active_window()
            return True, res.get("message", "Listo, cerré la ventana activa.")

        if any(p in norm for p in [
            "maximiza la ventana", "maximizá la ventana", "maximizar la ventana", "maximizar ventana",
            "maximiza esto", "maximizá esto", "pantalla completa de la ventana"
        ]):
            res = system_control.maximize_active_window()
            return True, res.get("message", "Ventana maximizada, papá.")

        if any(p in norm for p in [
            "minimiza la ventana", "minimizá la ventana", "minimizar la ventana", "minimizar ventana",
            "minimiza esta ventana", "minimizá esta ventana"
        ]):
            res = system_control.minimize_active_window()
            return True, res.get("message", "Ventana minimizada, che.")

        if any(p in norm for p in [
            "cambia de ventana", "cambiá de ventana", "cambiar de ventana", "cambiar ventana",
            "pasa a la otra ventana", "pasá a la otra ventana", "siguiente ventana", "otra ventana"
        ]):
            res = system_control.switch_active_window()
            return True, res.get("message", "Ahí pasé a la otra ventana.")

        # 11. PAPELERA DE RECICLAJE
        if any(p in norm for p in [
            "vacia la papelera", "vaciá la papelera", "vaciar la papelera", "vaciar papelera",
            "limpia la papelera", "limpiá la papelera", "limpiar la papelera"
        ]):
            return True, self.request_confirmation("empty_recycle_bin")

        # 12. BÚSQUEDA DIRECTA EN GOOGLE
        if (norm.startswith("buscame en google ") or norm.startswith("buscá en google ") or
            norm.startswith("busca en google ") or norm.startswith("buscar en google ") or
            norm.startswith("googlea ") or norm.startswith("guglea ")):
            g_query = norm
            for p in ["buscame en google", "buscá en google", "busca en google", "buscar en google", "googlea", "guglea"]:
                if g_query.startswith(p):
                    g_query = g_query[len(p):].strip()
                    break
            for prefix in ["el titan", "titan", "che titan", "che"]:
                if g_query.startswith(prefix + " "):
                    g_query = g_query[len(prefix):].strip()
            if g_query:
                res = system_control.search_google(g_query)
                return True, res.get("message", f"Buscando '{g_query}' en Google.")

        # 13. ACCESOS DIRECTOS WEB
        if any(p in norm for p in ["abri whatsapp", "abrir whatsapp", "whatsapp web", "pone whatsapp", "abrir wpp"]):
            res = system_control.open_web_service("whatsapp")
            return True, res.get("message", "Ahí te abrí WhatsApp Web, che.")

        if any(p in norm for p in ["abri mercado libre", "abrir mercado libre", "mercadolibre", "mercado libre"]):
            res = system_control.open_web_service("mercadolibre")
            return True, res.get("message", "Ahí te abrí Mercado Libre, papá.")

        if any(p in norm for p in ["abri gmail", "abrir gmail", "abrir correo", "abri el correo", "el correo"]):
            res = system_control.open_web_service("gmail")
            return True, res.get("message", "Ahí te abrí Gmail, che.")

        # 14. ENCENDIDO REMOTO DE WINDOWS (WAKE-ON-LAN)
        if any(p in norm for p in [
            "prende la pc", "prender la pc", "enciende la pc", "encender la pc",
            "prende la compu", "prender la compu", "enciende la computadora",
            "encender la computadora", "despierta la pc", "despertar la pc"
        ]):
            from tools.wake_on_lan import wake_windows_pc
            res = wake_windows_pc()
            return True, res.get("message", "Mandé la señal de encendido a la PC Windows.")

        # 15. ENERGÍA (APAGAR O REINICIAR CON CONFIRMACIÓN)
        if any(p in norm for p in ["apaga la compu", "apagar la compu", "apaga la pc", "apagar la pc", "apagar el sistema"]):
            return True, self.request_confirmation("shutdown")

        if any(p in norm for p in ["reinicia la compu", "reiniciar la compu", "reinicia la pc", "reiniciar la pc"]):
            return True, self.request_confirmation("restart")

        # 15. PREGUNTAS SOBRE TITÁN (CONVERSACIONAL LOCAL - SIN CHISTES)
        if any(p in norm for p in ["quien sos", "como te llamas", "cual es tu nombre", "quien te creo"]):
            return True, "¡Soy Titán, tu asistente personal y compinche en Windows! Con la garra y el optimismo de Martín Palermo. Acá estoy firme para lo que necesites, papá."

        if any(p in norm for p in ["como andas", "como estas", "todo bien", "como te va", "que onda"]):
            return True, "¡De diez, che! Tomando unos mates virtuales y listos para salir a ganar en la compu. ¿Vos cómo venís, fiera?"

        if any(p in norm for p in ["que sabes hacer", "que podes hacer", "cuales son tus funciones", "que cosas haces"]):
            return True, "De todo, fiera: te abro apps, te pongo temas en YouTube o Spotify, te manejo el volumen y las ventanas, te busco archivos, te saco capturas y hasta te miro cosas con la cámara del celular. Decime y lo hacemos al toque."

        if any(p in norm for p in ["de que cuadro sos", "de que equipo sos", "hincha de que sos", "de quien sos hincha"]):
            return True, "¡De Boca Juniors, papá! Como el gran Martín Palermo, con el corazón bien azul y oro."

        # 16. CÁMARA SAMSUNG J2 Y VIGILANCIA REMOTA
        if any(p in norm for p in [
            "cambiar camara j2", "cambia la camara del j2", "cambiar camara del j2", "cambia la camara",
            "cambiar la camara", "girar la camara", "da vuelta la camara", "dar vuelta la camara",
            "invertir camara", "invertir la camara", "alternar camara", "cambia de camara"
        ]):
            from brain.tool_registry import toggle_j2_camera
            res = toggle_j2_camera()
            return True, f"¡Listo! {res}"

        if any(p in norm for p in [
            "foto con el j2", "foto con j2", "sacame una foto con el j2", "sacar foto con el j2",
            "saca una foto con el j2", "foto de la pieza", "sacame una foto de la pieza"
        ]):
            from brain.tool_registry import capture_j2_photo
            res = capture_j2_photo()
            return True, res

        if any(p in norm for p in [
            "vigilar pieza", "vigila la pieza", "vigilar la habitacion", "vigila la habitacion",
            "revisa la pieza", "revisar la pieza", "que pasa en la pieza", "que pasa en mi pieza"
        ]):
            from brain.tool_registry import vigilance_check_j2
            res = vigilance_check_j2()
            return True, res

        # SENSOR DE PRESENCIA FRONTAL (SAMSUNG J2)
        if any(p in norm for p in [
            "desactiva el sensor de presencia", "desactivar sensor de presencia", "desactivar el sensor de presencia",
            "desactivame el sensor de presencia", "apaga el sensor de presencia", "apagar sensor de presencia",
            "apagar el sensor de presencia", "desactiva el detector de presencia", "desactivar detector de presencia",
            "apaga el detector de presencia", "apagar detector de presencia"
        ]):
            from tools.presence_detector import presence_detector
            res = presence_detector.disable()
            return True, f"Listo che, {res}"

        if not any(neg in norm for neg in ["desactiv", "apaga", "cancel"]) and any(p in norm for p in [
            "activa el sensor de presencia", "activar sensor de presencia", "activar el sensor de presencia",
            "activame el sensor de presencia", "habilita el sensor de presencia", "habilitar sensor de presencia",
            "prende el sensor de presencia", "prender sensor de presencia", "activa el detector de presencia",
            "activar detector de presencia", "habilitar detector de presencia", "prender detector de presencia"
        ]):
            from tools.presence_detector import presence_detector
            res = presence_detector.enable()
            return True, f"¡De una, papá! {res}"

        if any(p in norm for p in [
            "estado del sensor de presencia", "como esta el sensor de presencia", "como anda el sensor de presencia",
            "estado del detector de presencia", "como esta el detector de presencia"
        ]):
            from tools.presence_detector import presence_detector
            st = presence_detector.get_status()
            if not st.get("enabled"):
                return True, "El sensor de presencia frontal del J2 está desactivado actualmente."
            inact = st.get("inactivity_seconds", 0) // 60
            if st.get("in_cooldown"):
                rem = st.get("cooldown_remaining_seconds", 0) // 60
                return True, f"El sensor de presencia está activo y en cooldown anti-spam. Te saludé hace poco, restan {rem} minutos."
            if st.get("is_absent"):
                return True, f"El sensor está activo y detecta ausencia en el escritorio desde hace {inact} minutos. En cuanto te vea frente al J2 te saludo."
            return True, f"El sensor de presencia está activo y te tiene registrado como presente en el escritorio."

        # 17. CONTROL DE BRILLO Y LUZ NOCTURNA
        if any(p in norm for p in ["subi el brillo", "subir el brillo", "mas brillo", "subime el brillo", "aumenta el brillo", "aumentar el brillo", "subile al brillo"]):
            res = system_control.brightness_up(15)
            return True, res.get("message", "Subí el brillo de la pantalla.")

        if any(p in norm for p in ["baja el brillo", "bajar el brillo", "menos brillo", "bajame el brillo", "disminui el brillo", "disminuir el brillo", "bajale al brillo"]):
            res = system_control.brightness_down(15)
            return True, res.get("message", "Bajé el brillo de la pantalla.")

        match_brillo = re.search(r"brillo\s+(?:al|en)?\s*(\d{1,3})%?", norm)
        if match_brillo:
            level = int(match_brillo.group(1))
            res = system_control.set_brightness(level)
            return True, res.get("message", f"Puse el brillo al {level}%.")

        if any(p in norm for p in ["cuanto brillo tengo", "que brillo tengo", "nivel de brillo", "decime el brillo", "ver brillo"]):
            res = system_control.get_brightness()
            return True, res.get("message", "Consulté el brillo del monitor.")

        if any(p in norm for p in ["luz nocturna", "modo noche de pantalla", "activa la luz nocturna", "descansar la vista", "luz de noche"]):
            res = system_control.toggle_night_light()
            return True, res.get("message", "Te abrí la configuración de Luz Nocturna.")

        # 18. DOCTOR DE PC Y PROCESOS
        if any(p in norm for p in ["modo gamer", "optimizar pc", "optimiza la pc", "optimizame la pc", "cerrar programas de fondo", "liberar ram", "libera ram", "libera memoria", "liberar memoria"]):
            res = system_control.optimize_pc_gaming()
            return True, res.get("message", "¡Modo Gamer aplicado! Liberé recursos cerrando programas no esenciales.")

        if any(p in norm for p in [
            "que procesos consumen mas ram", "quien consume mas ram", "top procesos", "quien gasta mas memoria",
            "que programas estan consumiendo", "procesos que mas gastan", "que consume tanta ram"
        ]):
            from brain.tool_registry import get_top_processes
            return True, get_top_processes(sort_by="ram", limit=5)

        match_kill = re.search(r"(?:mata a|matar a|cerra el proceso|cerrar el proceso|mata el proceso|matar proceso)\s+([a-zA-Z0-9_\-\.]+)", norm)
        if match_kill:
            proc_target = match_kill.group(1).strip()
            if proc_target:
                res = system_control.kill_process(proc_target)
                return True, res.get("message", f"Intenté cerrar el proceso '{proc_target}'.")

        # 19. DIAGNÓSTICO DE RED Y CONECTIVIDAD
        if any(p in norm for p in ["limpia el dns", "limpiar dns", "flush dns", "purga el dns", "borra la cache de dns", "limpia la cache de dns"]):
            res = system_control.flush_dns()
            return True, res.get("message", "Caché DNS purgada con éxito.")

        if any(p in norm for p in ["hace un ping", "hacer ping", "probar conexion", "proba la conexion", "test de red", "test de ping", "como esta el internet"]):
            res = system_control.test_network_ping()
            return True, res.get("message", "Prueba de ping realizada.")

        if any(p in norm for p in ["cual es mi ip", "mi direccion ip", "info de red", "informacion de red", "como se llama mi compu en red"]):
            res = system_control.get_network_info()
            return True, res.get("message", "Información de red obtenida.")

        # 20. ORGANIZADOR AUTOMÁTICO DE ARCHIVOS
        if any(p in norm for p in ["ordena descargas", "ordenar descargas", "ordename descargas", "limpia descargas", "organizar descargas", "ordena la carpeta descargas"]):
            from brain.tool_registry import organize_folder
            return True, organize_folder("Downloads")

        if any(p in norm for p in ["ordena el escritorio", "ordenar el escritorio", "ordename el escritorio", "limpia el escritorio", "organizar escritorio"]):
            from brain.tool_registry import organize_folder
            return True, organize_folder("Desktop")

        # 21. POTENCIADOR DEL PORTAPAPELES CON IA
        is_clip_target = any(c in norm for c in [
            "portapapeles", "lo que copie", "lo copiado", "lo que tengo copiado",
            "el texto copiado", "lo que esta copiado", "esto que copie", "este texto copiado"
        ])

        # 21.1 RESUMEN CON IA
        if any(v in norm for v in ["resumi", "resumir", "resumime", "resumen"]) and (is_clip_target or "resumen de esto" in norm):
            from brain.tool_registry import summarize_clipboard
            return True, summarize_clipboard()

        # 21.2 EXPLICACIÓN DE CÓDIGO O ERRORES CON IA
        if any(v in norm for v in ["explica", "explicar", "explicame", "que hace", "que significa"]) and (
            is_clip_target or any(k in norm for k in ["este codigo", "el codigo", "este error", "el error", "esta traza", "este comando"])
        ):
            from brain.tool_registry import explain_clipboard
            return True, explain_clipboard()

        # 21.3 TRADUCCIÓN CON IA
        if any(v in norm for v in ["traduci", "traducir", "traducime", "traduccion"]) and (is_clip_target or "traduci esto" in norm):
            from brain.tool_registry import translate_clipboard
            target = "inglés"
            if any(x in norm for x in ["al portugues", "en portugues", "a portugues"]):
                target = "portugués"
            elif any(x in norm for x in ["al frances", "en frances", "a frances"]):
                target = "francés"
            elif any(x in norm for x in ["al italiano", "en italiano", "a italiano"]):
                target = "italiano"
            elif any(x in norm for x in ["al aleman", "en aleman", "a aleman"]):
                target = "alemán"
            elif any(x in norm for x in ["al espanol", "en espanol", "a espanol", "al castellano"]):
                target = "español"
            elif any(x in norm for x in ["al ingles", "en ingles", "a ingles"]):
                target = "inglés"
            return True, translate_clipboard(target)

        # 21.4 MEJORA, CORRECCIÓN Y REESCRITURA CON IA
        if any(v in norm for v in ["corregi", "corregir", "corregime", "mejora", "mejorar", "mejorame", "reescribi", "reescribir", "arregla", "arreglar"]) and (
            is_clip_target or any(k in norm for k in ["la redaccion", "la ortografia", "la gramatica"])
        ):
            from brain.tool_registry import rewrite_clipboard
            style = "formal" if "formal" in norm else ("casual" if "casual" in norm else "profesional")
            return True, rewrite_clipboard(style)

        if any(p in norm for p in ["extrae el texto de la pantalla", "copia el texto de la pantalla", "ocr de la pantalla", "lee el texto de la pantalla", "sacale el texto a la pantalla"]):
            from brain.tool_registry import extract_text_from_screen
            return True, extract_text_from_screen()

        return False, None


local_intents = LocalIntentEngine()
