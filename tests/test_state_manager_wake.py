"""Despertar de la etapa de inactividad (fix pava del mate, 2026-09-23).

Bug reportado por Exequiel: en la pantalla del J2 la animación del mate
quedaba bugueada, la pava quedaba fija todo el tiempo.

Causa: add_user_message() y set_state() tenían una guarda
("inactivity_stage not in ['mate','drowsy','sleeping']") que impedía despertar
la etapa una vez activa. El habla del usuario por Telegram (que no pasa por el
workaround de main.py) nunca la limpiaba, y el J2 solo saca la pava cuando
recibe el evento set_stage/wake.

Fix: se quitó la guarda en ambos métodos. El chequeo is_rest_cmd ya alcanza:
una orden de descanso no despierta, todo lo demás sí.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.state_manager import StateManager, AssistantState


def _mgr_with_events():
    mgr = StateManager()
    events = []
    mgr.subscribe(events.append)
    return mgr, events


def _stages(events):
    return [e.get("stage") for e in events if e.get("type") == "set_stage"]


def test_user_speech_wakes_from_mate_with_wake_event():
    mgr, events = _mgr_with_events()
    mgr.emit_stage("mate")
    assert mgr.inactivity_stage == "mate"
    events.clear()
    mgr.add_user_message("qué hora es")
    assert mgr.inactivity_stage == "idle"
    assert "wake" in _stages(events)


def test_telegram_speech_wakes_from_mate():
    # El mensaje de Telegram llega con prefijo "[Telegram] " y no pasa por el
    # workaround de main.py: este era el camino que dejaba la pava clavada.
    mgr, events = _mgr_with_events()
    mgr.emit_stage("mate")
    events.clear()
    mgr.add_user_message("[Telegram] qué hora es")
    assert mgr.inactivity_stage == "idle"
    assert "wake" in _stages(events)


def test_rest_command_does_not_wake_from_mate():
    mgr, events = _mgr_with_events()
    mgr.emit_stage("mate")
    events.clear()
    mgr.add_user_message("tomá mate")
    assert mgr.inactivity_stage == "mate"
    assert "wake" not in _stages(events)


def test_set_state_active_wakes_from_mate():
    mgr, events = _mgr_with_events()
    mgr.emit_stage("mate")
    events.clear()
    mgr.set_state(AssistantState.LISTENING)
    assert mgr.inactivity_stage == "idle"
    assert "wake" in _stages(events)


def test_set_state_idle_does_not_clear_mate():
    # La etapa diferida se aplica DESPUÉS de que Titán termina de hablar;
    # set_state(IDLE) no debe limpiarla.
    mgr, events = _mgr_with_events()
    mgr.emit_stage("mate")
    events.clear()
    mgr.set_state(AssistantState.IDLE)
    assert mgr.inactivity_stage == "mate"
    assert "wake" not in _stages(events)


def test_deferred_mate_flow_still_works():
    # Flujo "tomá mate": la orden no despierta, la etapa se aplica diferida
    # después del TTS y queda activa.
    mgr, events = _mgr_with_events()
    mgr.add_user_message("tomá mate")  # orden de descanso: no despierta
    mgr.defer_stage("mate")
    pending = mgr.pop_pending_stage()
    assert pending == "mate"
    events.clear()
    mgr.set_inactivity_stage(pending)
    assert mgr.inactivity_stage == "mate"
    assert "mate" in _stages(events)
