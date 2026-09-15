from __future__ import annotations

import secrets
import time
from typing import Dict, Optional, Tuple


class PairingManager:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._codes: Dict[str, Tuple[str, str, float]] = {}

    def create(self, device_id: str, token: str) -> str:
        self._purge()
        code = f"{secrets.randbelow(1_000_000):06d}"
        while code in self._codes:
            code = f"{secrets.randbelow(1_000_000):06d}"
        self._codes[code] = (device_id, token, time.time() + self.ttl_seconds)
        return code

    def claim(self, code: str) -> Optional[Tuple[str, str]]:
        self._purge()
        record = self._codes.pop(str(code).strip(), None)
        if not record:
            return None
        device_id, token, expires_at = record
        if expires_at < time.time():
            return None
        return device_id, token

    def _purge(self) -> None:
        now = time.time()
        self._codes = {code: record for code, record in self._codes.items() if record[2] >= now}


pairing_manager = PairingManager()
