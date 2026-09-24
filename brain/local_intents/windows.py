"""Programas, ventanas, papelera, energía, brillo y Wake-on-LAN.."""

from ._common import _mip
import re
from tools.system_control import system_control
from tools.app_launcher import app_launcher

from typing import Optional

def handle_apps(engine, text, clean, norm) -> "Optional[str]":
    """9. LANZAMIENTO DIRECTO DE PROGRAMAS COMUNES."""
    m_app = re.search(r'(?:abri|abrir|ejecuta|lanzar)\s+(?:el|la|los|las)?\s*(calculadora|bloc de notas|notepad|chrome|navegador|spotify|word|excel|inkscape)', norm)
    if m_app:
        app_raw = m_app.group(1).strip()
        app_name = "calculadora" if "calc" in app_raw else ("bloc de notas" if ("bloc" in app_raw or "notepad" in app_raw) else app_raw)
        res = app_launcher.launch_app(app_name)
        return res.get("message", f"Ahí te abrí {app_name}, che.")


def handle_window_control(engine, text, clean, norm) -> "Optional[str]":
    """10. CONTROL DE VENTANAS DE WINDOWS."""
    if any(_mip(norm, p) for p in [
        "cerra la ventana", "cerrá la ventana", "cerrar ventana", "cerrar la ventana",
        "cerra esto", "cerrá esto", "cerra el programa", "cerrá el programa", "cerrar programa"
    ]):
        res = system_control.close_active_window()
        return res.get("message", "Listo, cerré la ventana activa.")

    if any(_mip(norm, p) for p in [
        "maximiza la ventana", "maximizá la ventana", "maximizar la ventana", "maximizar ventana",
        "maximiza esto", "maximizá esto", "pantalla completa de la ventana"
    ]):
        res = system_control.maximize_active_window()
        return res.get("message", "Ventana maximizada, papá.")

    if any(_mip(norm, p) for p in [
        "minimiza la ventana", "minimizá la ventana", "minimizar la ventana", "minimizar ventana",
        "minimiza esta ventana", "minimizá esta ventana"
    ]):
        res = system_control.minimize_active_window()
        return res.get("message", "Ventana minimizada, che.")

    if any(_mip(norm, p) for p in [
        "cambia de ventana", "cambiá de ventana", "cambiar de ventana", "cambiar ventana",
        "pasa a la otra ventana", "pasá a la otra ventana", "siguiente ventana", "otra ventana"
    ]):
        res = system_control.switch_active_window()
        return res.get("message", "Ahí pasé a la otra ventana.")


def handle_recycle(engine, text, clean, norm) -> "Optional[str]":
    """11. PAPELERA DE RECICLAJE."""
    if any(_mip(norm, p) for p in [
        "vacia la papelera", "vaciá la papelera", "vaciar la papelera", "vaciar papelera",
        "limpia la papelera", "limpiá la papelera", "limpiar la papelera"
    ]):
        return engine.request_confirmation("empty_recycle_bin")


def handle_wol(engine, text, clean, norm) -> "Optional[str]":
    """14. ENCENDIDO REMOTO DE WINDOWS (WAKE-ON-LAN)."""
    if any(_mip(norm, p) for p in [
        "prende la pc", "prender la pc", "enciende la pc", "encender la pc",
        "prende la compu", "prender la compu", "enciende la computadora",
        "encender la computadora", "despierta la pc", "despertar la pc"
    ]):
        from tools.wake_on_lan import wake_windows_pc
        res = wake_windows_pc()
        return res.get("message", "Mandé la señal de encendido a la PC Windows.")


def handle_power(engine, text, clean, norm) -> "Optional[str]":
    """15. ENERGÍA (APAGAR O REINICIAR CON CONFIRMACIÓN)."""
    if any(_mip(norm, p) for p in ["apaga la compu", "apagar la compu", "apaga la pc", "apagar la pc", "apagar el sistema"]):
        return engine.request_confirmation("shutdown")

    if any(_mip(norm, p) for p in ["reinicia la compu", "reiniciar la compu", "reinicia la pc", "reiniciar la pc"]):
        return engine.request_confirmation("restart")


def handle_brightness(engine, text, clean, norm) -> "Optional[str]":
    """17. CONTROL DE BRILLO Y LUZ NOCTURNA."""
    if any(_mip(norm, p) for p in ["subi el brillo", "subir el brillo", "mas brillo", "subime el brillo", "aumenta el brillo", "aumentar el brillo", "subile al brillo"]):
        res = system_control.brightness_up(15)
        return res.get("message", "Subí el brillo de la pantalla.")

    if any(_mip(norm, p) for p in ["baja el brillo", "bajar el brillo", "menos brillo", "bajame el brillo", "disminui el brillo", "disminuir el brillo", "bajale al brillo"]):
        res = system_control.brightness_down(15)
        return res.get("message", "Bajé el brillo de la pantalla.")

    match_brillo = re.search(r"brillo\s+(?:al|en)?\s*(\d{1,3})%?", norm)
    if match_brillo:
        level = int(match_brillo.group(1))
        res = system_control.set_brightness(level)
        return res.get("message", f"Puse el brillo al {level}%.")

    if any(_mip(norm, p) for p in ["cuanto brillo tengo", "que brillo tengo", "nivel de brillo", "decime el brillo", "ver brillo"]):
        res = system_control.get_brightness()
        return res.get("message", "Consulté el brillo del monitor.")

    if any(_mip(norm, p) for p in ["luz nocturna", "modo noche de pantalla", "activa la luz nocturna", "descansar la vista", "luz de noche"]):
        res = system_control.toggle_night_light()
        return res.get("message", "Te abrí la configuración de Luz Nocturna.")
