"""Herramientas de archivos y apps."""

from tools.app_launcher import app_launcher

from tools.file_manager import file_manager

from ._common import _clamp, _remember_file



def launch_app(app_name: str) -> str:

    """Abre un programa o aplicación nativa o portable en Windows por su nombre (ej: 'spotify', 'inkscape', 'calculadora', 'chrome', 'notepad')."""

    res = app_launcher.launch_app(app_name)

    return res.get("message", str(res))


def register_portable_app(alias: str, file_path: str) -> str:

    """Registra una nueva aplicación o ejecutable portable en el catálogo apps_catalog.json con un alias amigable."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("register_portable_app", alias=alias, file_path=file_path)


def search_files(query: str, extension: str = "", location: str = "", max_results: int = 8) -> str:

    """Busca archivos en la computadora por nombre o extensión en los discos y carpetas configuradas."""

    res = file_manager.search_files(

        query=query,

        extension=extension if extension else None,

        location=location if location else None,

        # R-9: max_results viene del LLM sin validar; un valor absurdo
        # (ej. 100000) pondría a Titán a recorrer el disco. Tope 50.
        max_results=_clamp(max_results, 1, 50, 8)

    )

    # B-3: si la búsqueda falló (satélite desconectado, timeout RPC, excepción),
    # el dict trae status de error y NO tiene "count"/"files" -> devolver el
    # mensaje en vez de reventar con KeyError.
    if not isinstance(res, dict) or res.get("status") != "success":
        msg = res.get("message") if isinstance(res, dict) else None
        return msg or f"No pude buscar archivos para '{query}' en este momento."

    count = res.get("count", 0)

    if count == 0:

        return f"No se encontraron archivos con el término '{query}'."

    files = res.get("files", [])

    _remember_file(files[0].get("path", "") if files else "")

    lines = [f"Se encontraron {count} archivo(s):"]

    for f in files:

        size = f.get('size_kb', 0)

        lines.append(f"- {f.get('name', '?')} ({size} KB) en: {f.get('path', '')}")

    return "\n".join(lines)


def open_file(file_path: str) -> str:

    """Abre un archivo con su programa predeterminado para MOSTRARLO en pantalla.

    NO lee ni devuelve el contenido del archivo. Usar SOLO cuando el usuario pide
    explícitamente abrir/mostrar el archivo en pantalla ("abrilo", "mostramelo").
    Si el usuario quiere saber qué dice el archivo ("leé", "léelo", "qué dice"),
    usar read_file_content en su lugar."""

    _remember_file(file_path)

    res = file_manager.open_file(file_path)

    return res.get("message", str(res))


def show_in_folder(file_path: str) -> str:

    """Abre el explorador de archivos de Windows y resalta el archivo indicado."""

    res = file_manager.show_in_folder(file_path)

    return res.get("message", str(res))


def trash_file(file_path: str) -> str:

    """Manda un archivo a la papelera de reciclaje de Windows de forma segura (sin borrarlo permanentemente)."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("trash_file", file_path=file_path)


def move_file(source: str, destination: str) -> str:

    """Mueve un archivo de una ruta origen a una ruta destino."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("move_file", source=source, destination=destination)


def copy_file(source: str, destination: str) -> str:

    """Copia un archivo de una ruta a otra."""

    from brain.local_intents import local_intents
    # S-6: pide confirmación solo si va a pisar un archivo existente.
    if file_manager.resolve_copy_target(source, destination).exists():
        return local_intents.request_confirmation(
            "copy_file", source=source, destination=destination
        )
    res = file_manager.copy_file(source, destination)

    return res.get("message", str(res))


def read_file_content(file_path: str) -> str:

    """Lee y devuelve el CONTENIDO (texto) de un archivo para responder sobre él o leérselo al usuario en voz alta.

    Usar cuando el usuario pide "leé", "léelo", "qué dice", "revisá el contenido", o nombra un
    archivo de texto esperando conocer su contenido (no solo verlo en pantalla).
    Si solo dan el nombre, buscar primero la ruta con search_files."""

    res = file_manager.read_file_content(file_path)

    _remember_file(file_path)

    # B-4: accesos defensivos con .get() (un dict incompleto no debe reventar con
    # KeyError). El tamaño ya viene limitado a 3000 caracteres por file_manager
    # (max_chars), así que un log gigante no revienta el contexto.
    if res.get("status") == "success":

        filename = res.get("filename", file_path)

        content = res.get("content", "")

        tail = " (mostrando el principio, el archivo es más largo)" if res.get("truncated") else ""

        return f"Contenido de {filename}{tail}:\n{content}"

    return res.get("message", "No se pudo leer el archivo.")


# --- CREACIÓN Y GESTIÓN DE ARCHIVOS ---
def create_file(filename: str, content: str = "", folder: str = "Desktop") -> str:

    """Crea un archivo nuevo con el contenido indicado en el Escritorio o Descargas."""

    from brain.local_intents import local_intents
    # S-6: pide confirmación solo si el archivo ya existe (se va a pisar).
    if file_manager.resolve_create_target(filename, folder).exists():
        return local_intents.request_confirmation(
            "create_file", filename=filename, content=content, folder=folder
        )
    res = file_manager.create_file(filename=filename, content=content, folder=folder)

    return res.get("message", str(res))


def append_to_file(filename: str, content: str) -> str:

    """Agrega texto al final de un archivo existente en el Escritorio o Documentos."""

    from brain.local_intents import local_intents
    # S-6: modifica datos existentes -> siempre pide confirmación.
    return local_intents.request_confirmation(
        "append_to_file", filename=filename, content=content
    )


def extract_zip(zip_name_or_path: str, destination: str = "") -> str:

    """Descomprime un archivo .zip en una carpeta con el mismo nombre o la carpeta indicada."""

    res = file_manager.extract_zip(zip_name_or_path=zip_name_or_path, destination=destination)

    return res.get("message", str(res))


def organize_folder(folder_name: str = "Downloads") -> str:

    """Organiza automáticamente una carpeta (por defecto Descargas o Escritorio), clasificando archivos en subcarpetas por tipo."""

    from brain.local_intents import local_intents
    # S-6: mueve muchos archivos de una -> siempre pide confirmación.
    return local_intents.request_confirmation("organize_folder", folder_name=folder_name)
