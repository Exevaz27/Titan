"""Preguntas sobre Titán (conversacional local)."""

from ._common import _mip, _varied_choice

from typing import Optional

def handle_about_titan(engine, text, clean, norm) -> "Optional[str]":
    """15. PREGUNTAS SOBRE TITÁN (CONVERSACIONAL LOCAL - SIN CHISTES)."""
    if any(_mip(norm, p) for p in ["quien sos", "como te llamas", "cual es tu nombre", "quien te creo"]):
        return _varied_choice("about-quien-sos", [
            "¡Soy Titán, tu asistente personal! Vivo en la DDR3 con Linux y te manejo la Windows por satélite. Con la garra de Martín Palermo, acá estoy firme para lo que necesites, papá.",
            "Titán, compinche de fierro. Estoy instalado en la DDR3 y desde ahí te controlo la compu. Sangre azul y oro, como Palermo.",
            "Soy Titán, tu compa de todos los días. Vivo en la DDR3 con Linux; la Windows la manejo por control remoto. ¿Qué hacemos?",
        ])

    # NOTA 2026-09-18 (Exequiel): "¿cómo estás?" NO tiene respuesta fija.
    # Antes había una frase hecha acá y siempre repetía lo mismo. Ahora cae
    # a Gemini, que lo responde fresco cada vez (se acepta la latencia a
    # cambio de variedad real). Regla: el habla conversacional no lleva
    # frases hechas en código.

    if any(_mip(norm, p) for p in ["que sabes hacer", "que podes hacer", "cuales son tus funciones", "que cosas haces"]):
        return _varied_choice("about-que-haces", [
            "De todo, fiera: te abro apps, te pongo temas en YouTube o Spotify, te manejo el volumen y las ventanas, te busco archivos, te saco capturas y hasta te miro cosas con la cámara del celular. Decime y lo hacemos al toque.",
            "Soy tus manos en la compu: apps, música, tele, archivos, capturas, volumen... y si me hablás por Telegram también te respondo. Pedime nomás.",
            "Manejo la Windows por satélite y la DDR3 directo: programas, YouTube, Spotify, tele, archivos y más. ¿Qué necesitás?",
        ])

    if any(_mip(norm, p) for p in ["de que cuadro sos", "de que equipo sos", "hincha de que sos", "de quien sos hincha"]):
        return _varied_choice("about-cuadro", [
            "¡De Boca Juniors, papá! Como el gran Martín Palermo, con el corazón bien azul y oro.",
            "¡De Boca, obvio! Sangre azul y oro hasta en los circuitos.",
            "Bostero hasta la médula, como Palermo. ¿De qué otro cuadro iba a ser?",
        ])
