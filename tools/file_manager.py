import os
import time
import shutil
import subprocess
from core.process_utils import run_silent
from pathlib import Path
from typing import List, Dict, Any, Optional
import send2trash
import zipfile
from core.config import config
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState
from core.path_security import safe_zip_member_path

# Directorios a omitir durante búsquedas profundas para mayor velocidad
IGNORED_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "appdata", "$recycle.bin", "system volume information", "windows"
}

class FileManager:
    def _remote_exec_if_linux(self, action: str, args: dict, success_msg: str) -> Optional[Dict[str, Any]]:
        """Si corre en Linux (servidor DDR3), delega la acción al satélite Windows conectado vía WebSocket RPC bidireccional."""
        if os.name != 'nt':
            try:
                from server.websocket_hub import ws_hub
                if ws_hub.has_windows_satellite():
                    loop = getattr(state_mgr, "_loop", None)
                    if loop and loop.is_running():
                        import asyncio
                        fut = asyncio.run_coroutine_threadsafe(
                            ws_hub.call_remote(action, args, timeout=10.0), loop
                        )
                        try:
                            result = fut.result(timeout=11.0)
                            msg = result.get("message", success_msg)
                            state_mgr.emit_tool_call(action, args, msg)
                            return result
                        except Exception as e:
                            log_warning(f"[RPC] Error esperando respuesta del satélite para '{action}': {e}")
                            error_msg = f"El satélite Windows no confirmó la operación '{action}'."
                            state_mgr.emit_tool_call(action, args, error_msg)
                            return {"status": "timeout", "message": error_msg}
                    else:
                        state_mgr._notify({
                            "type": "remote_exec",
                            "action": action,
                            "args": args
                        })
                        state_mgr.emit_tool_call(action, args, success_msg)
                        return {"status": "success", "message": success_msg}
                else:
                    return {
                        "status": "warning",
                        "message": "Che, no detecto la compu principal conectada para operar con archivos de Windows. Asegurate de tener el satélite de Titán corriendo."
                    }
            except Exception as e:
                log_warning(f"Error delegando acción remota {action}: {e}")
        return None

    def search_files(self, query: str, extension: Optional[str] = None, location: Optional[str] = None, max_results: int = 10) -> Dict[str, Any]:
        """Busca archivos por nombre o extensión en las carpetas y discos configurados"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "search_files",
                {"query": query, "extension": extension, "location": location, "max_results": max_results},
                f"Buscando archivos para '{query}' en Windows..."
            )
            if remote_res:
                return remote_res

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Buscando archivos con '{query}'...")
        log_info(f"Iniciando búsqueda de archivos: query='{query}', extension='{extension}'")

        targets = []
        if location and os.path.exists(location):
            targets.append(Path(location))
        else:
            for p in config.search_folders:
                path_obj = Path(p)
                if path_obj.exists():
                    targets.append(path_obj)

        results: List[Dict[str, Any]] = []
        q_lower = query.lower().strip()
        ext_clean = f".{extension.lower().lstrip('.')}" if extension else None

        start_search_time = time.time()
        for root_dir in targets:
            if len(results) >= max_results or (time.time() - start_search_time) > 3.5:
                break
            try:
                p_root = Path(root_dir)
                root_parts_len = len(p_root.parts)
                # Discos enteros como D:\ o E:\ se limitan a 3 niveles para no colgarse
                is_full_drive = len(p_root.parts) <= 1 or str(root_dir).endswith(":\\") or str(root_dir).endswith(":/")
                max_allowed_depth = 3 if is_full_drive else 5

                for root, dirs, files in os.walk(root_dir):
                    if (time.time() - start_search_time) > 3.5:
                        break

                    # Limitar profundidad
                    current_depth = len(Path(root).parts) - root_parts_len
                    if current_depth >= max_allowed_depth:
                        dirs[:] = []
                        continue

                    # Filtrar carpetas ignoradas para que no tarde una eternidad
                    dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and not d.startswith(".")]

                    for f in files:
                        f_lower = f.lower()
                        # Comprobar extensión si se especificó
                        if ext_clean and not f_lower.endswith(ext_clean):
                            continue
                        # Comprobar nombre
                        if q_lower in f_lower or not q_lower:
                            full_path = Path(root) / f
                            try:
                                stat = full_path.stat()
                                results.append({
                                    "name": f,
                                    "path": str(full_path),
                                    "size_kb": round(stat.st_size / 1024, 1),
                                    "modified": stat.st_mtime
                                })
                            except Exception:
                                results.append({"name": f, "path": str(full_path)})

                            if len(results) >= max_results:
                                break
                    if len(results) >= max_results:
                        break
            except Exception as e:
                log_warning(f"No se pudo buscar en {root_dir}: {e}")

        msg = f"Encontré {len(results)} archivo(s) para '{query}'."
        state_mgr.emit_tool_call("search_files", {"query": query, "ext": extension}, msg)
        return {"status": "success", "count": len(results), "files": results}

    def open_file(self, file_path: str) -> Dict[str, Any]:
        """Abre un archivo con el programa predeterminado de Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "open_file",
                {"file_path": file_path},
                f"Abriendo '{file_path}' en la compu..."
            )
            if remote_res:
                return remote_res

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Abriendo archivo...")
        p = Path(file_path)
        if not p.exists():
            msg = f"El archivo '{file_path}' no existe, che."
            state_mgr.emit_tool_call("open_file", {"file_path": file_path}, msg)
            return {"status": "error", "message": msg}

        try:
            os.startfile(str(p.resolve()))
            msg = f"Te abrí '{p.name}' al toque."
            state_mgr.emit_tool_call("open_file", {"file_path": file_path}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            err_msg = f"Error abriendo '{p.name}': {e}"
            log_error(err_msg)
            return {"status": "error", "message": err_msg}

    def show_in_folder(self, file_path: str) -> Dict[str, Any]:
        """Abre el explorador de Windows seleccionando el archivo indicado"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "show_in_folder",
                {"file_path": file_path},
                f"Mostrando '{file_path}' en el explorador de Windows..."
            )
            if remote_res:
                return remote_res

        p = Path(file_path)
        if not p.exists():
            return {"status": "error", "message": f"La ruta '{file_path}' no existe."}

        try:
            run_silent(["explorer", f"/select,{str(p.resolve())}"], check=False)
            msg = f"Te mostré '{p.name}' en la carpeta."
            state_mgr.emit_tool_call("show_in_folder", {"file_path": file_path}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def trash_file(self, file_path: str) -> Dict[str, Any]:
        """Envía el archivo a la papelera de reciclaje de Windows de forma segura"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "trash_file",
                {"file_path": file_path},
                f"Mandando '{file_path}' a la papelera de reciclaje en Windows..."
            )
            if remote_res:
                return remote_res

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Enviando archivo a la papelera...")
        p = Path(file_path)
        if not p.exists():
            return {"status": "error", "message": f"El archivo '{file_path}' no existe."}

        try:
            send2trash.send2trash(str(p.resolve()))
            msg = f"Mandé '{p.name}' a la papelera de reciclaje seguro. Si te arrepentís, lo podés restaurar."
            state_mgr.emit_tool_call("trash_file", {"file_path": file_path}, msg)
            return {"status": "success", "message": msg}
        except Exception as e:
            err_msg = f"No pude mandar el archivo a la papelera: {e}"
            log_error(err_msg)
            return {"status": "error", "message": err_msg}


    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Mueve un archivo o carpeta a otra ubicación"""
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            return {"status": "error", "message": f"El archivo origen '{source}' no existe."}

        try:
            # Si destination es una carpeta existente, mover adentro
            target = shutil.move(str(src), str(dst))
            msg = f"Moví '{src.name}' a '{target}' al toque."
            state_mgr.emit_tool_call("move_file", {"src": source, "dst": destination}, msg)
            return {"status": "success", "message": msg, "target": target}
        except Exception as e:
            return {"status": "error", "message": f"Error moviendo archivo: {e}"}

    def copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Copia un archivo a otra ubicación"""
        src = Path(source)
        dst = Path(destination)
        if not src.exists():
            return {"status": "error", "message": f"El archivo origen '{source}' no existe."}

        try:
            target = shutil.copy2(str(src), str(dst))
            msg = f"Copié '{src.name}' a '{target}' al pie."
            state_mgr.emit_tool_call("copy_file", {"src": source, "dst": destination}, msg)
            return {"status": "success", "message": msg, "target": target}
        except Exception as e:
            return {"status": "error", "message": f"Error copiando archivo: {e}"}

    def read_file_content(self, file_path: str, max_chars: int = 3000) -> Dict[str, Any]:
        """Lee el contenido de un archivo de texto, código, markdown, csv, json"""
        p = Path(file_path)
        if not p.exists():
            return {"status": "error", "message": f"No encuentro el archivo '{file_path}'."}

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)
            
            truncated = p.stat().st_size > len(content)
            msg = f"Leí '{p.name}' ({len(content)} caracteres)."
            state_mgr.emit_tool_call("read_file", {"file_path": file_path}, msg)
            return {
                "status": "success",
                "filename": p.name,
                "content": content,
                "truncated": truncated
            }
        except Exception as e:
            return {"status": "error", "message": f"No pude leer el contenido del archivo: {e}"}

    def _resolve_folder(self, folder_name: str) -> Path:
        f_lower = folder_name.strip().lower()
        user_home = Path.home()
        if f_lower in ["desktop", "escritorio"]:
            return user_home / "Desktop"
        elif f_lower in ["downloads", "descargas"]:
            return user_home / "Downloads"
        elif f_lower in ["documents", "documentos"]:
            return user_home / "Documents"
        elif f_lower in ["music", "musica", "música"]:
            return user_home / "Music"
        elif f_lower in ["pictures", "fotos", "imagenes", "imágenes"]:
            return user_home / "Pictures"
        elif f_lower in ["videos", "vídeos"]:
            return user_home / "Videos"

        target = Path(folder_name)
        if target.is_absolute():
            return target
        return user_home / folder_name

    def create_file(self, filename: str, content: str = "", folder: str = "Desktop") -> Dict[str, Any]:
        """Crea un archivo nuevo con el contenido dado en la carpeta indicada (por defecto Escritorio)"""
        try:
            p_file = Path(filename)
            if p_file.is_absolute():
                target_path = p_file
            else:
                base_dir = self._resolve_folder(folder)
                base_dir.mkdir(parents=True, exist_ok=True)
                target_path = base_dir / filename

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            msg = f"Creé el archivo '{target_path.name}' en {target_path.parent.name} joya."
            state_mgr.emit_tool_call("create_file", {"filename": filename, "folder": folder}, msg)
            return {"status": "success", "message": msg, "path": str(target_path)}
        except Exception as e:
            return {"status": "error", "message": f"Error creando el archivo: {e}"}

    def append_to_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Agrega texto al final de un archivo existente"""
        try:
            p_file = Path(filename)
            target_path = None
            if p_file.is_absolute() and p_file.exists():
                target_path = p_file
            else:
                for folder in ["Desktop", "Downloads", "Documents"]:
                    cand = Path.home() / folder / filename
                    if cand.exists():
                        target_path = cand
                        break
                if not target_path and p_file.exists():
                    target_path = p_file

            if not target_path or not target_path.exists():
                return {"status": "error", "message": f"No encontré el archivo '{filename}' para agregar contenido."}

            with open(target_path, "a", encoding="utf-8") as f:
                f.write("\n" + content if target_path.stat().st_size > 0 else content)

            msg = f"Le agregué el contenido a '{target_path.name}' de diez."
            state_mgr.emit_tool_call("append_to_file", {"filename": filename}, msg)
            return {"status": "success", "message": msg, "path": str(target_path)}
        except Exception as e:
            return {"status": "error", "message": f"Error escribiendo en el archivo: {e}"}

    def extract_zip(self, zip_name_or_path: str, destination: str = "") -> Dict[str, Any]:
        """Descomprime un archivo .zip en la carpeta de destino o en una subcarpeta automática"""
        try:
            p_zip = Path(zip_name_or_path)
            target_zip = None
            if p_zip.is_absolute() and p_zip.exists():
                target_zip = p_zip
            else:
                for folder in ["Downloads", "Desktop", "Documents"]:
                    cand = Path.home() / folder / zip_name_or_path
                    if cand.exists():
                        target_zip = cand
                        break
                    if not zip_name_or_path.lower().endswith(".zip"):
                        cand_zip = Path.home() / folder / f"{zip_name_or_path}.zip"
                        if cand_zip.exists():
                            target_zip = cand_zip
                            break

            if not target_zip or not target_zip.exists():
                return {"status": "error", "message": f"No encontré el archivo zip '{zip_name_or_path}'."}

            if destination:
                dest_dir = self._resolve_folder(destination)
            else:
                dest_dir = target_zip.parent / target_zip.stem

            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_zip, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    try:
                        safe_zip_member_path(dest_dir, member.filename)
                    except ValueError:
                        return {
                            "status": "error",
                            "message": f"El ZIP contiene una ruta insegura y no se extrajo: {member.filename}"
                        }
                zip_ref.extractall(dest_dir)
                file_list = zip_ref.namelist()

            msg = f"Descomprimí '{target_zip.name}' con éxito ({len(file_list)} archivos extraídos en '{dest_dir.name}')."
            state_mgr.emit_tool_call("extract_zip", {"zip": target_zip.name, "dest": str(dest_dir)}, msg)
            return {"status": "success", "message": msg, "destination": str(dest_dir), "count": len(file_list)}
        except Exception as e:
            return {"status": "error", "message": f"Error descomprimiendo el archivo: {e}"}

    def organize_folder(self, folder_name: str = "Downloads") -> Dict[str, Any]:
        """Organiza automáticamente los archivos de una carpeta (por defecto Descargas) en subcarpetas por categoría"""
        try:
            target_dir = self._resolve_folder(folder_name)
            if not target_dir.exists() or not target_dir.is_dir():
                return {"status": "error", "message": f"La carpeta '{folder_name}' no existe o no es un directorio válido."}

            CATEGORIES = {
                "Imágenes": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"},
                "Documentos": {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".md", ".epub"},
                "Instaladores": {".exe", ".msi", ".iso"},
                "Comprimidos": {".zip", ".rar", ".7z", ".tar", ".gz"},
                "Música": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
                "Videos": {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"},
                "Código": {".py", ".js", ".ts", ".html", ".css", ".json", ".cpp", ".c", ".rs", ".java", ".sql"}
            }

            EXT_MAP = {}
            for cat, exts in CATEGORIES.items():
                for ext in exts:
                    EXT_MAP[ext] = cat

            moved_counts = {}
            total_moved = 0

            for item in list(target_dir.iterdir()):
                if not item.is_file():
                    continue

                ext = item.suffix.lower()
                if ext in [".crdownload", ".part", ".tmp"] or item.name.startswith("~$") or item.name.startswith("."):
                    continue
                if target_dir.name.lower() in ["desktop", "escritorio"] and ext == ".lnk":
                    continue

                cat = EXT_MAP.get(ext, "Otros")
                cat_dir = target_dir / cat
                cat_dir.mkdir(parents=True, exist_ok=True)

                dest_file = cat_dir / item.name
                if dest_file.exists():
                    timestamp = int(time.time())
                    dest_file = cat_dir / f"{item.stem}_{timestamp}{item.suffix}"

                shutil.move(str(item), str(dest_file))
                moved_counts[cat] = moved_counts.get(cat, 0) + 1
                total_moved += 1

            if total_moved == 0:
                msg = f"La carpeta '{target_dir.name}' ya está limpia y ordenada, no había archivos sueltos para mover."
            else:
                detalles = ", ".join([f"{count} en {cat}" for cat, count in moved_counts.items()])
                msg = f"¡Listo, che! Ordené {total_moved} archivos en '{target_dir.name}': {detalles}."

            state_mgr.emit_tool_call("organize_folder", {"folder": target_dir.name, "total_moved": total_moved}, msg)
            return {"status": "success", "message": msg, "total_moved": total_moved, "details": moved_counts}
        except Exception as e:
            return {"status": "error", "message": f"Error organizando la carpeta: {e}"}

file_manager = FileManager()
