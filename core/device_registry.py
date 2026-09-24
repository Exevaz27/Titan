from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.json_store import atomic_write_json, json_locked


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "authorized_devices.json"


class DeviceRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"devices": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data.get("devices"), dict) else {"devices": {}}
        except (OSError, ValueError):
            return {"devices": {}}

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def verify(self, device_id: str, token: str, role: str) -> bool:
        device = self._load().get("devices", {}).get(device_id)
        if not device or not device.get("enabled", True):
            return False
        if role not in device.get("roles", []):
            return False
        expected = str(device.get("token_sha256", ""))
        return bool(expected and secrets.compare_digest(self._hash_token(token), expected))

    def enroll(self, device_id: str, roles: list[str]) -> Tuple[str, Dict[str, Any]]:
        clean_id = device_id.strip()
        if not clean_id or not roles:
            raise ValueError("El dispositivo necesita un ID y al menos un rol")
        token = secrets.token_urlsafe(32)
        # R-6: la actualización es read-modify-write bajo lock exclusivo
        # (hilos + otros procesos) y la escritura es atómica: dos enrolamientos
        # concurrentes ya no se pisan, y un corte a mitad de escritura no deja
        # un JSON truncado.
        with json_locked(self.path):
            data = self._load()
            data["devices"][clean_id] = {
                "roles": sorted(set(roles)),
                "enabled": True,
                "token_sha256": self._hash_token(token),
            }
            atomic_write_json(self.path, data)
        return token, data["devices"][clean_id]

    def revoke(self, device_id: str) -> bool:
        with json_locked(self.path):
            data = self._load()
            device = data["devices"].get(device_id)
            if not device:
                return False
            device["enabled"] = False
            atomic_write_json(self.path, data)
        return True

    def grant_role(self, device_id: str, role: str) -> bool:
        """S-4: agrega un rol a un dispositivo existente (migración al rol
        admin). Devuelve True si el rol se agregó."""
        clean_id = device_id.strip()
        if not clean_id or not role:
            return False
        with json_locked(self.path):
            data = self._load()
            device = data["devices"].get(clean_id)
            if not device or not device.get("enabled", True):
                return False
            roles = set(device.get("roles", []))
            if role in roles:
                return False
            roles.add(role)
            device["roles"] = sorted(roles)
            atomic_write_json(self.path, data)
        return True

    def list_devices(self) -> Dict[str, Any]:
        return self._load().get("devices", {})


registry = DeviceRegistry()
