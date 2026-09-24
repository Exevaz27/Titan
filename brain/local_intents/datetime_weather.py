"""Hora/fecha y clima.."""

from ._common import _mip
import datetime
from core.state_manager import state_mgr
from tools.system_control import system_control

from typing import Optional

def handle_datetime(engine, text, clean, norm) -> "Optional[str]":
    """1. HORA Y FECHA."""
    if any(_mip(norm, p) for p in ["que hora es", "la hora", "dime la hora", "decime la hora"]):
        now = datetime.datetime.now()
        h = now.hour
        m = now.minute
        periodo = "de la mañana" if h < 13 else ("de la tarde" if h < 20 else "de la noche")
        h_12 = h if h <= 12 else (h - 12)
        if h_12 == 0: h_12 = 12
        min_str = "en punto" if m == 0 else f"y {m}"
        msg = f"Son las {h_12} {min_str} {periodo}, che."
        state_mgr.emit_tool_call("get_local_time", {}, msg)
        return msg

    if any(_mip(norm, p) for p in ["que dia es", "que fecha es", "en que dia estamos", "en que fecha estamos"]):
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        now = datetime.datetime.now()
        dia_semana = dias[now.weekday()]
        dia_num = now.day
        mes = meses[now.month - 1]
        msg = f"Hoy es {dia_semana} {dia_num} de {mes}, che."
        state_mgr.emit_tool_call("get_local_date", {}, msg)
        return msg


def handle_weather(engine, text, clean, norm) -> "Optional[str]":
    """2. CLIMA Y PRONÓSTICO (excluyendo consultas de temperatura de hardware, mate, cocina)."""
    is_weather = (
        any(_mip(norm, p) for p in ["clima", "pronostico", "tiempo hoy", "va a llover", "estado del tiempo"]) or
        (("temperatura" in norm or "cuantos grados" in norm) and not any(_mip(norm, h) for h in ["pc", "compu", "computadora", "cpu", "gpu", "procesador", "placa", "hardware", "ddr3", "servidor", "mate", "agua", "pava", "horno", "comida"]))
    )
    if is_weather:
        ciudad = "Buenos Aires"
        for c in ["cordoba", "rosario", "mendoza", "la plata", "salta", "mar del plata", "tucuman"]:
            if c in norm:
                ciudad = c.capitalize()
                break
        res = system_control.get_weather(ciudad)
        msg = res.get("message", "No pude conseguir el pronóstico ahora.")
        return msg
