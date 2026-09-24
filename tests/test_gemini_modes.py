"""Regresión: reset_chat() debe funcionar en TODOS los modos.

Bug real (2026-09-15): la rama "rebel" de reset_chat() no definía
`temperature`, lo que provocaba UnboundLocalError al activar el modo
rebelde. El except lo tragaba, dejaba aio_chat_talk en None y Titán
respondía el engañoso "todavía no pusiste tu clave de Gemini" solo en
modo rebelde (en modo normal andaba bien).
"""
import sys
import types as pytypes
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain.gemini_client import GeminiBrain


def _brain_with_fake_client():
    brain = GeminiBrain.__new__(GeminiBrain)  # sin __init__: sin red ni clave
    brain.client = MagicMock()
    fake_chat = object()
    brain.client.aio.chats.create.return_value = fake_chat
    brain.chat_session = None
    brain.current_mode = "normal"
    brain.is_rebel_mode = False
    brain.rebel_turn_count = 0
    brain.aio_chat_talk = None
    brain.aio_chat_tools = None
    brain.aio_chat_session = None
    return brain, fake_chat


def test_reset_chat_rebel_mode_creates_session():
    brain, fake_chat = _brain_with_fake_client()
    brain.current_mode = "rebel"
    brain.reset_chat()
    assert brain.aio_chat_talk is fake_chat, (
        "En modo rebelde la sesión de chat quedó en None (¿UnboundLocalError tragado?)"
    )


def test_reset_chat_all_modes_create_session():
    for mode in ("normal", "rebel", "kids", "termo", "pollera"):
        brain, fake_chat = _brain_with_fake_client()
        brain.current_mode = mode
        brain.reset_chat()
        assert brain.aio_chat_talk is fake_chat, f"Modo '{mode}': sesión en None"
        # La config de generación debe incluir temperature en todos los modos
        _, kwargs = brain.client.aio.chats.create.call_args
        gen_config = kwargs["config"]
        assert gen_config.temperature is not None, f"Modo '{mode}': temperature None"


# ============================================================
# Marca de expresión facial [cara:X] (modo pollera, 2026-09-18)
# ============================================================
from brain.gemini_client import split_face_tag


def test_face_tag_retado_al_inicio():
    expr, clean = split_face_tag("[cara:retado] P-perdón, Orianita...")
    assert expr == "retado"
    assert clean == "P-perdón, Orianita..."
    assert "[cara" not in clean


def test_face_tag_enojado_case_insensitive():
    expr, clean = split_face_tag("[CARA:ENOJADO] Con la jefa no, eh.")
    assert expr == "enojado"
    assert clean == "Con la jefa no, eh."


def test_face_tag_ausente():
    expr, clean = split_face_tag("Hola, ¿cómo andás?")
    assert expr is None
    assert clean == "Hola, ¿cómo andás?"


def test_face_tag_marca_fuera_de_lugar_no_dispara_pero_se_limpia():
    # Si el modelo la pone donde no debe, no dispara expresión pero
    # tampoco se escucha/lee en ningún canal.
    expr, clean = split_face_tag("Che [cara:retado], perdón.")
    assert expr is None
    assert "[cara" not in clean
    assert clean == "Che , perdón."


def test_face_tag_solo_valores_conocidos():
    expr, clean = split_face_tag("[cara:contento] Qué alegría.")
    assert expr is None
    assert "[cara" not in clean


def test_face_tag_normal_limpia_expresion_fija():
    # [cara:normal] (2026-09-18): el cerebro la manda cuando el tema se corta;
    # dispara limpieza en el HUD, no una expresión.
    expr, clean = split_face_tag("[cara:normal] Bueno, cambiemos de tema.")
    assert expr == "normal"
    assert clean == "Bueno, cambiemos de tema."
    assert "[cara" not in clean
