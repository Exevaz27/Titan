from __future__ import annotations

import hmac
import os
from typing import Optional

from core.device_registry import registry
from core.logger import log_warning

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _token_from_headers(headers) -> str:
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    token = headers.get("x-titan-token", "").strip()
    if token:
        return token
    cookie_header = headers.get("cookie", "")
    for item in cookie_header.split(";"):
        name, _, value = item.strip().partition("=")
        if name == "titan_token":
            return value.strip()
    return ""


def _device_id_from_headers(headers) -> str:
    device_id = headers.get("x-titan-device-id", "").strip()
    if device_id:
        return device_id
    cookie_header = headers.get("cookie", "")
    for item in cookie_header.split(";"):
        name, _, value = item.strip().partition("=")
        if name == "titan_device_id":
            return value.strip()
    return ""


def _expected_token(role: str) -> str:
    if role == "satellite":
        return os.getenv("TITAN_SATELLITE_TOKEN", "").strip()
    return os.getenv("TITAN_API_TOKEN", "").strip()


def _is_loopback(host: Optional[str]) -> bool:
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def token_is_valid(token: str, role: str) -> bool:
    expected = _expected_token(role)
    return bool(expected and token and hmac.compare_digest(token, expected))


def token_is_valid_for_roles(token: str, roles: tuple[str, ...]) -> bool:
    return any(token_is_valid(token, role) for role in roles)


def device_auth_is_required() -> bool:
    return os.getenv("TITAN_DEVICE_AUTH_REQUIRED", "true").strip().lower() not in {"0", "false", "no"}


def device_is_valid(device_id: str, token: str, roles: tuple[str, ...]) -> bool:
    return bool(device_id and token and any(registry.verify(device_id, token, role) for role in roles))


def authorize_http(request: Request, role: str = "api") -> None:
    from fastapi import HTTPException, status

    client_host = request.client.host if request.client else None
    token = _token_from_headers(request.headers)
    device_id = _device_id_from_headers(request.headers)
    if _is_loopback(client_host) and not token:
        return
    if device_auth_is_required() and device_is_valid(device_id, token, (role,)):
        return
    if device_auth_is_required():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Dispositivo no autorizado")
    if token_is_valid(token, role):
        return
    if not _expected_token(role):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falta configurar TITAN_{'SATELLITE_' if role == 'satellite' else ''}TOKEN",
        )
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de Titán inválido")


async def authorize_websocket(websocket: WebSocket, role: str = "api") -> None:
    from fastapi import WebSocketException

    client_host = websocket.client.host if websocket.client else None
    token = _token_from_headers(websocket.headers)
    device_id = _device_id_from_headers(websocket.headers)
    if not token:
        token = websocket.query_params.get("token", "").strip()
    if not device_id:
        device_id = websocket.query_params.get("device_id", "").strip()
    if _is_loopback(client_host) and not token:
        return
    valid_roles = ("api", "satellite") if role == "ws" else (role,)
    if device_auth_is_required() and device_is_valid(device_id, token, valid_roles):
        return
    if device_auth_is_required():
        log_warning(
            f"[Seguridad] WebSocket rechazado: host={client_host or 'desconocido'}, "
            f"device_id={device_id or 'ausente'}, token={'presente' if token else 'ausente'}, "
            f"roles={','.join(valid_roles)}"
        )
        await websocket.close(code=1008, reason="Dispositivo no autorizado")
        raise WebSocketException(code=1008, reason="Dispositivo no autorizado")
    if token_is_valid_for_roles(token, valid_roles):
        return
    await websocket.close(code=1008, reason="Autenticación requerida")
    raise WebSocketException(code=1008, reason="Autenticación requerida")
