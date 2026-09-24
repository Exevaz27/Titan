"""Cadena VPN Saltamontes -> XuperTV (2026-09-22).

XuperTV solo anda detrás de la VPN "Saltamontes": se abre la VPN, a los
10-15s XuperTV abre sola y a los 30-35s la VPN se desactiva sola. Titán NO
necesita conocer el paquete de XuperTV (su nombre interno no contiene
"xuper"): abre Saltamontes y espera a que DEJE de estar en primer plano,
señal de que XuperTV tomó la pantalla sola. Dos errores posibles
(reportados por Exequiel):
  1. La VPN no conecta -> OK reintenta la conexión.
  2. XuperTV abre pero tarda en cargar y la VPN cae antes -> cartel de
     "limitación de la política" -> ATRÁS y se arranca de nuevo.
Si todo falla, se sugiere fallback a Cloudstream (lo decide Exequiel).
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools.tv_control as tvc
from tools.tv_control import TVControl

VPN_PKG = "com.saltamontes.vpn"
XUPER_PKG = "com.xupertv.app"


def _focused(pkg):
    return f"  mCurrentFocus=Window{{abc {pkg}/.MainActivity}}"


CARTEL_XML = (
    "<hierarchy>"
    '<node text="Debido a la limitación de la política, la cuenta no se puede '
    'usar en tu área. Póngase en contacto con el distribuidor."/>'
    '<node text="Usar otra cuenta"/><node text="Salida"/>'
    "</hierarchy>"
)
CLEAN_XML = '<hierarchy><node text="Inicio"/><node text="Buscar"/></hierarchy>'


class FakeADB:
    """Guiona _run_shell por escenario. Cuenta llamadas para simular el
    paso del tiempo (aparición de XuperTV, etc.)."""

    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []
        self.n_window = 0

    def __call__(self, cmd, timeout=6.0):
        self.calls.append(cmd)
        if cmd.startswith("pm list packages"):
            # Escenario "sin_xuper": ningún paquete contiene "xuper"
            # (el caso real de la tele de Exequiel, 2026-09-22).
            if self.scenario == "sin_xuper":
                return True, f"package:{VPN_PKG}\npackage:com.otro.app"
            return True, f"package:{VPN_PKG}\npackage:{XUPER_PKG}\npackage:com.otro.app"
        if cmd.startswith("dumpsys power"):
            return True, "mWakefulness=Awake"
        if cmd.startswith("monkey -p"):
            return True, "Events injected: 1"
        if cmd.startswith("dumpsys window"):
            self.n_window += 1
            return True, self._window()
        if cmd.startswith("uiautomator dump"):
            return True, CARTEL_XML if self.scenario == "cartel" else CLEAN_XML
        if cmd.startswith("input keyevent"):
            if "keyevent 4" in cmd:
                # ATRÁS ante el cartel: volvemos a la pantalla de
                # Saltamontes; se reinicia la simulación del tiempo.
                self.n_window = 0
            return True, ""
        return True, ""

    def _window(self):
        # happy/cartel/sin_xuper: otra app toma la pantalla al 3er poll
        # (XUPER_PKG acá es solo "la app que abrió Saltamontes sola"; el
        # código real ya no necesita conocer su nombre interno).
        # error1: no aparece en los primeros 12 polls (simula 20s+), aparece
        #        tras el OK (la VPN reconecta).
        # fail: nunca aparece.
        if self.scenario in ("happy", "cartel", "sin_xuper"):
            return _focused(XUPER_PKG) if self.n_window >= 3 else _focused(VPN_PKG)
        if self.scenario == "error1":
            ok_sent = any("input keyevent 66" in c for c in self.calls)
            return _focused(XUPER_PKG) if ok_sent and self.n_window >= 14 else _focused(VPN_PKG)
        return _focused(VPN_PKG)


@pytest.fixture
def ctl(monkeypatch):
    c = TVControl()
    # Tiempos chicos: los sleeps se anulan y los timeouts se acortan.
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(tvc, "_VPN_FIRST_WAIT", 0.05)
    monkeypatch.setattr(tvc, "_VPN_SECOND_WAIT", 0.05)
    monkeypatch.setattr(tvc, "_VPN_LOAD_WAIT", 0.0)
    monkeypatch.setattr(tvc, "_VPN_POLL_STEP", 0.0)
    monkeypatch.setattr(tvc, "_VPN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(tvc, "_VPN_LAUNCH_WAIT", 0.05)
    return c


def _patch_run(ctl, monkeypatch, scenario):
    fake = FakeADB(scenario)
    monkeypatch.setattr(ctl, "_run_shell", fake)
    monkeypatch.setattr(ctl, "_ensure_connected", lambda: True)
    return fake


def test_happy_path(ctl, monkeypatch):
    fake = _patch_run(ctl, monkeypatch, "happy")
    res = ctl.open_app("xupertv")
    assert res["status"] == "success"
    assert "suggest_fallback" not in res
    # Se lanzó la VPN (no XuperTV directo).
    assert any(f"monkey -p {VPN_PKG}" in c for c in fake.calls)
    assert not any(f"monkey -p {XUPER_PKG}" in c for c in fake.calls)


def test_error1_ok_reintenta_vpn(ctl, monkeypatch):
    fake = _patch_run(ctl, monkeypatch, "error1")
    res = ctl.open_app("xupertv")
    assert res["status"] == "success"
    # Se tocó OK para reintentar la conexión VPN.
    assert any("input keyevent 66" in c for c in fake.calls)


def test_error2_cartel_reintenta_cadena(ctl, monkeypatch):
    # Primera pasada: cartel -> ATRÁS -> segunda pasada limpia.
    calls = {"n_uiauto": 0}

    fake = _patch_run(ctl, monkeypatch, "cartel")
    orig = fake.__call__

    def hooked(cmd, timeout=6.0):
        if cmd.startswith("uiautomator dump"):
            calls["n_uiauto"] += 1
            # Segundo intento: ya cargó bien.
            if calls["n_uiauto"] >= 2:
                return True, CLEAN_XML
        return orig(cmd, timeout)

    monkeypatch.setattr(ctl, "_run_shell", hooked)
    res = ctl.open_app("XuperTV")
    assert res["status"] == "success"
    # Se tocó ATRÁS ante el cartel y se relanzó la VPN (2 intentos).
    assert any("input keyevent 4" in c for c in fake.calls)
    assert sum(f"monkey -p {VPN_PKG}" in c for c in fake.calls) == 2


def test_fallo_total_sugiere_fallback(ctl, monkeypatch):
    fake = _patch_run(ctl, monkeypatch, "fail")
    res = ctl.open_app("xupertv")
    assert res["status"] == "error"
    assert res["suggest_fallback"] is True


def test_open_app_rutea_segun_config(ctl, monkeypatch):
    # xupertv -> cadena VPN; cloudstream -> apertura directa.
    vpn_calls = []
    monkeypatch.setattr(ctl, "_open_via_vpn",
                        lambda name: vpn_calls.append(name) or {"status": "success", "message": "ok"})
    launched = []
    monkeypatch.setattr(ctl, "_launch_package", lambda pkg: launched.append(pkg) or True)
    monkeypatch.setattr(ctl, "_discover_package", lambda q: "com.lagradost.cloudstream3.prereleasf")
    monkeypatch.setattr(ctl, "is_awake", lambda: True)

    ctl.open_app("xupertv")
    assert vpn_calls == ["xupertv"]
    assert launched == []

    ctl.open_app("cloudstream")
    assert launched == ["com.lagradost.cloudstream3.prereleasf"]


def test_config_defaults_sin_archivo(ctl, monkeypatch, tmp_path):
    # Sin tv_apps.json: defaults (saltamontes + xupertv por VPN).
    monkeypatch.setattr("os.path.exists", lambda p: False)
    c2 = TVControl()
    assert c2._tv_apps["vpn_app"] == "saltamontes"
    assert "xupertv" in c2._tv_apps["apps_con_vpn"]


def test_cartel_no_detecta_falso_positivo(ctl, monkeypatch):
    _patch_run(ctl, monkeypatch, "happy")
    assert ctl._has_geo_cartel() is False


def test_cartel_detecta_texto(ctl, monkeypatch):
    _patch_run(ctl, monkeypatch, "cartel")
    assert ctl._has_geo_cartel() is True


def test_confirmacion_fallback_en_matriz():
    from core.confirmation import requires_confirmation, describe_action, ttl_for
    assert requires_confirmation("tv_fallback_cloudstream")
    assert "Cloudstream" in describe_action("tv_fallback_cloudstream", {})
    assert ttl_for("tv_fallback_cloudstream") == 120


def test_execute_fallback_abre_cloudstream(monkeypatch):
    from core.confirmation import execute_action
    opened = []
    import tools.tv_control as tvc_mod
    monkeypatch.setattr(tvc_mod.tv_control, "open_app",
                        lambda name: opened.append(name) or {"status": "success", "message": "ok"})
    execute_action("tv_fallback_cloudstream", {})
    assert opened == ["cloudstream"]


def test_intent_matchea_variantes_de_transcripcion(monkeypatch):
    """El reconocedor transcribe 'XuperTV' como 'súper TV'/'super TV'.
    El intent local debe matchearlas igual (2026-09-22: log de Exequiel)."""
    from brain.local_intents.hud_camera import handle_camera
    import tools.tv_control as tvc_mod
    opened = []
    monkeypatch.setattr(tvc_mod.tv_control, "open_app",
                        lambda name: opened.append(name) or {"status": "success", "message": "ok"})
    casos = [
        ("abrir xuper tv", "abrir xuper tv"),
        ("abrir súper tv", "abrir super tv"),   # como lo escuchó el mic
        ("abri supertv", "abri supertv"),
        ("abrir xupertv", "abrir xupertv"),
    ]
    for text, norm in casos:
        opened.clear()
        res = handle_camera(None, text, text.lower(), norm)
        assert opened == ["xupertv"], f"no matcheó: {text!r}"
        assert res == "ok"


def test_intent_no_falso_positivo_con_super_suelto(monkeypatch):
    """'super' suelto ('está súper', 'se ve súper la tv') NO abre XuperTV."""
    from brain.local_intents.hud_camera import handle_camera
    import tools.tv_control as tvc_mod
    opened = []
    monkeypatch.setattr(tvc_mod.tv_control, "open_app",
                        lambda name: opened.append(name) or {"status": "success", "message": "ok"})
    for text, norm in [("esta super la peli", "esta super la peli"),
                       ("se ve super la tv", "se ve super la tv")]:
        opened.clear()
        handle_camera(None, text, text.lower(), norm)
        assert opened == [], f"falso positivo: {text!r}"


def test_sin_paquete_xuper_igual_anda(ctl, monkeypatch):
    """Regresión del bug reportado por Exequiel (2026-09-22): ningún
    paquete instalado contiene 'xuper' y no hace falta — la cadena igual
    anda porque Saltamontes abre XuperTV sola; Titán solo espera a que
    la VPN deje el primer plano."""
    fake = _patch_run(ctl, monkeypatch, "sin_xuper")
    res = ctl.open_app("xupertv")
    assert res["status"] == "success"
    assert "suggest_fallback" not in res
    # Se lanzó la VPN; XuperTV nunca se buscó ni se lanzó directo.
    assert any(f"monkey -p {VPN_PKG}" in c for c in fake.calls)
    assert not any("xuper" in c for c in fake.calls if c.startswith("monkey -p"))
