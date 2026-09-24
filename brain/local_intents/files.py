"""Organizador de archivos y lectura en voz alta.."""

from ._common import _mip
import re

from typing import Optional

def handle_organizer(engine, text, clean, norm) -> "Optional[str]":
    """20. ORGANIZADOR AUTOMÁTICO DE ARCHIVOS."""
    if any(_mip(norm, p) for p in ["ordena descargas", "ordenar descargas", "ordename descargas", "limpia descargas", "organizar descargas", "ordena la carpeta descargas"]):
        from brain.tool_registry import organize_folder
        return organize_folder("Downloads")

    if any(_mip(norm, p) for p in ["ordena el escritorio", "ordenar el escritorio", "ordename el escritorio", "limpia el escritorio", "organizar escritorio"]):
        from brain.tool_registry import organize_folder
        return organize_folder("Desktop")


def handle_read_aloud(engine, text, clean, norm) -> "Optional[str]":
    """22. LEER ARCHIVO EN VOZ ALTA (determinístico, sin Gemini)."""
    # "leé X" / "léelo" / "qué dice el archivo X" van directo a read_file_content.
    # Se resuelve local porque Gemini confundía open_file con read_file_content
    # y abría el archivo en pantalla en vez de leerlo.
    words = set(norm.split())
    read_verbs = {"lee", "leelo", "leela", "leeme", "leemelo", "leemela", "lectura"}
    wants_read = (
        bool(words & read_verbs)
        or ("que dice" in norm and "archivo" in norm)
        or ("contenido" in norm and "archivo" in norm)
        or re.match(r"^(el |la )?(archivo|nota|documento|texto) .+", norm) is not None
    )
    open_pronoun = bool(words & {"abrilo", "abrila", "mostramelo", "mostramela"})
    if wants_read or open_pronoun:
        from brain.tool_registry import get_last_file_path, read_file_content
        target = ""
        if wants_read:
            t = norm
            t = re.sub(r"^(lee|leeme|leelo|leela|leemelo|leemela|lectura)\b\s*", "", t)
            t = re.sub(r"^que dice\s+(el\s+|la\s+)?", "", t)
            t = re.sub(r"^contenido\s+del\s+(archivo\s+)?", "", t)
            t = re.sub(r"^(el|la|los|las)\s+", "", t)
            t = re.sub(r"^(archivo|nota|documento|texto)\s+", "", t)
            t = re.sub(r"\s+(de la carpeta|de mi carpeta|de documentos)$", "", t)
            t = re.sub(r"\s+en\s+(mis|mi|la|el)\s+.+$", "", t)
            t = t.strip()
            if t and t not in read_verbs:
                target = t
        if not target:
            # "léelo" sin nombre: último archivo mencionado/encontrado
            target = get_last_file_path()
            if not target:
                return None  # que lo resuelva Gemini con el historial
        if open_pronoun:
            from brain.tool_registry import open_file as reg_open_file
            return reg_open_file(target)
        import os as _os
        if not _os.path.exists(target):
            from tools.file_manager import file_manager
            res = file_manager.search_files(query=target, max_results=5)
            # Si la búsqueda falló (satélite desconectado, timeout), propagar
            # el mensaje real en vez de decir "no encontrado".
            if not isinstance(res, dict) or res.get("status") != "success":
                msg = res.get("message") if isinstance(res, dict) else None
                return msg or f"No pude buscar el archivo '{target}' en este momento."
            files = res.get("files", [])
            if not files:
                return f"No encontré ningún archivo con el nombre '{target}'."
            target = files[0].get("path", "")
        return read_file_content(target)
