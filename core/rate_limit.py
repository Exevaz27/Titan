"""Rate limiting simple en memoria (P0).

Se usa para frenar fuerza bruta contra /api/pair/claim: el código de
emparejamiento tiene solo 6 dígitos y sin límite de intentos se podría
adivinar. No necesita dependencias externas; vive en memoria del proceso.
"""
from __future__ import annotations

import time
from typing import Dict, Tuple


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 600, lockout_seconds: int = 600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        # key -> (fallos_en_ventana, inicio_ventana, bloqueado_hasta)
        self._state: Dict[str, Tuple[int, float, float]] = {}

    def _prune(self, now: float) -> None:
        for key, (_failures, window_start, blocked_until) in list(self._state.items()):
            if blocked_until and blocked_until < now:
                # Bloqueo expirado: olvidar la clave
                del self._state[key]
            elif not blocked_until and now - window_start > self.window_seconds:
                # Ventana expirada sin bloqueo: reiniciar conteo
                del self._state[key]

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        self._prune(now)
        record = self._state.get(key)
        return bool(record and record[2] > now)

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        record = self._state.get(key)
        if not record:
            return 0
        return max(0, int(record[2] - now))

    def register_failure(self, key: str) -> None:
        now = time.monotonic()
        self._prune(now)
        failures, window_start, _ = self._state.get(key, (0, now, 0.0))
        if now - window_start > self.window_seconds:
            failures, window_start = 0, now
        failures += 1
        blocked_until = now + self.lockout_seconds if failures >= self.max_attempts else 0.0
        self._state[key] = (failures, window_start, blocked_until)

    def register_success(self, key: str) -> None:
        self._state.pop(key, None)
