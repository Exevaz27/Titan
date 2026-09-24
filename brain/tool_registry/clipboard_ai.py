"""Herramientas de IA sobre el portapapeles."""

from core.config import config

from tools.system_control import system_control



# --- PORTAPAPELES Y VISIÓN CON IA ---
def summarize_clipboard(max_sentences: int = 3) -> str:
    """Lee el texto copiado en el portapapeles de Windows, extrae las ideas principales con Gemini y devuelve un resumen claro por voz y texto."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para resumir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para resumir el texto copiado."

    try:
        prompt = (
            f"Actuá como Titán, asistente compinche argentino. Resumí el siguiente texto copiado del portapapeles "
            f"extrayendo los puntos clave en un máximo de {max_sentences} oraciones directas, claras y fáciles de escuchar:\n\n{text}"
        )
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    summary = resp.text.strip()
                    return f"Te resumo lo que tenés copiado:\n{summary}"
            except Exception:
                continue
        return "No pude generar el resumen del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al resumir el portapapeles: {e}"


def explain_clipboard() -> str:
    """Lee el código, mensaje de error, comando o texto técnico copiado en el portapapeles de Windows y lo explica de forma didáctica en español argentino."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para explicar, che."
    if not brain.client:
        return "No tengo conexión con Gemini para explicar lo que copiaste."

    try:
        prompt = (
            f"Actuá como Titán, asistente compinche argentino y programador experto. "
            f"Explicá qué hace, qué significa o cómo solucionar el siguiente contenido copiado en el portapapeles "
            f"(puede ser código fuente, una traza de error de terminal, un comando o un fragmento técnico). "
            f"Sé didáctico, conciso y directo, sin vueltas innecesarias:\n\n{text}"
        )
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    explanation = resp.text.strip()
                    return f"Mirá, esto es lo que tenés copiado:\n{explanation}"
            except Exception:
                continue
        return "No pude analizar ni explicar el contenido del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al explicar el portapapeles: {e}"


def translate_clipboard(target_language: str = "español") -> str:
    """Lee el texto actual copiado en el portapapeles de Windows, lo traduce al idioma especificado con Gemini y copia el resultado al portapapeles."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para traducir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para traducir el texto."

    try:
        prompt = f"Traducí el siguiente texto al idioma {target_language}. Devolvé ÚNICAMENTE el texto traducido sin notas ni explicaciones:\n\n{text}"
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    translated = resp.text.strip()
                    system_control.set_clipboard(translated)
                    return f"¡Listo! Traduje el texto al {target_language} y te lo dejé copiado en el portapapeles listo para pegar:\n'{translated[:140]}...'"
            except Exception:
                continue
        return "No pude traducir el texto del portapapeles en este momento."
    except Exception as e:
        return f"Hubo un error al traducir el portapapeles: {e}"


def rewrite_clipboard(style: str = "profesional") -> str:
    """Reescribe y corrige la ortografía y redacción del texto copiado en el portapapeles con el estilo solicitado (profesional, casual, formal, etc.) y lo vuelve a copiar al portapapeles."""
    from brain.gemini_client import brain
    cb = system_control.get_clipboard()
    text = (cb.get("text") or cb.get("content") or "").strip() if cb.get("status") == "success" else ""
    if not text:
        return "El portapapeles está vacío, no hay nada copiado para mejorar o reescribir, che."
    if not brain.client:
        return "No tengo conexión con Gemini para reescribir el texto."

    try:
        prompt = f"Reescribí y mejorá la redacción del siguiente texto con un estilo {style} (corrigiendo faltas de ortografía, puntuación y mejorando el tono). Devolvé ÚNICAMENTE el texto reescrito sin saludos ni explicaciones:\n\n{text}"
        models_to_try = [config.gemini_model or "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        for cand in models_to_try:
            try:
                resp = brain.client.models.generate_content(model=cand, contents=prompt)
                if resp and resp.text:
                    rewritten = resp.text.strip()
                    system_control.set_clipboard(rewritten)
                    return f"¡De diez! Reescribí el texto con estilo {style} y ya lo tenés copiado en el portapapeles:\n'{rewritten[:140]}...'"
            except Exception:
                continue
        return "No pude reescribir el texto del portapapeles."
    except Exception as e:
        return f"Hubo un error al reescribir el portapapeles: {e}"
