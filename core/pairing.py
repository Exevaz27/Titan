from __future__ import annotations

import secrets
import time
from typing import Dict, List, Optional


class PairingManager:
    """Códigos de emparejamiento de 6 dígitos, de un solo uso y con TTL.

    Dos tipos de código:
    - "pair": lo genera un admin desde /admin para un dispositivo ya enrolado.
      Al canjearlo se entregan las cookies de ese dispositivo.
    - "setup": código de configuración inicial. Se genera al arrancar Titán
      (y se muestra SOLO en consola) cuando no hay ningún dispositivo con
      rol "api". Al canjearlo se enrola un dispositivo nuevo con esos roles.
    """

    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._codes: Dict[str, Dict] = {}

    def _new_code(self) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        while code in self._codes:
            code = f"{secrets.randbelow(1_000_000):06d}"
        return code

    def create(self, device_id: str, token: str) -> str:
        self._purge()
        code = self._new_code()
        self._codes[code] = {
            "kind": "pair",
            "device_id": device_id,
            "token": token,
            "expires_at": time.time() + self.ttl_seconds,
        }
        return code

    def create_setup(self, roles: List[str], ttl_seconds: int = 600) -> str:
        """Genera un código de configuración inicial (mostrar solo en consola)."""
        self._purge()
        code = self._new_code()
        self._codes[code] = {
            "kind": "setup",
            "roles": list(roles),
            "expires_at": time.time() + ttl_seconds,
        }
        return code

    def claim(self, code: str) -> Optional[Dict]:
        self._purge()
        record = self._codes.pop(str(code).strip(), None)
        if not record:
            return None
        if record["expires_at"] < time.time():
            return None
        return record

    def _purge(self) -> None:
        now = time.time()
        self._codes = {code: record for code, record in self._codes.items() if record["expires_at"] >= now}


pairing_manager = PairingManager()
