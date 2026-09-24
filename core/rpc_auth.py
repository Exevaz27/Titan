"""P0-4 — Autenticación mutua del canal RPC con el satélite Windows.

Problema que resuelve: hasta P0-3 el satélite se autenticaba ante el servidor
con su token, pero el servidor NUNCA se autenticaba ante el satélite. Cualquiera
en la LAN capaz de suplantar a la DDR3 (IP libre, ARP spoofing, host mal
configurado) podía recibir la conexión del satélite y enviarle `remote_exec`
con acciones como `shutdown_pc`, `get_clipboard` o `take_screenshot`, y el
satélite las obedecía a ciegas.

Mecanismo (HMAC-SHA256 con el token del satélite como clave compartida):

1. Handshake: el satélite genera un nonce aleatorio y lo manda en
   `register_satellite`. El servidor responde `satellite_auth_ok` con
   `server_proof = HMAC("titan-satellite-server-proof:v1:" + nonce)`.
   El satélite verifica el proof antes de aceptar cualquier `remote_exec`.
   Solo quien conoce el token puede generar un proof válido.

2. Por comando: cada `remote_exec` lleva `hmac = HMAC("v1|" + request_id + "|"
   + action + "|" + args_canónicos)`. El satélite lo verifica antes de
   ejecutar. Esto protege también contra inyección de comandos en una
   conexión ya establecida.

Este módulo usa SOLO la stdlib para poder importarse tanto en el servidor
(DDR3) como en el paquete mínimo del satélite (Windows).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

# Dominio separado por uso: que un proof de handshake no sirva como firma de
# comando ni viceversa.
_PROOF_DOMAIN = "titan-satellite-server-proof:v1:"
_COMMAND_DOMAIN = "titan-satellite-remote-exec:v1:"


def generate_nonce(nbytes: int = 32) -> str:
    """Genera un nonce aleatorio (hex) para el desafío del handshake."""
    return secrets.token_hex(nbytes)


def server_proof(token: str, nonce: str) -> str:
    """Calcula el proof que el servidor debe devolver en el handshake."""
    if not token or not nonce:
        raise ValueError("token y nonce son obligatorios para el proof")
    return hmac.new(
        token.encode("utf-8"),
        (_PROOF_DOMAIN + nonce).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_server_proof(token: str, nonce: str, proof: str) -> bool:
    """Verifica el proof del servidor (lado satélite). Falla cerrado."""
    if not token or not nonce or not proof:
        return False
    try:
        expected = server_proof(token, nonce)
    except ValueError:
        return False
    return hmac.compare_digest(expected, proof)


def canonical_args(args: dict) -> str:
    """Serialización canónica de los args para firmar (orden estable)."""
    return json.dumps(args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_remote_command(token: str, request_id: str, action: str, args: dict) -> str:
    """Firma un comando remote_exec (lado servidor)."""
    if not token or not request_id or not action:
        raise ValueError("token, request_id y action son obligatorios para firmar")
    message = "|".join((_COMMAND_DOMAIN, request_id, action, canonical_args(args)))
    return hmac.new(token.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_remote_command(token: str, payload: dict) -> bool:
    """Verifica la firma de un remote_exec recibido (lado satélite).

    `payload` es el dict completo del mensaje (con request_id, action, args
    y hmac). Falla cerrado ante cualquier manipulación o campo faltante.
    """
    if not token or not isinstance(payload, dict):
        return False
    try:
        expected = sign_remote_command(
            token,
            str(payload.get("request_id", "")),
            str(payload.get("action", "")),
            payload.get("args") if isinstance(payload.get("args"), dict) else {},
        )
    except ValueError:
        return False
    return hmac.compare_digest(expected, str(payload.get("hmac", "")))
