from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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
        data = self._load()
        data["devices"][clean_id] = {
            "roles": sorted(set(roles)),
            "enabled": True,
            "token_sha256": self._hash_token(token),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return token, data["devices"][clean_id]

    def revoke(self, device_id: str) -> bool:
        data = self._load()
        device = data["devices"].get(device_id)
        if not device:
            return False
        device["enabled"] = False
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True

    def list_devices(self) -> Dict[str, Any]:
        return self._load().get("devices", {})


registry = DeviceRegistry()
