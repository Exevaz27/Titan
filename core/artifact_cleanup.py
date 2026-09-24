"""P0-5 — Limpieza de artefactos privados/residuales.

Titán genera archivos con datos privados que se acumulan sin límite:

- Satélite Windows: `~/Pictures/Screenshots/captura_*.png` — CADA captura
  (incluso las de "mirá la pantalla", que el usuario nunca pidió guardar)
  quedaba permanente en disco.
- Satélite Windows: `%TEMP%/titan_wallpaper.*` — descargas de fondos (P0-4).
- DDR3: `server/static/generated/titan_img_*.jpg` — imágenes IA servidas
  por /static, crecen sin tope.

Este módulo barre esos directorios con dos reglas por spec:
1. TTL: se borra lo más viejo que N días.
2. Tope de tamaño: si el total supera el máximo, se borra lo más viejo
   primero hasta entrar en el tope.

Solo biblioteca estándar: también corre en el paquete mínimo del satélite.
"""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List


@dataclass
class ArtifactSpec:
    """Describe un conjunto de artefactos a limpiar."""

    name: str
    directory: Callable[[], Path] | Path
    patterns: List[str] = field(default_factory=lambda: ["*"])
    ttl_days: float = 30.0
    max_bytes: int = 1024 * 1024 * 1024  # 1 GB por defecto
    only_platform: str = ""  # "nt" / "posix" / "" (todas)

    def resolve_dir(self) -> Path | None:
        d = self.directory() if callable(self.directory) else self.directory
        try:
            return Path(d)
        except Exception:
            return None


def _pictures_screenshots_dir() -> Path:
    return Path.home() / "Pictures" / "Screenshots"


def _temp_dir() -> Path:
    import tempfile

    return Path(tempfile.gettempdir())


def _generated_images_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "server" / "static" / "generated"


def default_specs() -> List[ArtifactSpec]:
    """Specs registrados por defecto (según plataforma)."""
    return [
        ArtifactSpec(
            name="screenshots",
            directory=_pictures_screenshots_dir,
            patterns=["captura_*.png"],
            ttl_days=30.0,
            max_bytes=1024 * 1024 * 1024,  # 1 GB
            only_platform="nt",
        ),
        ArtifactSpec(
            name="wallpaper_tmp",
            directory=_temp_dir,
            patterns=["titan_wallpaper.*"],
            ttl_days=7.0,
            max_bytes=512 * 1024 * 1024,  # 512 MB
            only_platform="nt",
        ),
        ArtifactSpec(
            name="generated_images",
            directory=_generated_images_dir,
            patterns=["titan_img_*.jpg"],
            ttl_days=30.0,
            max_bytes=2 * 1024 * 1024 * 1024,  # 2 GB
        ),
    ]


def sweep_spec(spec: ArtifactSpec) -> Dict[str, int]:
    """Limpia un spec. Devuelve {'deleted': n, 'bytes_freed': b}."""
    result = {"deleted": 0, "bytes_freed": 0}
    if spec.only_platform and os.name != spec.only_platform:
        return result
    directory = spec.resolve_dir()
    if directory is None or not directory.is_dir():
        return result

    now = time.time()
    ttl_seconds = spec.ttl_days * 86400.0

    candidates: List[tuple[float, Path, int]] = []  # (mtime, path, size)
    for entry in directory.iterdir():
        try:
            if not entry.is_file():
                continue
            if not any(fnmatch.fnmatch(entry.name, pat) for pat in spec.patterns):
                continue
            st = entry.stat()
            candidates.append((st.st_mtime, entry, st.st_size))
        except OSError:
            continue

    def _delete(path: Path, size: int) -> None:
        try:
            path.unlink()
            result["deleted"] += 1
            result["bytes_freed"] += size
        except OSError:
            pass

    # 1. TTL: borrar lo vencido.
    survivors: List[tuple[float, Path, int]] = []
    for mtime, path, size in candidates:
        if now - mtime > ttl_seconds:
            _delete(path, size)
        else:
            survivors.append((mtime, path, size))

    # 2. Tope de tamaño: borrar lo más viejo primero.
    survivors.sort(key=lambda c: c[0])  # más viejo primero
    total = sum(size for _, _, size in survivors)
    for mtime, path, size in survivors:
        if total <= spec.max_bytes:
            break
        _delete(path, size)
        total -= size

    return result


def sweep_all(specs: List[ArtifactSpec] | None = None) -> Dict[str, Dict[str, int]]:
    """Barre todos los specs. Devuelve {nombre_spec: resultado}."""
    report: Dict[str, Dict[str, int]] = {}
    for spec in default_specs() if specs is None else specs:
        try:
            report[spec.name] = sweep_spec(spec)
        except Exception:
            report[spec.name] = {"deleted": 0, "bytes_freed": 0}
    return report
