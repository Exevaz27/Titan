"""R-6: escrituras JSON atómicas con lock entre procesos.

Varios registros (authorized_devices.json y otros JSON de estado) se
actualizaban con read-modify-write sin ningún lock y con write_text no
atómico: dos escrituras concurrentes (ej. enrolar desde el /admin y revocar
desde la CLI al mismo tiempo) podían perderse entre sí, y un corte de luz o
un kill a mitad de escritura dejaba un JSON truncado e ilegible.

Este módulo da las dos piezas:
  - atomic_write_json(): escribe a un tmp en el mismo directorio y hace
    os.replace(); el destino siempre queda completo o intacto, nunca a medias.
  - json_locked(): lock exclusivo entre procesos (flock en Unix) + lock de
    hilos, para que el read-modify-write sea una sección crítica.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict

try:
    import fcntl  # Unix (DDR3). En Windows no existe: se usa solo el lock de hilos.
except ImportError:  # pragma: no cover
    fcntl = None


_THREAD_LOCKS: Dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path: Path) -> threading.Lock:
    key = str(Path(path).resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


def atomic_write_json(path: Path, data: Any) -> None:
    """Escribe JSON de forma atómica: tmp en el mismo directorio + os.replace.

    Un corte a mitad de escritura nunca deja el archivo destino corrupto:
    los lectores ven el contenido viejo completo o el nuevo completo.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class json_locked:
    """Sección crítica para actualizar un JSON: lock entre procesos + hilos.

    Uso:
        with json_locked(path):
            data = cargar(path)
            ... mutar data ...
            atomic_write_json(path, data)
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._thread_lock = _thread_lock_for(self.path)
        self._lock_file = None

    def __enter__(self):
        self._thread_lock.acquire()
        if fcntl is not None:
            # Archivo de lock separado: el JSON puede no existir todavía.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file = open(str(self.path) + ".lock", "w")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            if self._lock_file is not None and fcntl is not None:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
        finally:
            self._thread_lock.release()
        return False
