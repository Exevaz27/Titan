"""Tests P0-4 — Seguridad RPC del satélite y set_wallpaper.

Cubre:
  1. Auth mutua: challenge-response del handshake (server_proof).
     Solo quien conoce el token genera un proof válido.
  2. Firma HMAC por comando: el satélite rechaza remote_exec manipulados
     (acción/args/request_id alterados, firma ausente, token incorrecto).
  3. Allowlist RPC: set_wallpaper incluida; acciones desconocidas fuera.
  4. Validación de URL en /api/pc/wallpaper/set (solo http/https o ruta
     local; rechaza file://, ftp://, javascript:, etc.).
  5. Descarga endurecida de set_wallpaper: timeout implícito, tamaño máximo,
     Content-Type image/*, magic bytes de imagen real.
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import rpc_auth


class FakeHeaders(dict):
    def get(self, key, default=""):
        return super().get(key, default)


class FakeResp:
    """Respuesta falsa de urlopen: context manager + read por chunks."""

    def __init__(self, data: bytes, content_type: str = "image/png", chunk: int = 65536):
        self._data = data
        self._chunk = chunk
        self.headers = FakeHeaders({"Content-Type": content_type} if content_type else {})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        if not self._data:
            return b""
        out, self._data = self._data[: self._chunk], self._data[self._chunk :]
        return out


def make_png_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
    return buf.getvalue()


class TestRpcAuthHandshake(unittest.TestCase):
    def test_nonce_es_hex_unico(self):
        n1, n2 = rpc_auth.generate_nonce(), rpc_auth.generate_nonce()
        self.assertEqual(len(n1), 64)
        self.assertNotEqual(n1, n2)
        int(n1, 16)  # no lanza si es hex válido

    def test_proof_roundtrip(self):
        token, nonce = "token-secreto", rpc_auth.generate_nonce()
        proof = rpc_auth.server_proof(token, nonce)
        self.assertTrue(rpc_auth.verify_server_proof(token, nonce, proof))

    def test_proof_token_incorrecto_falla(self):
        token, nonce = "token-secreto", rpc_auth.generate_nonce()
        proof = rpc_auth.server_proof(token, nonce)
        self.assertFalse(rpc_auth.verify_server_proof("otro-token", nonce, proof))

    def test_proof_nonce_manipulado_falla(self):
        token, nonce = "token-secreto", rpc_auth.generate_nonce()
        proof = rpc_auth.server_proof(token, nonce)
        self.assertFalse(rpc_auth.verify_server_proof(token, nonce + "x", proof))

    def test_proof_vacio_falla_cerrado(self):
        self.assertFalse(rpc_auth.verify_server_proof("t", "n", ""))
        self.assertFalse(rpc_auth.verify_server_proof("", "n", "abc"))
        self.assertFalse(rpc_auth.verify_server_proof("t", "", "abc"))


class TestRpcAuthComandos(unittest.TestCase):
    def _payload_firmado(self, token="tok", action="mute", args=None, request_id="r1"):
        args = {} if args is None else args
        payload = {"type": "remote_exec", "action": action, "args": args, "request_id": request_id}
        payload["hmac"] = rpc_auth.sign_remote_command(token, request_id, action, args)
        return payload

    def test_comando_valido_pasa(self):
        p = self._payload_firmado()
        self.assertTrue(rpc_auth.verify_remote_command("tok", p))

    def test_accion_manipulada_falla(self):
        p = self._payload_firmado(action="mute")
        p["action"] = "shutdown_pc"  # atacante cambia la acción post-firma
        self.assertFalse(rpc_auth.verify_remote_command("tok", p))

    def test_args_manipulados_fallan(self):
        p = self._payload_firmado(action="set_volume", args={"level": 10})
        p["args"] = {"level": 100}
        self.assertFalse(rpc_auth.verify_remote_command("tok", p))

    def test_request_id_manipulado_falla(self):
        p = self._payload_firmado(request_id="r1")
        p["request_id"] = "r2"
        self.assertFalse(rpc_auth.verify_remote_command("tok", p))

    def test_sin_hmac_falla(self):
        p = self._payload_firmado()
        del p["hmac"]
        self.assertFalse(rpc_auth.verify_remote_command("tok", p))

    def test_token_incorrecto_falla(self):
        p = self._payload_firmado(token="tok")
        self.assertFalse(rpc_auth.verify_remote_command("otro", p))

    def test_orden_de_claves_no_afecta(self):
        # La serialización canónica hace que el orden de las claves no importe.
        p1 = self._payload_firmado(args={"b": 1, "a": 2})
        p2 = dict(p1)
        p2["args"] = {"a": 2, "b": 1}
        p2["hmac"] = rpc_auth.sign_remote_command("tok", "r1", "mute", {"a": 2, "b": 1})
        self.assertEqual(p1["hmac"], p2["hmac"])


class TestAllowlistRpc(unittest.TestCase):
    def test_set_wallpaper_en_allowlist(self):
        import desktop.remote_satellite as sat

        self.assertIn("set_wallpaper", sat.RPC_ALLOWED_ACTIONS)

    def test_acciones_peligrosas_conocidas_siguen_listadas(self):
        import desktop.remote_satellite as sat

        for action in ("shutdown_pc", "kill_process", "take_screenshot", "get_clipboard"):
            self.assertIn(action, sat.RPC_ALLOWED_ACTIONS)

    def test_acciones_desconocidas_fuera(self):
        import desktop.remote_satellite as sat

        for action in ("rm_rf", "__import__", "eval", "exec", "format_c"):
            self.assertNotIn(action, sat.RPC_ALLOWED_ACTIONS)

    def test_allowlist_no_vacia_y_sin_duplicados_implicitos(self):
        import desktop.remote_satellite as sat

        self.assertGreater(len(sat.RPC_ALLOWED_ACTIONS), 30)


class TestValidateWallpaperUrl(unittest.TestCase):
    def test_urls_validas(self):
        from server.web_server import validate_wallpaper_url

        self.assertEqual(validate_wallpaper_url("/imagenes/gen.png"), "/imagenes/gen.png")
        self.assertEqual(
            validate_wallpaper_url("https://example.com/fondo.jpg"),
            "https://example.com/fondo.jpg",
        )
        self.assertEqual(
            validate_wallpaper_url("http://192.168.100.5:8000/x.png"),
            "http://192.168.100.5:8000/x.png",
        )

    def test_urls_invalidas(self):
        from server.web_server import validate_wallpaper_url

        for bad in (
            "",
            "   ",
            "file:///etc/passwd",
            "ftp://example.com/x.jpg",
            "javascript:alert(1)",
            "data:image/png;base64,AAA",
            "https://",  # sin host
            "example.com/sin-esquema.jpg",
            "x" * 2049,
        ):
            with self.assertRaises(ValueError, msg=f"debería rechazar: {bad[:30]}"):
                validate_wallpaper_url(bad)


class TestDownloadWallpaper(unittest.TestCase):
    def _parchear_urlopen(self, monkey_data: bytes, content_type="image/png"):
        import urllib.request
        from tools.system_control import system_control

        orig = urllib.request.urlopen
        urllib.request.urlopen = lambda req, timeout=None: FakeResp(monkey_data, content_type)
        self.addCleanup(setattr, urllib.request, "urlopen", orig)
        return system_control

    def test_descarga_imagen_valida(self):
        import tempfile

        sc = self._parchear_urlopen(make_png_bytes(), "image/png")
        path = sc._download_wallpaper_image("https://example.com/fondo.png")
        try:
            self.assertTrue(os.path.exists(path))
            self.assertTrue(path.endswith(".png"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            if os.path.exists(path):
                os.unlink(path)
        self.assertTrue(path.startswith(tempfile.gettempdir()))

    def test_rechaza_content_type_no_imagen(self):
        sc = self._parchear_urlopen(make_png_bytes(), "image/png")
        # Mismo bytes pero el servidor dice text/html -> se rechaza igual.
        import urllib.request

        urllib.request.urlopen = lambda req, timeout=None: FakeResp(make_png_bytes(), "text/html")
        with self.assertRaises(ValueError):
            sc._download_wallpaper_image("https://example.com/fondo.png")

    def test_rechaza_bytes_que_no_son_imagen(self):
        sc = self._parchear_urlopen(b"<html>no soy imagen</html>", "image/png")
        with self.assertRaises(ValueError):
            sc._download_wallpaper_image("https://example.com/fondo.png")

    def test_rechaza_sobretamano(self):
        sc = self._parchear_urlopen(make_png_bytes(), "image/png")
        sc.WALLPAPER_MAX_BYTES = 10  # instancia: no toca la clase
        try:
            with self.assertRaises(ValueError):
                sc._download_wallpaper_image("https://example.com/fondo.png")
        finally:
            del sc.WALLPAPER_MAX_BYTES

    def test_rechaza_esquema_invalido_sin_red(self):
        from tools.system_control import system_control

        with self.assertRaises(ValueError):
            system_control._download_wallpaper_image("file:///etc/passwd")

    def test_detect_image_kind(self):
        from tools.system_control import SystemControl

        self.assertEqual(SystemControl._detect_image_kind(b"\xff\xd8\xff" + b"0" * 10), "jpg")
        self.assertEqual(SystemControl._detect_image_kind(b"\x89PNG\r\n\x1a\n" + b"0" * 10), "png")
        self.assertEqual(SystemControl._detect_image_kind(b"GIF89a" + b"0" * 10), "gif")
        self.assertEqual(SystemControl._detect_image_kind(b"BM" + b"0" * 10), "bmp")
        self.assertIsNone(SystemControl._detect_image_kind(b"esto no es imagen"))


class TestHubFirmaRpc(unittest.TestCase):
    """El hub firma cada remote_exec con el token de cada satélite."""

    class FakeSatWs:
        def __init__(self):
            self.sent = []

        async def send_text(self, msg):
            self.sent.append(msg)

    def _hub_con_satelite(self, token_guardado):
        from server.websocket_hub import WebSocketHub

        hub = WebSocketHub()
        ws = self.FakeSatWs()
        hub.satellite_connections.add(ws)
        hub.connection_meta[ws] = {"role": "satellite"}
        if token_guardado:
            hub.connection_meta[ws]["rpc_token"] = token_guardado
        return hub, ws

    def test_firma_por_conexion_y_verificable(self):
        import asyncio
        import json

        hub, ws = self._hub_con_satelite("tok-sat")
        ok = asyncio.run(hub.send_rpc_to_satellites({
            "type": "remote_exec", "action": "mute", "args": {}, "request_id": "r9",
        }))
        self.assertTrue(ok)
        payload = json.loads(ws.sent[0])
        self.assertIn("hmac", payload)
        # El satélite lo verifica con su token...
        self.assertTrue(rpc_auth.verify_remote_command("tok-sat", payload))
        # ...y lo rechaza con otro token.
        self.assertFalse(rpc_auth.verify_remote_command("impostor", payload))

    def test_satelite_viejo_sin_handshake_no_recibe_ordenes(self):
        # P0-4 (fix fail-open): un satélite viejo conectado pero SIN
        # handshake de autenticación mutua (sin rpc_token guardado) NO
        # debe recibir la orden. Falla cerrado: se conecta pero no ejecuta.
        import asyncio

        hub, ws = self._hub_con_satelite(token_guardado="")
        ok = asyncio.run(hub.send_rpc_to_satellites({
            "type": "remote_exec", "action": "mute", "args": {}, "request_id": "r9",
        }))
        self.assertFalse(ok)
        self.assertEqual(ws.sent, [])

    def test_satelite_viejo_no_bloquea_a_satelite_nuevo(self):
        # Fail-closed por conexión: el satélite viejo no recibe nada,
        # pero el satélite nuevo (con handshake) sí recibe su orden firmada.
        import asyncio
        import json

        from server.websocket_hub import WebSocketHub

        hub = WebSocketHub()
        ws_viejo = self.FakeSatWs()
        ws_nuevo = self.FakeSatWs()
        hub.satellite_connections.add(ws_viejo)
        hub.satellite_connections.add(ws_nuevo)
        hub.connection_meta[ws_viejo] = {"role": "satellite"}
        hub.connection_meta[ws_nuevo] = {"role": "satellite", "rpc_token": "tok-sat"}
        ok = asyncio.run(hub.send_rpc_to_satellites({
            "type": "remote_exec", "action": "mute", "args": {}, "request_id": "r9",
        }))
        self.assertTrue(ok)
        self.assertEqual(ws_viejo.sent, [])
        payload = json.loads(ws_nuevo.sent[0])
        self.assertIn("hmac", payload)
        self.assertTrue(rpc_auth.verify_remote_command("tok-sat", payload))

    def test_sin_satelites_no_envia(self):
        import asyncio

        from server.websocket_hub import WebSocketHub

        hub = WebSocketHub()
        ok = asyncio.run(hub.send_rpc_to_satellites({"type": "remote_exec"}))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
