import os
import shutil
import subprocess
import time
import re
import shlex
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
from core.logger import log_info, log_error, log_warning
from core.reply_variants import pick as reply_pick


def _strip_accents(text: str) -> str:
    """Normaliza un texto quitando tildes, diéresis y la virgulilla de la ñ.

    B-30: antes se reemplazaban a mano solo áéíóú y la ñ quedaba intacta,
    así "niños" no matcheaba "ninos". Con NFKD la ñ se descompone en
    n + tilde combinante y al filtrar las marcas se obtiene "n".
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if unicodedata.category(c) != "Mn"
    )


# S-1: los package names Android tienen un formato estricto. Cualquier
# candidato que no lo cumpla (ej. "a.b;reboot") se descarta antes de
# armar el comando monkey, como defensa en profundidad además del
# citado de argumentos en _run_shell.
_PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")

# Configuración por defecto de la tele BGH Android TV
DEFAULT_TV_IP = "192.168.100.8"
DEFAULT_TV_PORT = 5555

# Mapeo de nombres comunes a paquetes de Android TV
APP_PACKAGES = {
    "onplay": "ar.com.onplay.tv",
    "on play": "ar.com.onplay.tv",
    "onplay tv": "ar.com.onplay.tv",
    "smarttube": "org.smarttube.stable",
    "smart tube": "org.smarttube.stable",
    "youtube sin anuncios": "org.smarttube.stable",
    "youtube": "org.smarttube.stable",
    "youtube oficial": "com.google.android.youtube.tv",
    "youtube music": "com.google.android.youtube.tvmusic",
    "netflix": "com.netflix.ninja",
    "vlc": "org.videolan.vlc",
    "cloudstream": "com.lagradost.cloudstream3.prereleasf",
    "cloud stream": "com.lagradost.cloudstream3.prereleasf",
    "ottplay": "com.ottplay.ottplay",
    "punto play": "com.example.puntoplaypremium",
    "puntoplay": "com.example.puntoplaypremium",
    "spotify": "com.spotify.tv.android",
    "flow": "ar.telecom.flow.tv",
    "disney": "com.disney.disneyplus",
    "disney plus": "com.disney.disneyplus",
    "prime video": "com.amazon.amazonvideo.livingroom",
    "prime": "com.amazon.amazonvideo.livingroom",
    "max": "com.wbd.stream",
    "hbo": "com.wbd.stream",
    "twitch": "tv.twitch.android.app",
    "pluto": "tv.pluto.android",
    "pluto tv": "tv.pluto.android",
    "proton vpn": "ch.protonvpn.android",
    "localsend": "org.localsend.localsend_app"
}

# Teclas mapeadas a Keycodes de Android
KEY_CODES = {
    "arriba": 19,      # KEYCODE_DPAD_UP
    "up": 19,
    "abajo": 20,       # KEYCODE_DPAD_DOWN
    "down": 20,
    "izquierda": 21,   # KEYCODE_DPAD_LEFT
    "left": 21,
    "derecha": 22,     # KEYCODE_DPAD_RIGHT
    "right": 22,
    "ok": 66,          # KEYCODE_ENTER
    "enter": 66,
    "seleccionar": 66,
    "atras": 4,        # KEYCODE_BACK
    "atrás": 4,
    "back": 4,
    "inicio": 3,       # KEYCODE_HOME
    "home": 3,
    "menu": 82,        # KEYCODE_MENU
    "menú": 82,
    "play": 126,       # KEYCODE_MEDIA_PLAY
    "pausa": 127,      # KEYCODE_MEDIA_PAUSE
    "play_pause": 85,  # KEYCODE_MEDIA_PLAY_PAUSE
    "stop": 86,        # KEYCODE_MEDIA_STOP
    "next": 87,        # KEYCODE_MEDIA_NEXT
    "prev": 88,        # KEYCODE_MEDIA_PREVIOUS
    "power": 26,       # KEYCODE_POWER
    "wake": 224,       # KEYCODE_WAKEUP
    "sleep": 223,      # KEYCODE_SLEEP
    "mute": 164,       # KEYCODE_VOLUME_MUTE
    "vol_up": 24,      # KEYCODE_VOLUME_UP
    "vol_down": 25     # KEYCODE_VOLUME_DOWN
}

# Entradas HDMI reales de la BGH (MediaTek), descubiertas vía dumpsys tv_input:
# HW4 = puerto HDMI 1, HW5 = puerto HDMI 2. La tele solo tiene 2 HDMI.
HDMI_INPUT_IDS = {
    1: "com.mediatek.tvinput/.hdmi.HDMIInputService/HW4",
    2: "com.mediatek.tvinput/.hdmi.HDMIInputService/HW5",
}

# Catálogo completo de 97 canales de OnPlay extraído de ClayTVv2.m3u
ONPLAY_CHANNELS: Dict[int, Tuple[str, str]] = {
    1: ("América TV HD", "Aire y Noticias"),
    2: ("TV Pública HD", "Aire y Noticias"),
    3: ("Canal 9 HD", "Aire y Noticias"),
    4: ("Telefe", "Aire y Noticias"),
    5: ("Canal 13 HD", "Aire y Noticias"),
    6: ("TN", "Aire y Noticias"),
    7: ("C5N", "Aire y Noticias"),
    8: ("Crónica TV", "Aire y Noticias"),
    9: ("A24", "Aire y Noticias"),
    10: ("La Nación HD", "Aire y Noticias"),
    11: ("26 TV", "Aire y Noticias"),
    12: ("NET TV", "Aire y Noticias"),
    13: ("Argentina 12", "Aire y Noticias"),
    14: ("Canal de la Ciudad", "Aire y Noticias"),
    15: ("ESPN Premium HD", "Deportes"),
    16: ("TNT Sports HD", "Deportes"),
    17: ("TyC Sports HD", "Deportes"),
    18: ("ESPN HD", "Deportes"),
    19: ("ESPN 2 HD", "Deportes"),
    20: ("ESPN 3 HD", "Deportes"),
    21: ("Fox Sports HD", "Deportes"),
    22: ("Fox Sports 2 HD", "Deportes"),
    23: ("Fox Sports 3 HD", "Deportes"),
    24: ("DXTV", "Deportes"),
    25: ("América Sports", "Deportes"),
    26: ("El Garage", "Deportes"),
    27: ("ESPN 4 HD", "Deportes"),
    28: ("Cartoon Network", "Infantiles"),
    29: ("Nickelodeon", "Infantiles"),
    30: ("Discovery Kids", "Infantiles"),
    31: ("Disney Channel HD", "Infantiles"),
    32: ("Disney Jr", "Infantiles"),
    33: ("Paka Paka", "Infantiles"),
    34: ("HTV", "Música y Variedades"),
    35: ("MTV", "Música y Variedades"),
    36: ("Quiero Música", "Música y Variedades"),
    37: ("Canal a", "Música y Variedades"),
    38: ("KZO", "Música y Variedades"),
    39: ("Metro HD", "Música y Variedades"),
    40: ("Canal Rural", "Música y Variedades"),
    41: ("RAI", "Internacionales"),
    42: ("Bravo", "Variedades"),
    43: ("Somos", "Variedades"),
    44: ("TVE", "Internacionales"),
    45: ("HBO", "Cine y Series"),
    46: ("HBO Signature", "Cine y Series"),
    47: ("HBO Xtreme", "Cine y Series"),
    48: ("Star Channel", "Cine y Series"),
    49: ("TNT HD", "Cine y Series"),
    50: ("TNT Series", "Cine y Series"),
    51: ("TNT Novelas", "Cine y Series"),
    52: ("Sony", "Cine y Series"),
    53: ("AXN", "Cine y Series"),
    54: ("Warner Channel", "Cine y Series"),
    55: ("FX", "Cine y Series"),
    56: ("Cinecanal", "Cine y Series"),
    57: ("Cinemax", "Cine y Series"),
    58: ("Cine AR", "Cine y Series"),
    59: ("Space", "Cine y Series"),
    60: ("TCM", "Cine y Series"),
    61: ("Studio Universal", "Cine y Series"),
    62: ("AMC", "Cine y Series"),
    63: ("A&E", "Cine y Series"),
    64: ("Film and Arts", "Cine y Series"),
    65: ("Volver", "Cine y Series"),
    66: ("Telemundo HD", "Cine y Series"),
    67: ("Discovery HD", "Documentales"),
    68: ("Discovery Theater HD", "Documentales"),
    69: ("Discovery World HD", "Documentales"),
    70: ("Discovery Science", "Documentales"),
    71: ("Discovery Home and Health", "Documentales"),
    72: ("Discovery ID", "Documentales"),
    73: ("National Geographic", "Documentales"),
    74: ("History HD", "Documentales"),
    75: ("History 2", "Documentales"),
    76: ("Encuentro", "Documentales"),
    77: ("Animal Planet", "Documentales"),
    78: ("El Gourmet", "Documentales"),
    79: ("Ciudad Magazine", "Variedades"),
    80: ("MIX TV", "Variedades"),
    81: ("Lifetime", "Cine y Series"),
    82: ("E! Entertainment", "Variedades"),
    83: ("CNN Español", "Noticias"),
    84: ("Comedy Central HD", "Entretenimiento"),
    85: ("Universal Channel HD", "Cine y Series"),
    86: ("DSports", "Deportes"),
    87: ("DSports 2", "Deportes"),
    88: ("Tigo Sports", "Deportes"),
    89: ("Tigo Sports +", "Deportes"),
    90: ("SNT", "Internacionales"),
    91: ("Telefuturo", "Internacionales"),
    92: ("La Tele", "Internacionales"),
    93: ("C9N", "Internacionales"),
    94: ("Canal 13 (Py)", "Internacionales"),
    95: ("Pasiones", "Cine y Series"),
    96: ("Telenovelas", "Cine y Series"),
    97: ("Allegro", "Música y Variedades")
}

# Aliases y modismos argentinos para canales
CHANNEL_ALIASES: Dict[str, int] = {
    "espn premium": 15,
    "espn premiun": 15,
    "pack futbol": 15,
    "el pack": 15,
    "partido de boca": 15,
    "partido de river": 15,
    "futbol argentino": 15,
    "futbol": 15,
    "fútbol": 15,
    "tnt sports": 16,
    "tnt sport": 16,
    "tyc": 17,
    "tyc sports": 17,
    "tyc sport": 17,
    "espn": 18,
    "espn 1": 18,
    "espn 2": 19,
    "espn 3": 20,
    "fox sports": 21,
    "fox sport": 21,
    "fox sports 1": 21,
    "fox sports 2": 22,
    "fox sports 3": 23,
    "dxtv": 24,
    "deportv": 24,
    "america sports": 25,
    "el garage": 26,
    "garage": 26,
    "espn 4": 27,
    "telefe": 4,
    "canal 11": 4,
    "el trece": 5,
    "trece": 5,
    "canal 13": 5,
    "tn": 6,
    "todo noticias": 6,
    "c5n": 7,
    "cronica": 8,
    "crónica": 8,
    "a24": 9,
    "la nacion": 10,
    "la nacion mas": 10,
    "ln+": 10,
    "canal 26": 11,
    "26": 11,
    "net tv": 12,
    "canal 9": 3,
    "tv publica": 2,
    "la publica": 2,
    "america": 1,
    "américa": 1,
    "cartoon network": 28,
    "cartoon": 28,
    "nickelodeon": 29,
    "discovery kids": 30,
    "disney": 31,
    "disney channel": 31,
    "paka paka": 33,
    "htv": 34,
    "mtv": 35,
    "quiero": 36,
    "hbo": 45,
    "star channel": 48,
    "star": 48,
    "tnt": 49,
    "sony": 52,
    "warner": 54,
    "warner channel": 54,
    "fx": 55,
    "cinecanal": 56,
    "cinemax": 57,
    "cine ar": 58,
    "cinear": 58,
    "space": 59,
    "volver": 65,
    "discovery": 67,
    "nat geo": 73,
    "national geographic": 73,
    "history": 74,
    "el gourmet": 78,
    "gourmet": 78,
    "ciudad magazine": 79,
    "dsports": 86,
    "directv sports": 86,
    "dsports 2": 87,
    "directv sports 2": 87
}


# Cadena Saltamontes -> XuperTV (tiempos medidos por Exequiel, 2026-09-22):
# la VPN tarda ~5s en conectar desde que abre la app, XuperTV abre sola a
# los 10-15s y la VPN se desactiva sola a los 30-35s (no hay que tocar nada).
_VPN_FIRST_WAIT = 20.0    # espera inicial a que XuperTV tome la pantalla
_VPN_SECOND_WAIT = 20.0   # espera extra tras OK (reintento de conexión VPN)
_VPN_LOAD_WAIT = 8.0      # espera a que XuperTV termine de cargar
_VPN_MAX_ATTEMPTS = 2     # reintentos completos ante el cartel de la política
_VPN_POLL_STEP = 2.0
_VPN_LAUNCH_WAIT = 10.0   # espera a que Saltamontes aparezca en primer plano tras lanzarla


class TVControl:
    """
    Controlador inteligente para la BGH Android TV (192.168.100.8).
    Permite encendido, apagado, volumen, multimedia, navegación y apertura directa
    de aplicaciones (OnPlay, YouTube, Netflix, etc.) con latencia cero vía ADB local.
    """

    def __init__(self, ip: str = DEFAULT_TV_IP, port: int = DEFAULT_TV_PORT):
        self.ip = ip
        self.port = port
        self.target = f"{self.ip}:{self.port}"
        self._adb_path = self._find_adb()
        self._last_connected_time = 0.0
        self._tv_apps = self._load_tv_apps()

    def _load_tv_apps(self) -> Dict[str, Any]:
        """Lee data/tv_apps.json (app de VPN y apps que la necesitan).

        Si el archivo no existe o está roto, usa los defaults: la VPN es
        Saltamontes y XuperTV siempre se abre a través de ella.
        """
        default: Dict[str, Any] = {"vpn_app": "saltamontes", "apps_con_vpn": ["xupertv"]}
        try:
            import json
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, "data", "tv_apps.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
                if isinstance(cfg, dict):
                    default.update(cfg)
        except Exception as e:
            log_warning(f"[TVControl] No se pudo leer tv_apps.json, uso defaults: {e}")
        return default

    def _find_adb(self) -> str:
        """Localiza el binario de adb tanto en Windows como en Linux DDR3"""
        found = shutil.which("adb")
        if found:
            return found
        
        # Rutas comunes en Linux
        linux_paths = [
            "/usr/lib/android-sdk/platform-tools/adb",
            "/usr/bin/adb",
            "/usr/local/bin/adb"
        ]
        for p in linux_paths:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
                
        # Rutas comunes en Windows
        win_candidates = [
            r"C:\Users\Exevaz27\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe",
            r"C:\platform-tools\adb.exe",
            r"C:\adb\adb.exe"
        ]
        for p in win_candidates:
            if os.path.exists(p):
                return p
                
        return "adb"

    def _ensure_connected(self) -> bool:
        """Verifica y asegura la conexión con la tele BGH"""
        now = time.time()
        if now - self._last_connected_time < 30.0:
            return True

        try:
            cmd = [self._adb_path, "connect", self.target]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            out = res.stdout.lower()
            if "connected" in out or "already connected" in out:
                self._last_connected_time = now
                return True
        except Exception as e:
            log_warning(f"[TVControl] Error conectando a {self.target}: {e}")
        return False

    def _run_shell(self, cmd_str: str, timeout: float = 6.0) -> Tuple[bool, str]:
        """Ejecuta un comando ADB sin pasar por un shell local ni remoto.

        S-1: `adb shell` re-ensambla sus argumentos con espacios y el shell
        de Android los interpreta. Por eso cada argumento se cita con
        shlex.quote() y se envía como un único argumento: el shell del
        dispositivo lo parsea respetando las comillas, así `;`, `$()`,
        backticks, `|` o `&&` llegan como texto literal y no se ejecutan.
        """
        try:
            self._ensure_connected()
            remote_args = shlex.split(cmd_str, posix=True)
            remote_cmd = " ".join(shlex.quote(a) for a in remote_args)
            full_cmd = [self._adb_path, "-s", self.target, "shell", remote_cmd]
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            out = res.stdout.strip()
            if res.returncode != 0 and ("not found" in out.lower() or "offline" in out.lower()):
                self._last_connected_time = 0.0
                self._ensure_connected()
                res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
                out = res.stdout.strip()

            clean_lines = [
                l for l in out.splitlines()
                if not l.lower().startswith("connected to") and not l.lower().startswith("already connected") and not l.lower().startswith("* daemon")
            ]
            clean_out = "\n".join(clean_lines).strip()
            return (res.returncode == 0, clean_out if clean_out else out)
        except subprocess.TimeoutExpired:
            log_warning(f"[TVControl] Timeout ejecutando comando en TV: {cmd_str}")
            return (False, "Timeout de conexión con la tele")
        except Exception as e:
            log_error(f"[TVControl] Error ejecutando comando en TV: {e}")
            return (False, str(e))

    def is_awake(self) -> bool:
        """Determina si la tele está encendida y activa"""
        ok, out = self._run_shell("dumpsys power", timeout=3.0)
        if not ok:
            return False
        for line in out.splitlines():
            if "mWakefulness=" in line:
                return "Awake" in line
        return False

    def turn_on(self) -> Dict[str, Any]:
        """Enciende la tele BGH desde standby"""
        if self.is_awake():
            return {"status": "success", "message": reply_pick("tv.already_on")}
        
        self._run_shell("input keyevent 224")
        time.sleep(0.5)
        if not self.is_awake():
            self._run_shell("input keyevent 26")
            
        return {"status": "success", "message": reply_pick("tv.turn_on")}

    def turn_off(self) -> Dict[str, Any]:
        """Apaga o pone la tele en modo reposo/standby"""
        if not self.is_awake():
            return {"status": "success", "message": reply_pick("tv.already_off")}
            
        self._run_shell("input keyevent 223")
        time.sleep(0.5)
        if self.is_awake():
            self._run_shell("input keyevent 26")
            
        return {"status": "success", "message": reply_pick("tv.turn_off")}

    def power_toggle(self) -> Dict[str, Any]:
        """Alterna encendido/apagado de la tele"""
        self._run_shell("input keyevent 26")
        return {"status": "success", "message": reply_pick("tv.toggle")}

    def set_hdmi(self, port: int = 1) -> Dict[str, Any]:
        """Cambia la entrada de la tele a HDMI 1-2 vía intent de passthrough de Android TV.

        Los keycodes 243-246 no están mapeados en esta BGH, así que se usa el
        método oficial: ACTION_VIEW sobre content://android.media.tv/passthrough/<inputId>
        con el inputId URL-encodeado (descubierto vía dumpsys tv_input).
        """
        if port not in HDMI_INPUT_IDS:
            return {"status": "error", "message": "La tele solo tiene HDMI 1 y 2, fiera. Pedime uno de esos."}
        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)
        input_id = HDMI_INPUT_IDS[port].replace("/", "%2F")
        uri = f"content://android.media.tv/passthrough/{input_id}"
        ok, out = self._run_shell(f"am start -a android.intent.action.VIEW -d {uri}", timeout=8.0)
        time.sleep(1.5)
        failed = (not ok) or ("error" in out.lower()) or ("not found" in out.lower())
        if failed:
            log_warning(f"[TVControl] Falló cambio a HDMI {port}: {out}")
            return {"status": "error", "message": f"No pude pasar a HDMI {port}, che. Probá con el control."}
        log_info(f"[TVControl] Entrada cambiada a HDMI {port}")
        return {"status": "success", "message": reply_pick("tv.hdmi", port=port)}

    def set_tv_input(self) -> Dict[str, Any]:
        """Cambia la entrada de la tele al sintonizador de TV (aire/cable, keycode 178)"""
        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)
        self._run_shell("input keyevent 178")
        time.sleep(0.8)
        log_info("[TVControl] Entrada cambiada a sintonizador de TV")
        return {"status": "success", "message": reply_pick("tv.tv_input")}

    def go_home(self) -> Dict[str, Any]:
        """Vuelve al inicio (launcher) de Android TV (keycode 3)"""
        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)
        self._run_shell("input keyevent 3")
        return {"status": "success", "message": reply_pick("tv.go_home")}

    def volume_up(self, steps: int = 1) -> Dict[str, Any]:
        """Sube el volumen de la tele"""
        steps = max(1, min(steps, 15))
        for _ in range(steps):
            self._run_shell("input keyevent 24")
            time.sleep(0.05)
        return {"status": "success", "message": reply_pick("tv.volume_up", steps=steps, s="s" if steps > 1 else "")}

    def volume_down(self, steps: int = 1) -> Dict[str, Any]:
        """Baja el volumen de la tele"""
        steps = max(1, min(steps, 15))
        for _ in range(steps):
            self._run_shell("input keyevent 25")
            time.sleep(0.05)
        return {"status": "success", "message": reply_pick("tv.volume_down", steps=steps, s="s" if steps > 1 else "")}

    def mute(self) -> Dict[str, Any]:
        """Mutea o desmutea el volumen de la tele"""
        self._run_shell("input keyevent 164")
        return {"status": "success", "message": reply_pick("tv.mute")}

    def set_volume(self, level: int) -> Dict[str, Any]:
        """Fija el nivel de volumen en la tele (0 a 100)"""
        level = max(0, min(level, 100))
        self._run_shell(f"cmd media_session volume --stream 3 --set {level}")
        return {"status": "success", "message": reply_pick("tv.set_volume", level=level)}

    def play_pause(self) -> Dict[str, Any]:
        """Alterna Play / Pausa en la tele"""
        self._run_shell("input keyevent 85")
        return {"status": "success", "message": reply_pick("tv.play_pause")}

    def next_track(self) -> Dict[str, Any]:
        """Pasa al siguiente video o capítulo en la tele"""
        self._run_shell("input keyevent 87")
        return {"status": "success", "message": reply_pick("tv.next")}

    def prev_track(self) -> Dict[str, Any]:
        """Vuelve al video o capítulo anterior en la tele"""
        self._run_shell("input keyevent 88")
        return {"status": "success", "message": reply_pick("tv.previous")}

    def send_key(self, key_name: str) -> Dict[str, Any]:
        """Envía una tecla de navegación del control remoto a la tele"""
        k = key_name.lower().strip()
        code = KEY_CODES.get(k)
        if not code:
            return {"status": "error", "message": f"No reconozco la tecla '{key_name}'."}
        self._run_shell(f"input keyevent {code}")
        return {"status": "success", "message": reply_pick("tv.send_key", key=key_name)}

    def type_text(self, text: str) -> Dict[str, Any]:
        """Escribe un texto en el buscador o campo activo de la tele"""
        safe_text = text.replace(" ", "%s").replace("'", "").replace('"', "")
        self._run_shell(f"input text {safe_text}")
        return {"status": "success", "message": reply_pick("tv.type_text", text=text)}

    def _discover_package(self, query: str) -> Optional[str]:
        """Busca en la tele un paquete instalado cuyo nombre contenga el texto.

        Sirve para apps fuera del catálogo (XuperTV, Ukiku, etc.) cuyos
        package names varían según la build instalada.
        """
        ok, out = self._run_shell("pm list packages", timeout=10.0)
        if not ok or not out:
            return None
        q = query.lower().replace(" ", "")
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            pkg = line[len("package:"):]
            if q and q in pkg.lower():
                log_info(f"[TVControl] Paquete descubierto para '{query}': {pkg}")
                return pkg
        return None

    def _launch_package(self, pkg: str) -> bool:
        """Lanza un paquete con monkey. True si el sistema confirma con
        'Events injected' (no basta con que el comando no falle)."""
        # S-1: descartar cualquier cosa que no sea un package name válido
        # antes de interpolarlo en el comando monkey.
        if not _PKG_RE.match(pkg):
            log_warning(f"[TVControl] Paquete inválido, se ignora: {pkg!r}")
            return False
        ok, out = self._run_shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        if not (ok and "events injected" in out.lower()):
            log_warning(f"[TVControl] No abrió {pkg}: {out[:120]}")
            return False
        return True

    def _foreground_has(self, pkg: str) -> bool:
        """True si el paquete está en la ventana enfocada ahora mismo."""
        _, _, focused = self.get_focused_window()
        return bool(pkg and pkg in focused)

    def _wait_foreground(self, pkg: str, timeout: float) -> bool:
        """Espera (polling) a que el paquete tome la pantalla."""
        end = time.time() + timeout
        while time.time() < end:
            if self._foreground_has(pkg):
                return True
            time.sleep(_VPN_POLL_STEP)
        return self._foreground_has(pkg)

    def _wait_foreground_left(self, pkg: str, timeout: float) -> bool:
        """Espera (polling) a que el paquete DEJE la pantalla.

        Se usa en la cadena VPN: Saltamontes abre XuperTV sola, así que el
        éxito es que la VPN ya no esté en primer plano (no hace falta saber
        el nombre interno del paquete de XuperTV).
        """
        end = time.time() + timeout
        while time.time() < end:
            if not self._foreground_has(pkg):
                return True
            time.sleep(_VPN_POLL_STEP)
        return not self._foreground_has(pkg)

    def _has_geo_cartel(self) -> bool:
        """Detecta el cartel de 'limitación de la política' de XuperTV
        (la VPN se desactivó antes de que la app termine de cargar).

        Se lee con uiautomator dump y se buscan las marcas del cartel
        normalizadas (sin acentos): 'limitación de la política',
        'no se puede usar en tu área' y 'distribuidor'.
        """
        ok, out = self._run_shell("uiautomator dump /dev/stdout", timeout=10.0)
        if not ok or not out:
            return False
        t = _strip_accents(out.lower())
        return (("limitaci" in t and "tu area" in t) or "distribuidor" in t)

    def _open_via_vpn(self, target_name: str) -> Dict[str, Any]:
        """Abre una app que solo anda detrás de la VPN (XuperTV) con la
        cadena de Saltamontes, replicando el procedimiento manual de Exequiel.

        NO necesita conocer el paquete de la app objetivo: Saltamontes la
        abre sola, así que el éxito es que la VPN DEJE de estar en primer
        plano (XuperTV tomó la pantalla).

        1. Abre la app de la VPN y espera a que tome la pantalla.
        2. Espera a que la VPN deje el primer plano: XuperTV abrió sola
           (la VPN tarda ~5s en conectar; XuperTV abre sola a los 10-15s).
        3. Error 1: si la VPN sigue al frente, se toca OK (reintenta la
           conexión VPN, como hace él con el control) y se espera de nuevo.
        4. Error 2: si salió el cartel de limitación de la política (la VPN
           se desactivó antes de que XuperTV termine de cargar), se toca
           ATRÁS y se arranca la cadena de nuevo (máx. _VPN_MAX_ATTEMPTS).
        5. Si todo falla, se sugiere el fallback a Cloudstream (el que
           decide es Exequiel, no se abre solo).
        """
        vpn_query = str(self._tv_apps.get("vpn_app", "saltamontes"))
        vpn_pkg = self._discover_package(vpn_query)
        if not vpn_pkg:
            return {"status": "error", "suggest_fallback": True,
                    "message": f"No encontré la app de la VPN ({vpn_query}) instalada en la tele."}

        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)

        for attempt in range(1, _VPN_MAX_ATTEMPTS + 1):
            log_info(f"[TVControl] Cadena VPN intento {attempt}/{_VPN_MAX_ATTEMPTS}: {vpn_pkg}")
            if not self._launch_package(vpn_pkg):
                continue
            # Confirmar que Saltamontes tomó la pantalla antes de esperar
            # que la abandone (si no, el launcher al fondo daría un
            # falso "éxito" inmediato).
            if not self._wait_foreground(vpn_pkg, _VPN_LAUNCH_WAIT):
                log_warning("[TVControl] Saltamontes no tomó la pantalla")
                continue
            if not self._wait_foreground_left(vpn_pkg, _VPN_FIRST_WAIT):
                log_info("[TVControl] La app no apareció; toco OK para reintentar la VPN")
                self._run_shell("input keyevent 66", timeout=2.5)
                if not self._wait_foreground_left(vpn_pkg, _VPN_SECOND_WAIT):
                    log_warning("[TVControl] La VPN no conectó tras el reintento")
                    continue
            time.sleep(_VPN_LOAD_WAIT)
            if self._has_geo_cartel():
                log_warning("[TVControl] Cartel de limitación de política; cierro y reintento")
                self._run_shell("input keyevent 4", timeout=2.5)
                time.sleep(1.5)
                continue
            log_info("[TVControl] App abierta y cargada vía VPN")
            return {"status": "success",
                    "message": reply_pick("tv.xuper_ok")}

        return {"status": "error", "suggest_fallback": True,
                "message": reply_pick("tv.xuper_fail")}

    def open_app(self, app_name: str) -> Dict[str, Any]:
        """Abre una aplicación en la tele por su nombre común o paquete.

        Las apps de apps_con_vpn (XuperTV) SIEMPRE se abren por la cadena de
        la VPN: abrirlas directo nace muerta por el bloqueo geográfico.

        Si no está en el catálogo, descubre el paquete real instalado en la tele
        y prueba cada candidato hasta que uno abra de verdad (monkey confirma
        con 'Events injected', no basta con que el comando no falle).
        """
        q = app_name.lower().strip()

        # XuperTV (y las que se sumen) jamás se abren directo: van por la VPN.
        if q in [a.lower() for a in self._tv_apps.get("apps_con_vpn", [])]:
            return self._open_via_vpn(q)

        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)

        candidates: List[str] = []
        pkg = APP_PACKAGES.get(q)
        if not pkg:
            for k, v in APP_PACKAGES.items():
                if k in q or q in k:
                    pkg = v
                    break
        if pkg:
            candidates.append(pkg)
        disc = self._discover_package(q)
        if disc and disc not in candidates:
            candidates.append(disc)
        if "." in q and q not in candidates:
            candidates.append(q)

        display_names = {
            "ar.com.onplay.tv": "OnPlay TV",
            "org.smarttube.stable": "SmartTube (YouTube)",
            "com.netflix.ninja": "Netflix",
            "com.google.android.youtube.tv": "YouTube",
            "org.videolan.vlc": "VLC",
            "com.spotify.tv.android": "Spotify",
            "com.lagradost.cloudstream3.prereleasf": "Cloudstream",
        }

        for cand in candidates:
            if self._launch_package(cand):
                name_clean = display_names.get(cand, app_name.capitalize())
                log_info(f"[TVControl] App abierta con éxito: {cand} ({name_clean})")
                return {"status": "success", "message": reply_pick("tv.open_app", app=name_clean)}

        return {
            "status": "error",
            "message": f"No encontré la app '{app_name}' en la tele. Probá con YouTube, OnPlay, Netflix, VLC, etc."
        }

    def resolve_channel(self, query: str) -> Optional[Tuple[int, str]]:
        """
        Resuelve un texto o número al canal exacto de OnPlay (de 1 a 97).
        Devuelve (channel_number, channel_title) o None.
        """
        q = _strip_accents(query.lower().strip())

        clean_q = q
        # Quitar palabras de relleno y frases introductorias
        noise_words = [
            "prende la tele y pone", "prende la tele y ponele", "prende la tele y poneme",
            "prende la tele y", "prender la tele y poner", "prender la tele y",
            "prende la tele", "prender la tele", "prende", "prender", "prendeme",
            "pone", "poné", "poneme", "ponele", "poner", "abrir", "abri", "abrí",
            "sintoniza", "sintonizá", "sintonizame", "ver", "mira", "mirá", "mirame",
            "en onplay", "en la tele", "en la tv", "en tele", "onplay", "tele", "tv",
            "el", "la", "los", "las", "por favor", "porfa", "che", "titan", "titán",
            "canal", "numero", "ch", "y", "e"
        ]
        # Ordenar por longitud descendente para remover frases largas primero
        for noise in sorted(noise_words, key=len, reverse=True):
            clean_q = re.sub(rf'\b{re.escape(noise)}\b', ' ', clean_q)
        clean_q = " ".join(clean_q.split()).strip()

        # 1. Alias exacto sobre texto limpio
        if clean_q in CHANNEL_ALIASES:
            ch_num = CHANNEL_ALIASES[clean_q]
            return ch_num, ONPLAY_CHANNELS[ch_num][0]

        # 2. Alias exacto sobre texto original sin acentos
        if q in CHANNEL_ALIASES:
            ch_num = CHANNEL_ALIASES[q]
            return ch_num, ONPLAY_CHANNELS[ch_num][0]

        # 3. Búsqueda de alias por frase completa / palabra (priorizando los más largos: "tnt sports" antes que "tnt")
        for alias, ch_num in sorted(CHANNEL_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf'\b{re.escape(alias)}\b', clean_q) or re.search(rf'\b{re.escape(alias)}\b', q):
                return ch_num, ONPLAY_CHANNELS[ch_num][0]

        # 4. Coincidencia directa con nombres de canales (normalizados)
        for num, (title, cat) in ONPLAY_CHANNELS.items():
            t_clean = _strip_accents(title.lower())
            t_clean = re.sub(r'\b(hd|tv)\b', '', t_clean).strip()
            t_clean = " ".join(t_clean.split())
            if clean_q and clean_q == t_clean:
                return num, title

        # 5. Solicitud explícita de número ("canal 15", "el 17", o "15")
        digit_m = re.search(r'\b(\d{1,3})\b', clean_q)
        if digit_m:
            val = int(digit_m.group(1))
            if val in ONPLAY_CHANNELS:
                return val, ONPLAY_CHANNELS[val][0]

        # 6. Coincidencia segura (evitando que nombres cortos como "TN" coincidan con "TNT")
        for num, (title, cat) in ONPLAY_CHANNELS.items():
            t_clean = _strip_accents(title.lower())
            t_clean = re.sub(r'\b(hd|tv)\b', '', t_clean).strip()
            t_clean = " ".join(t_clean.split())
            if not clean_q or not t_clean:
                continue
            if len(t_clean) <= 3:
                if re.search(rf'\b{re.escape(t_clean)}\b', clean_q):
                    return num, title
            else:
                if clean_q in t_clean or t_clean in clean_q:
                    return num, title

        return None

    def get_focused_window(self) -> Tuple[bool, bool, str]:
        """
        Devuelve (is_player, is_menu, focused_component) analizando ÚNICAMENTE
        la ventana y actividad actualmente enfocadas en pantalla (mCurrentFocus / mFocusedApp),
        evitando falsos positivos de ventanas en segundo plano o wake locks.
        """
        ok, out = self._run_shell("dumpsys window", timeout=3.5)
        if not ok or not out:
            return False, False, ""

        focused = ""
        for line in out.splitlines():
            s = line.strip()
            if "mCurrentFocus" in s and "null" not in s:
                focused += " " + s
            elif "mFocusedApp" in s and "null" not in s:
                focused += " " + s

        is_player = "ChannelPlayerActivity" in focused
        is_menu = "MenuActivity" in focused
        return is_player, is_menu, focused

    def tune_channel(self, channel_query: str) -> Dict[str, Any]:
        """
        Sintoniza directamente un canal en OnPlay por nombre o número:
        1. Resuelve el número de canal y nombre a partir del catálogo de 97 canales.
        2. Enciende la tele si está en reposo.
        3. Si la app no está abierta o en pantalla, la abre limpiamente con am start.
        4. Si está en MenuActivity, presiona OK para ingresar al reproductor en vivo.
        5. Envía las teclas numéricas correspondientes + ENTER.
        """
        resolved = self.resolve_channel(channel_query)
        if not resolved:
            return {
                "status": "error",
                "message": f"No encontré el canal '{channel_query}' en OnPlay. Probá con ESPN Premium, TNT Sports, TyC Sports, Telefe, TN, Fox Sports, HBO, etc."
            }

        ch_num, ch_title = resolved

        # 1. Asegurar tele encendida
        was_awake = self.is_awake()
        if not was_awake:
            self.turn_on()
            time.sleep(2.0)

        # 2. Asegurar que esté dentro del reproductor de TV en vivo
        is_player, is_menu, focused = self.get_focused_window()

        if not is_player:
            if not is_menu:
                # Si la app estaba en segundo plano o congelada, forzar detención e inicio limpio
                self._run_shell("am force-stop ar.com.onplay.tv", timeout=2.0)
                time.sleep(0.3)
                self._run_shell("am start -n ar.com.onplay.tv/ar.com.claynet.tv.standalone.MainActivity", timeout=3.0)
                # Esperar a que cargue la app (espera activa hasta 6 segundos)
                for _ in range(12):
                    time.sleep(0.5)
                    is_player, is_menu, focused = self.get_focused_window()
                    if is_menu or is_player:
                        break

            # Si está en el menú de bienvenida, presionar OK sobre "OnPlay TV"
            if not is_player:
                time.sleep(0.8)
                self._run_shell("input keyevent 66", timeout=2.5)
                # Esperar a que arranque el reproductor
                for _ in range(10):
                    time.sleep(0.4)
                    is_player, _, focused = self.get_focused_window()
                    if is_player:
                        break
                time.sleep(0.8)
        else:
            time.sleep(0.2)

        # 3. Enviar dígitos numéricos de canal
        for digit in str(ch_num):
            digit_code = 7 + int(digit)
            self._run_shell(f"input keyevent {digit_code}", timeout=2.0)
            time.sleep(0.15)

        # ENTER para confirmar sintonización inmediata
        self._run_shell("input keyevent 66", timeout=2.5)

        log_info(f"[TVControl] Canal sintonizado: {ch_title} (Canal {ch_num})")
        return {
            "status": "success",
            "channel_number": ch_num,
            "channel_name": ch_title,
            "message": reply_pick("tv.tune_channel", channel=ch_title, num=ch_num)
        }

    def open_onplay_live(self, channel_name_or_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Macro especializada para abrir OnPlay y sintonizar TV en vivo.
        Si se pasa un canal, lo sintoniza. Si no, abre la app y presiona OK para entrar directo a TV en vivo.
        """
        if channel_name_or_number:
            return self.tune_channel(str(channel_name_or_number))

        if not self.is_awake():
            self.turn_on()
            time.sleep(2.0)

        is_player, is_menu, focused = self.get_focused_window()
        if not is_player:
            if not is_menu:
                self._run_shell("am force-stop ar.com.onplay.tv", timeout=2.0)
                time.sleep(0.3)
                self._run_shell("am start -n ar.com.onplay.tv/ar.com.claynet.tv.standalone.MainActivity", timeout=3.0)
                for _ in range(12):
                    time.sleep(0.5)
                    is_player, is_menu, focused = self.get_focused_window()
                    if is_menu or is_player:
                        break

            if not is_player:
                time.sleep(0.8)
                self._run_shell("input keyevent 66", timeout=2.5)
                for _ in range(10):
                    time.sleep(0.4)
                    is_player, _, focused = self.get_focused_window()
                    if is_player:
                        break

        return {
            "status": "success",
            "message": reply_pick("tv.onplay_tv")
        }

    def list_channels(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Devuelve la lista de canales disponibles en OnPlay con sus números y categorías"""
        results = []
        for num, (title, cat) in ONPLAY_CHANNELS.items():
            if category and category.lower() not in cat.lower():
                continue
            results.append({"number": num, "name": title, "category": cat})
        return results

    def get_status(self) -> Dict[str, Any]:
        """Devuelve el estado completo de la tele BGH"""
        awake = self.is_awake()
        return {
            "ip": self.ip,
            "port": self.port,
            "connected": self._ensure_connected(),
            "power": "encendida" if awake else "apagada / reposo",
            "model": "BGH Smart TV (Android 14)",
            "total_channels": len(ONPLAY_CHANNELS)
        }

tv_control = TVControl()
