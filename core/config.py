import os
import json
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde .env
_env_path = BASE_DIR / ".env"
load_dotenv(_env_path)
# S-14: el .env guarda la API key; si quedó legible para otros usuarios
# del sistema, se ajusta a 600 en cada arranque.
try:
    if _env_path.exists():
        _mode = _env_path.stat().st_mode & 0o777
        if _mode & 0o077:
            os.chmod(_env_path, 0o600)
            print(f"[Seguridad] Permisos de .env ajustados a 600 (estaban en {oct(_mode)}).")
except Exception:
    pass

class Config:
    def __init__(self):
        self.base_dir: Path = BASE_DIR
        self.config_path: Path = BASE_DIR / "config.json"
        self.apps_catalog_path: Path = BASE_DIR / "apps_catalog.json"
        
        # Variables de entorno
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
        self.server_host: str = os.getenv("SERVER_HOST", "0.0.0.0").strip()
        self.server_port: int = int(os.getenv("SERVER_PORT", "8000").strip())
        # S-11: puerto solo-TLS para el canal del satélite (wss://). El 8000
        # queda intacto para HUD/navegadores.
        self.satellite_tls_port: int = int(os.getenv("SATELLITE_TLS_PORT", "8443").strip())
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_allowed_user_id: str = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
        self.hf_token: str = os.getenv("HF_TOKEN", "").strip()
        
        # Cargar configuración persistente JSON
        self.settings: Dict[str, Any] = self._load_json(self.config_path, {
            "tts": {
                "voice": "es-AR-TomasNeural",
                "rate": "+5%",
                "pitch": "+0Hz",
                "volume": "+0%"
            },
            "asistente": {
                "nombre": "Che Asistente",
                "idioma": "es-AR",
                "palabras_clave": ["che asistente", "asistente", "che gemini", "escuchame", "che amigo"]
            },
            "hotkey": {
                "activacion": "ctrl+space",
                "activacion_alternativa": "alt+a"
            },
            "carpetas_busqueda": [
                str(Path.home() / "Desktop"),
                str(Path.home() / "Documents"),
                str(Path.home() / "Downloads"),
                "D:\\",
                "E:\\"
            ]
        })
        
        # Cargar catálogo de apps
        self.catalog_data: Dict[str, Any] = self._load_json(self.apps_catalog_path, {
            "apps": {
                "inkscape": "E:\\Programas\\Inkscape\\bin\\inkscape.exe",
                "bloc de notas": "notepad.exe",
                "calculadora": "calc.exe"
            },
            "carpetas_escaneo_portable": ["E:\\Programas", "C:\\Portables", "D:\\Portables"]
        })

    def _load_json(self, path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error cargando {path.name}: {e}")
        return default

    def save_settings(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config.json: {e}")

    def save_apps_catalog(self):
        try:
            with open(self.apps_catalog_path, "w", encoding="utf-8") as f:
                json.dump(self.catalog_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando apps_catalog.json: {e}")

    def set_telegram_allowed_user_id(self, user_id: str):
        import re
        self.telegram_allowed_user_id = str(user_id).strip()
        env_path = BASE_DIR / ".env"
        try:
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                if "TELEGRAM_ALLOWED_USER_ID=" in content:
                    content = re.sub(r'TELEGRAM_ALLOWED_USER_ID=.*', f'TELEGRAM_ALLOWED_USER_ID={self.telegram_allowed_user_id}', content)
                else:
                    content += f"\nTELEGRAM_ALLOWED_USER_ID={self.telegram_allowed_user_id}\n"
                env_path.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"Error guardando TELEGRAM_ALLOWED_USER_ID: {e}")

    @property
    def tts_voice(self) -> str:
        return self.settings.get("tts", {}).get("voice", "es-AR-TomasNeural")

    @property
    def tts_rate(self) -> str:
        return self.settings.get("tts", {}).get("rate", "+5%")

    @property
    def tts_pitch(self) -> str:
        return self.settings.get("tts", {}).get("pitch", "+0Hz")

    @property
    def tts_volume(self) -> str:
        return self.settings.get("tts", {}).get("volume", "+0%")

    @property
    def assistant_name(self) -> str:
        return self.settings.get("asistente", {}).get("nombre", "Titán")

    def set_assistant_name(self, new_name: str) -> str:
        clean = new_name.strip()
        if not clean:
            return self.assistant_name
        if "asistente" not in self.settings:
            self.settings["asistente"] = {}
        self.settings["asistente"]["nombre"] = clean
        kws = self.settings["asistente"].setdefault("palabras_clave", [])
        lower = clean.lower()
        if lower not in kws:
            kws.insert(0, lower)
            kws.insert(1, f"che {lower}")
        self.save_settings()
        return clean

    @property
    def default_music_player(self) -> str:
        return self.settings.get("reproductor_musica", "spotify")

    def set_default_music_player(self, player: str) -> str:
        target = "spotify" if "spot" in player.lower() else "youtube"
        self.settings["reproductor_musica"] = target
        self.save_settings()
        return target

    @property
    def wake_words(self) -> List[str]:
        return self.settings.get("asistente", {}).get("palabras_clave", ["titán", "titan", "che titán", "asistente"])

    @property
    def hotkey(self) -> str:
        return self.settings.get("hotkey", {}).get("activacion", "ctrl+space")

    @property
    def search_folders(self) -> List[str]:
        return self.settings.get("carpetas_busqueda", [])

    @property
    def portable_apps(self) -> Dict[str, str]:
        return self.catalog_data.get("apps", {})

    @property
    def portable_folders(self) -> List[str]:
        return self.catalog_data.get("carpetas_escaneo_portable", [])

# Instancia global única
config = Config()
