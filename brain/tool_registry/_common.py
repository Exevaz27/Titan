"""Helpers internos del registry (clamp, memoria de último archivo)."""

# Lo actualizan search_files, read_file_content y open_file; lo lee local_intents.

_last_file_path: str = ""



def _clamp(value, lo: int, hi: int, default: int) -> int:
    """R-3: valida rangos de los argumentos numéricos que vienen del LLM.
    Un valor absurdo (ej. volumen 99999, brillo -50) se recorta al rango
    válido en vez de propagarse a la herramienta."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))



# Último archivo mencionado/encontrado (para resolver "léelo"/"abrilo" sin nombre).

# Lo actualizan search_files, read_file_content y open_file; lo lee local_intents.

_last_file_path: str = ""


def _remember_file(path: str) -> None:

    global _last_file_path

    if path:

        _last_file_path = path


def get_last_file_path() -> str:

    """Devuelve la ruta del último archivo mencionado (o "" si no hay)."""

    return _last_file_path
