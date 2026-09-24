from __future__ import annotations

import hmac
import os

from core.device_registry import registry
from core.logger import log_warning

# P0: se eliminó el bypass de autenticación para loopback. TODA conexión
# HTTP/WebSocket necesita credencial válida, venga de donde venga
# (localhost, LAN o Tailscale). Cualquiera en la LAN es una amenaza potencial.


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


def token_is_valid(token: str, role: str) -> bool:
    expected = _expected_token(role)
    return bool(expected and token and hmac.compare_digest(token, expected))


def token_is_valid_for_roles(token: str, roles: tuple[str, ...]) -> bool:
    return any(token_is_valid(token, role) for role in roles)


def device_auth_is_required() -> bool:
    return os.getenv("TITAN_DEVICE_AUTH_REQUIRED", "true").strip().lower() not in {"0", "false", "no"}


def device_is_valid(device_id: str, token: str, roles: tuple[str, ...]) -> bool:
    # S-4: el rol "admin" implica "api" en la capa de transporte. Todo lo que
    # pide rol "api" (middleware de /api/*, HUD, /ws) acepta también admin;
    # lo que pide rol "admin" explícito (/api/admin/*, /admin) sigue siendo
    # exclusivo de admin.
    effective = set(roles)
    if "api" in effective:
        effective.add("admin")
    return bool(device_id and token and any(registry.verify(device_id, token, role) for role in effective))


def api_devices_exist() -> bool:
    """True si hay al menos un dispositivo habilitado con rol 'api'.

    Se usa al arrancar: si no hay ninguno, se genera un código de
    configuración inicial en consola para emparejar el primer navegador/HUD.
    """
    try:
        devices = registry.list_devices()
    except Exception:
        return False
    return any(
        "api" in d.get("roles", []) and d.get("enabled", True)
        for d in devices.values()
        if isinstance(d, dict)
    )


def admin_devices_exist() -> bool:
    """S-4: True si hay al menos un dispositivo habilitado con rol 'admin'."""
    try:
        devices = registry.list_devices()
    except Exception:
        return False
    return any(
        "admin" in d.get("roles", []) and d.get("enabled", True)
        for d in devices.values()
        if isinstance(d, dict)
    )


def ensure_admin_role() -> int:
    """S-4 (migración, idempotente): si ningún dispositivo tiene rol 'admin',
    se lo otorga a cada dispositivo habilitado con rol 'api'.

    Antes de S-4 todos los 'api' podían gestionar dispositivos desde /admin
    (eran igual de confiables); la migración conserva ese acceso existente
    mientras el rol queda establecido para el futuro (los dispositivos nuevos
    se enrolan con el rol mínimo). Devuelve cuántos se promovieron.
    """
    try:
        devices = registry.list_devices()
    except Exception:
        return 0
    if admin_devices_exist():
        return 0
    promoted = 0
    for device_id, d in devices.items():
        if (
            isinstance(d, dict)
            and "api" in d.get("roles", [])
            and d.get("enabled", True)
            and registry.grant_role(device_id, "admin")
        ):
            promoted += 1
    if promoted:
        log_warning(
            f"[Seguridad] S-4: {promoted} dispositivo(s) 'api' recibieron el rol "
            "'admin' (migración por única vez; los nuevos se enrolan con rol mínimo)."
        )
    return promoted


def authorize_http(request: Request, role: str = "api") -> None:
    from fastapi import HTTPException, status

    # P0: sin bypass de loopback. Sin credencial válida no hay acceso.
    token = _token_from_headers(request.headers)
    device_id = _device_id_from_headers(request.headers)
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

    # P0: sin bypass de loopback y sin tokens en query strings (quedan en
    # historial/logs). Solo headers o cookies.
    token = _token_from_headers(websocket.headers)
    device_id = _device_id_from_headers(websocket.headers)
    valid_roles = ("api", "satellite") if role == "ws" else (role,)
    if device_auth_is_required() and device_is_valid(device_id, token, valid_roles):
        return
    if device_auth_is_required():
        client_host = websocket.client.host if websocket.client else None
        log_warning(
            f"[Seguridad] WebSocket rechazado: host={client_host or 'desconocido'}, "
            f"device_id={device_id or 'ausente'}, token={'presente' if token else 'ausente'}, "
            f"roles={','.join(valid_roles)}"
        )
        # P0: no cerrar el socket acá. Al lanzar WebSocketException, el
        # manejador interno de Starlette lo cierra con ese código/motivo.
        # (Cerrar antes del raise provocaba doble close -> RuntimeError.)
        raise WebSocketException(code=1008, reason="Dispositivo no autorizado")
    if token_is_valid_for_roles(token, valid_roles):
        return
    raise WebSocketException(code=1008, reason="Autenticación requerida")
