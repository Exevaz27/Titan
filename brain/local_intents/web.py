"""Búsquedas web y accesos directos.."""

from ._common import _mip
from tools.system_control import system_control

from typing import Optional

def handle_google(engine, text, clean, norm) -> "Optional[str]":
    """12. BÚSQUEDA DIRECTA EN GOOGLE."""
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
            return res.get("message", f"Buscando '{g_query}' en Google.")


def handle_web_shortcuts(engine, text, clean, norm) -> "Optional[str]":
    """13. ACCESOS DIRECTOS WEB."""
    if any(_mip(norm, p) for p in ["abri whatsapp", "abrir whatsapp", "whatsapp web", "pone whatsapp", "abrir wpp"]):
        res = system_control.open_web_service("whatsapp")
        return res.get("message", "Ahí te abrí WhatsApp Web, che.")

    if any(_mip(norm, p) for p in ["abri mercado libre", "abrir mercado libre", "mercadolibre", "mercado libre"]):
        res = system_control.open_web_service("mercadolibre")
        return res.get("message", "Ahí te abrí Mercado Libre, papá.")

    if any(_mip(norm, p) for p in ["abri gmail", "abrir gmail", "abrir correo", "abri el correo", "el correo"]):
        res = system_control.open_web_service("gmail")
        return res.get("message", "Ahí te abrí Gmail, che.")
