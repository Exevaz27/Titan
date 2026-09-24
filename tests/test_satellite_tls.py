"""S-11: tests del canal TLS del satélite (wss:// con cert pineado)."""
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import satellite_tls
from core.satellite_tls import (
    CERT_FILENAME,
    KEY_FILENAME,
    build_tls_server_config,
    build_ws_target,
    client_ssl_context,
    server_ssl_context,
)

NEEDS_OPENSSL = unittest.skipIf(
    shutil.which("openssl") is None, "openssl no disponible"
)


def _make_cert(tmp_path: Path, san: str = "IP:127.0.0.1") -> Path:
    """Genera un cert autofirmado de prueba en tmp_path/certs/."""
    certs = tmp_path / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(certs / KEY_FILENAME),
            "-out", str(certs / CERT_FILENAME),
            "-days", "2", "-nodes",
            "-subj", "/CN=Titan-Test",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestSatelliteTLS(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    @NEEDS_OPENSSL
    def test_build_ws_target_prefiere_wss_con_cert(self):
        root = _make_cert(self.tmp_path)
        url, ctx = build_ws_target("192.168.100.5", 8000, 8443, root=root)
        self.assertEqual(url, "wss://192.168.100.5:8443/ws")
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_build_ws_target_cae_a_ws_sin_cert(self):
        url, ctx = build_ws_target("192.168.100.5", 8000, 8443, root=self.tmp_path)
        self.assertEqual(url, "ws://192.168.100.5:8000/ws")
        self.assertIsNone(ctx)

    @NEEDS_OPENSSL
    def test_server_ssl_context_ok_y_none(self):
        root = _make_cert(self.tmp_path)
        self.assertIsInstance(server_ssl_context(root), ssl.SSLContext)
        self.assertIsNone(server_ssl_context(self.tmp_path / "vacio"))

    @NEEDS_OPENSSL
    def test_build_tls_server_config(self):
        root = _make_cert(self.tmp_path)
        cfg = build_tls_server_config(object(), "0.0.0.0", 8443)
        self.assertTrue(cfg is None or hasattr(cfg, "app"))

    @NEEDS_OPENSSL
    def test_handshake_tls_con_cert_pineado(self):
        root = _make_cert(self.tmp_path)
        crt, key = root / "certs" / CERT_FILENAME, root / "certs" / KEY_FILENAME

        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile=str(crt), keyfile=str(key))

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        received = {}

        def _serve():
            conn, _ = srv.accept()
            with server_ctx.wrap_socket(conn, server_side=True) as tls:
                received["data"] = tls.recv(16)
                tls.sendall(b"ok")

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        client_ctx = client_ssl_context(root)
        with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
            with client_ctx.wrap_socket(raw, server_hostname="127.0.0.1") as tls:
                tls.sendall(b"ping")
                self.assertEqual(tls.recv(16), b"ok")
        t.join(timeout=10)
        srv.close()
        self.assertEqual(received.get("data"), b"ping")

    @NEEDS_OPENSSL
    def test_cliente_rechaza_otro_cert(self):
        root_bueno = _make_cert(self.tmp_path / "bueno")
        root_malo = _make_cert(self.tmp_path / "malo")
        crt_m, key_m = root_malo / "certs" / CERT_FILENAME, root_malo / "certs" / KEY_FILENAME

        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile=str(crt_m), keyfile=str(key_m))

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def _serve():
            try:
                conn, _ = srv.accept()
                with server_ctx.wrap_socket(conn, server_side=True):
                    pass
            except Exception:
                pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        client_ctx = client_ssl_context(root_bueno)
        with self.assertRaises(ssl.SSLCertVerificationError):
            with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
                with client_ctx.wrap_socket(raw, server_hostname="127.0.0.1"):
                    pass
        t.join(timeout=10)
        srv.close()

    def test_default_tls_port(self):
        self.assertEqual(satellite_tls.DEFAULT_TLS_PORT, 8443)


if __name__ == "__main__":
    unittest.main()
