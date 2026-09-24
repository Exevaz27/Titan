"""Potenciador del portapapeles con IA.."""

from ._common import _mip

from typing import Optional

def handle_clipboard_ai(engine, text, clean, norm) -> "Optional[str]":
    """21. POTENCIADOR DEL PORTAPAPELES CON IA."""
    is_clip_target = any(_mip(norm, c) for c in [
        "portapapeles", "lo que copie", "lo copiado", "lo que tengo copiado",
        "el texto copiado", "lo que esta copiado", "esto que copie", "este texto copiado"
    ])

    # 21.1 RESUMEN CON IA
    if any(_mip(norm, v) for v in ["resumi", "resumir", "resumime", "resumen"]) and (is_clip_target or "resumen de esto" in norm):
        from brain.tool_registry import summarize_clipboard
        return summarize_clipboard()

    # 21.2 EXPLICACIÓN DE CÓDIGO O ERRORES CON IA
    if any(_mip(norm, v) for v in ["explica", "explicar", "explicame", "que hace", "que significa"]) and (
        is_clip_target or any(_mip(norm, k) for k in ["este codigo", "el codigo", "este error", "el error", "esta traza", "este comando"])
    ):
        from brain.tool_registry import explain_clipboard
        return explain_clipboard()

    # 21.3 TRADUCCIÓN CON IA
    if any(_mip(norm, v) for v in ["traduci", "traducir", "traducime", "traduccion"]) and (is_clip_target or "traduci esto" in norm):
        from brain.tool_registry import translate_clipboard
        target = "inglés"
        if any(_mip(norm, x) for x in ["al portugues", "en portugues", "a portugues"]):
            target = "portugués"
        elif any(_mip(norm, x) for x in ["al frances", "en frances", "a frances"]):
            target = "francés"
        elif any(_mip(norm, x) for x in ["al italiano", "en italiano", "a italiano"]):
            target = "italiano"
        elif any(_mip(norm, x) for x in ["al aleman", "en aleman", "a aleman"]):
            target = "alemán"
        elif any(_mip(norm, x) for x in ["al espanol", "en espanol", "a espanol", "al castellano"]):
            target = "español"
        elif any(_mip(norm, x) for x in ["al ingles", "en ingles", "a ingles"]):
            target = "inglés"
        return translate_clipboard(target)

    # 21.4 MEJORA, CORRECCIÓN Y REESCRITURA CON IA
    if any(_mip(norm, v) for v in ["corregi", "corregir", "corregime", "mejora", "mejorar", "mejorame", "reescribi", "reescribir", "arregla", "arreglar"]) and (
        is_clip_target or any(_mip(norm, k) for k in ["la redaccion", "la ortografia", "la gramatica"])
    ):
        from brain.tool_registry import rewrite_clipboard
        style = "formal" if "formal" in norm else ("casual" if "casual" in norm else "profesional")
        return rewrite_clipboard(style)

    if any(_mip(norm, p) for p in ["extrae el texto de la pantalla", "copia el texto de la pantalla", "ocr de la pantalla", "lee el texto de la pantalla", "sacale el texto a la pantalla"]):
        from brain.tool_registry import extract_text_from_screen
        return extract_text_from_screen()
