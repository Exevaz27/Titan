"""S-11: canal TLS dedicado para el satélite (wss://).

Antes el satélite se conectaba por ``ws://`` en texto plano: el token
(X-Titan-Token) y todo el tráfico viajaban sniffables para cualquiera en
la LAN doméstica. Ahora el servidor expone la MISMA app FastAPI en un
segundo puerto solo-TLS (por defecto 8443) y el satélite se conecta por
``wss://`` verificando el certificado autofirmado que viaja pineado en
su propio paquete.

Por qué un segundo puerto y no TLS en todo: el HUD del J2 y el /pair
del celular usan el puerto 8000 con navegadores viejos; un cert
autofirmado para una IP de LAN ahí daría pantallas de advertencia. El
puerto 8000 queda intacto; solo el satélite usa el 8443.

Por qué autofirmado y no un CA público: ningún CA público firma
certificados para IPs privadas (192.168.100.x). El satélite no confía
en el sistema: confía ÚNICAMENTE en este cert (pinning), así que un
atacante en la LAN no puede hacer MITM con otro certificado.
"""
from __future__ import annotations

import ssl
from pathlib import Path
from typing import Optional, Tuple

CERT_FILENAME = "titan-satellite.crt"
KEY_FILENAME = "titan-satellite.key"
DEFAULT_TLS_PORT = 8443


def repo_root() -> Path:
    """Raíz del proyecto (sirve tanto en ~/titan como en D:\\Titan-Satelite)."""
    return Path(__file__).resolve().parent.parent


def cert_paths(root: Optional[Path] = None) -> Tuple[Path, Path]:
    """Devuelve (certificado, clave privada) bajo <root>/certs/."""
    base = (root or repo_root()) / "certs"
    return base / CERT_FILENAME, base / KEY_FILENAME


def server_ssl_context(root: Optional[Path] = None) -> Optional[ssl.SSLContext]:
    """Contexto TLS del servidor. None si faltan los archivos (el listener
    TLS no se levanta y el satélite cae al plan B con aviso)."""
    crt, key = cert_paths(root)
    if not crt.is_file() or not key.is_file():
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(crt), keyfile=str(key))
    return ctx


def build_tls_server_config(app, host: str, port: int):
    """uvicorn.Config con TLS para el canal del satélite.

    Devuelve None si no hay certificado (el servidor sigue solo con el
    puerto plano). Importa uvicorn acá para no cargarlo en el satélite.
    """
    import uvicorn

    crt, key = cert_paths()
    if not crt.is_file() or not key.is_file():
        return None
    return uvicorn.Config(
        app=app,
        host=host,
        port=port,
        ssl_certfile=str(crt),
        ssl_keyfile=str(key),
        log_level="warning",
        loop="asyncio",
    )


def client_ssl_context(root: Optional[Path] = None) -> Optional[ssl.SSLContext]:
    """Contexto TLS del satélite: confía SOLO en el cert pineado.

    Devuelve None si el archivo no está (el satélite avisa fuerte y usa
    ws:// como plan B para no quedar muerto por una instalación incompleta;
    ese fallback NO lo puede disparar un atacante de red, solo la falta
    del archivo local).
    """
    crt, _key = cert_paths(root)
    if not crt.is_file():
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=str(crt))
    return ctx


def build_ws_target(
    host: str,
    plain_port: int,
    tls_port: int,
    root: Optional[Path] = None,
) -> Tuple[str, Optional[ssl.SSLContext]]:
    """Elige la URL del WebSocket del satélite.

    Devuelve (url, ssl_ctx): ``wss://`` con contexto verificado si está el
    cert pineado; si no, ``ws://`` con None (el llamador debe avisar).
    """
    ctx = client_ssl_context(root)
    if ctx is not None:
        return f"wss://{host}:{tls_port}/ws", ctx
    return f"ws://{host}:{plain_port}/ws", None
