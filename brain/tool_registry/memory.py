"""Herramientas de memoria y notas."""



def remember(key: str, value: str) -> str:

    """Guarda un recuerdo, dato personal o preferencia del usuario a largo plazo para nunca olvidarlo."""

    from core.memory import titan_memory

    return titan_memory.remember(key, value)


def recall(key: str) -> str:

    """Busca en la memoria a largo plazo lo que Titán recuerda sobre una palabra, tema o preferencia."""

    from core.memory import titan_memory

    return titan_memory.recall(key)


def list_memories() -> str:

    """Lista todos los recuerdos y preferencias guardadas en la memoria de Titán."""

    from core.memory import titan_memory

    return titan_memory.list_all_memories()


def add_note(text: str) -> str:

    """Anota una tarea, pendiente o recordatorio en la lista de notas personales."""

    from core.memory import titan_memory

    return titan_memory.add_note(text)


def get_notes() -> str:

    """Muestra todas las notas y recordatorios pendientes del usuario."""

    from core.memory import titan_memory

    return titan_memory.get_notes()


def delete_note(note_id_or_text: str) -> str:

    """Elimina una nota por su número de ID o texto coincidente."""

    from core.memory import titan_memory

    return titan_memory.delete_note(note_id_or_text)
