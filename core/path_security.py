from pathlib import Path


def safe_zip_member_path(destination: Path, member_name: str) -> Path:
    """Devuelve la ruta segura de un miembro ZIP o lanza ValueError."""
    resolved_destination = destination.resolve()
    member_path = (resolved_destination / member_name).resolve()
    try:
        member_path.relative_to(resolved_destination)
    except ValueError as exc:
        raise ValueError(f"Ruta ZIP fuera del destino: {member_name}") from exc
    return member_path