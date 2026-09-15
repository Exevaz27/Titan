import os
import subprocess
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from core.config import config
from core.logger import log_info, log_error, log_warning
from core.state_manager import state_mgr, AssistantState
from core.process_utils import popen_silent

# Rutas estándar del menú inicio de Windows
START_MENU_PATHS = [
    Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
]

SAFE_SYSTEM_APPS = {
    "notepad": "notepad.exe",
    "bloc de notas": "notepad.exe",
    "calc": "calc.exe",
    "calculadora": "calc.exe",
    "mspaint": "mspaint.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
}

class AppLauncher:
    def __init__(self):
        self._cached_apps: Dict[str, str] = {}
        self.refresh_cache()

    def refresh_cache(self):
        """Indexa aplicaciones del catálogo y accesos directos de Windows"""
        self._cached_apps = {}

        # 1. Cargar desde apps_catalog.json (máxima prioridad)
        catalog_apps = config.portable_apps
        for alias, path in catalog_apps.items():
            self._cached_apps[alias.lower().strip()] = path

        # 2. Escanear accesos directos (.lnk) del Menú Inicio
        for menu_path in START_MENU_PATHS:
            if menu_path.exists():
                for lnk in menu_path.rglob("*.lnk"):
                    name = lnk.stem.lower().strip()
                    if name not in self._cached_apps:
                        self._cached_apps[name] = str(lnk)

        # 3. Escanear carpetas de portables configuradas (nivel 1, nivel 2 y bin para que sea instantáneo)
        for folder_str in config.portable_folders:
            folder = Path(folder_str)
            if folder.exists() and folder.is_dir():
                try:
                    # Nivel 1: ejecutables en la raíz de la carpeta
                    for exe in folder.glob("*.exe"):
                        name = exe.stem.lower().strip()
                        if name not in self._cached_apps:
                            self._cached_apps[name] = str(exe)
                    # Nivel 2: subcarpetas inmediatas y sus carpetas /bin
                    for sub in folder.iterdir():
                        if sub.is_dir() and not sub.name.startswith(".") and sub.name.lower() not in ["node_modules", "windows"]:
                            for exe in sub.glob("*.exe"):
                                name = exe.stem.lower().strip()
                                if name not in self._cached_apps:
                                    self._cached_apps[name] = str(exe)
                            bin_dir = sub / "bin"
                            if bin_dir.is_dir():
                                for exe in bin_dir.glob("*.exe"):
                                    name = exe.stem.lower().strip()
                                    if name not in self._cached_apps:
                                        self._cached_apps[name] = str(exe)
                except Exception as e:
                    log_warning(f"Error escaneando carpeta portable {folder_str}: {e}")

        log_info(f"Índice de aplicaciones actualizado ({len(self._cached_apps)} programas detectados)")

    def find_app(self, query: str) -> Optional[Tuple[str, str]]:
        """Busca una app por nombre exacto o aproximado. Retorna (nombre, ruta)"""
        q = query.lower().strip()

        # Coincidencia exacta
        if q in self._cached_apps:
            return q, self._cached_apps[q]

        # Coincidencia parcial (subcadena)
        for name, path in self._cached_apps.items():
            if q in name or name in q:
                return name, path

        # Coincidencia difusa
        matches = difflib.get_close_matches(q, list(self._cached_apps.keys()), n=1, cutoff=0.5)
        if matches:
            best = matches[0]
            return best, self._cached_apps[best]

        return None

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Abre una aplicación por nombre"""
        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Abriendo {app_name}...")
        log_info(f"Intentando abrir aplicación: '{app_name}'")

        match = self.find_app(app_name)
        if match:
            matched_name, path = match
            try:
                if matched_name == "spotify":
                    from tools.system_control import system_control
                    return system_control.play_spotify("")
                elif os.path.exists(path):
                    os.startfile(path)
                else:
                    # Un catálogo obsoleto no debe convertirse en un comando de shell.
                    return {
                        "status": "not_found",
                        "message": f"La ruta configurada para '{matched_name}' ya no existe: {path}"
                    }
                
                msg = f"Ahí te abrí {matched_name}, papá."
                state_mgr.emit_tool_call("launch_app", {"app_name": app_name}, msg)
                return {"status": "success", "message": msg, "path": path}
            except Exception as e:
                err_msg = f"Hubo un bardo al abrir {matched_name}: {e}"
                log_error(err_msg)
                state_mgr.emit_tool_call("launch_app", {"app_name": app_name}, err_msg)
                return {"status": "error", "message": err_msg}

        # Sólo se permiten alias explícitos de aplicaciones del sistema.
        safe_command = SAFE_SYSTEM_APPS.get(app_name.lower().strip())
        if safe_command:
            try:
                popen_silent([safe_command])
                msg = f"Mandé a ejecutar '{app_name}' directamente."
                state_mgr.emit_tool_call("launch_app", {"app_name": app_name}, msg)
                return {"status": "success", "message": msg, "path": safe_command}
            except Exception as e:
                log_error(f"Error ejecutando aplicación del sistema '{app_name}': {e}")

        err_msg = f"No encontré ninguna app segura que se llame '{app_name}' en tus discos ni en Windows."
        log_warning(err_msg)
        state_mgr.emit_tool_call("launch_app", {"app_name": app_name}, err_msg)
        return {"status": "not_found", "message": err_msg}

    # Alias compatible
    launch = launch_app

    def register_portable_app(self, alias: str, file_path: str) -> Dict[str, Any]:
        """Agrega un ejecutable al archivo apps_catalog.json"""
        path_obj = Path(file_path)
        if not path_obj.exists():
            return {"status": "error", "message": f"La ruta '{file_path}' no existe en la compu."}

        alias_clean = alias.lower().strip()
        config.catalog_data.setdefault("apps", {})[alias_clean] = str(path_obj.resolve())
        config.save_apps_catalog()
        self.refresh_cache()

        msg = f"Agendé '{alias_clean}' apuntando a '{file_path}' en tu catálogo."
        state_mgr.emit_tool_call("register_portable_app", {"alias": alias, "path": file_path}, msg)
        return {"status": "success", "message": msg}

    def list_catalog_apps(self) -> Dict[str, str]:
        return config.portable_apps

app_launcher = AppLauncher()
