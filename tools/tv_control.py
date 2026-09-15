import os
import shutil
import subprocess
import time
import re
import shlex
from typing import Dict, Any, Optional, List, Tuple
from core.logger import log_info, log_error, log_warning

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
        """Ejecuta un comando ADB sin pasar por un shell local."""
        try:
            self._ensure_connected()
            remote_args = shlex.split(cmd_str, posix=True)
            full_cmd = [self._adb_path, "-s", self.target, "shell", *remote_args]
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
            return {"status": "success", "message": "La tele ya está prendida, papá."}
        
        self._run_shell("input keyevent 224")
        time.sleep(0.5)
        if not self.is_awake():
            self._run_shell("input keyevent 26")
            
        return {"status": "success", "message": "Listo fiera, tele prendida."}

    def turn_off(self) -> Dict[str, Any]:
        """Apaga o pone la tele en modo reposo/standby"""
        if not self.is_awake():
            return {"status": "success", "message": "La tele ya está apagada, che."}
            
        self._run_shell("input keyevent 223")
        time.sleep(0.5)
        if self.is_awake():
            self._run_shell("input keyevent 26")
            
        return {"status": "success", "message": "Listo papá, tele apagada."}

    def power_toggle(self) -> Dict[str, Any]:
        """Alterna encendido/apagado de la tele"""
        self._run_shell("input keyevent 26")
        return {"status": "success", "message": "Comando de encendido/apagado enviado a la tele."}

    def volume_up(self, steps: int = 1) -> Dict[str, Any]:
        """Sube el volumen de la tele"""
        steps = max(1, min(steps, 15))
        for _ in range(steps):
            self._run_shell("input keyevent 24")
            time.sleep(0.05)
        return {"status": "success", "message": f"Subí el volumen de la tele {steps} punto{'s' if steps > 1 else ''}."}

    def volume_down(self, steps: int = 1) -> Dict[str, Any]:
        """Baja el volumen de la tele"""
        steps = max(1, min(steps, 15))
        for _ in range(steps):
            self._run_shell("input keyevent 25")
            time.sleep(0.05)
        return {"status": "success", "message": f"Bajé el volumen de la tele {steps} punto{'s' if steps > 1 else ''}."}

    def mute(self) -> Dict[str, Any]:
        """Mutea o desmutea el volumen de la tele"""
        self._run_shell("input keyevent 164")
        return {"status": "success", "message": "Muteé la tele, fiera."}

    def set_volume(self, level: int) -> Dict[str, Any]:
        """Fija el nivel de volumen en la tele (0 a 100)"""
        level = max(0, min(level, 100))
        self._run_shell(f"cmd media_session volume --stream 3 --set {level}")
        return {"status": "success", "message": f"Puse el volumen de la tele en {level}."}

    def play_pause(self) -> Dict[str, Any]:
        """Alterna Play / Pausa en la tele"""
        self._run_shell("input keyevent 85")
        return {"status": "success", "message": "Listo, alterné play/pausa en la tele."}

    def next_track(self) -> Dict[str, Any]:
        """Pasa al siguiente video o capítulo en la tele"""
        self._run_shell("input keyevent 87")
        return {"status": "success", "message": "Pasé al siguiente en la tele."}

    def prev_track(self) -> Dict[str, Any]:
        """Vuelve al video o capítulo anterior en la tele"""
        self._run_shell("input keyevent 88")
        return {"status": "success", "message": "Volví al anterior en la tele."}

    def send_key(self, key_name: str) -> Dict[str, Any]:
        """Envía una tecla de navegación del control remoto a la tele"""
        k = key_name.lower().strip()
        code = KEY_CODES.get(k)
        if not code:
            return {"status": "error", "message": f"No reconozco la tecla '{key_name}'."}
        self._run_shell(f"input keyevent {code}")
        return {"status": "success", "message": f"Tecla {key_name} enviada a la tele."}

    def type_text(self, text: str) -> Dict[str, Any]:
        """Escribe un texto en el buscador o campo activo de la tele"""
        safe_text = text.replace(" ", "%s").replace("'", "").replace('"', "")
        self._run_shell(f"input text {safe_text}")
        return {"status": "success", "message": f"Escribí '{text}' en la tele, papá."}

    def open_app(self, app_name: str) -> Dict[str, Any]:
        """Abre una aplicación en la tele por su nombre común o paquete"""
        q = app_name.lower().strip()
        
        if not self.is_awake():
            self.turn_on()
            time.sleep(1.0)

        pkg = APP_PACKAGES.get(q)
        if not pkg:
            for k, v in APP_PACKAGES.items():
                if k in q or q in k:
                    pkg = v
                    break

        if not pkg:
            if "." in q:
                pkg = q
            else:
                return {
                    "status": "error",
                    "message": f"No encontré la app '{app_name}' en la tele. Probá con YouTube, OnPlay, Netflix, VLC, etc."
                }

        ok, out = self._run_shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        
        display_names = {
            "ar.com.onplay.tv": "OnPlay TV",
            "org.smarttube.stable": "SmartTube (YouTube)",
            "com.netflix.ninja": "Netflix",
            "com.google.android.youtube.tv": "YouTube",
            "org.videolan.vlc": "VLC",
            "com.spotify.tv.android": "Spotify"
        }
        name_clean = display_names.get(pkg, app_name.capitalize())
        
        if ok:
            log_info(f"[TVControl] App abierta con éxito: {pkg} ({name_clean})")
            return {"status": "success", "message": f"Ahí te abrí {name_clean} en la tele, papá."}
        else:
            log_warning(f"[TVControl] Error abriendo {pkg}: {out}")
            return {"status": "error", "message": f"No pude abrir {name_clean} en la tele."}

    def resolve_channel(self, query: str) -> Optional[Tuple[int, str]]:
        """
        Resuelve un texto o número al canal exacto de OnPlay (de 1 a 97).
        Devuelve (channel_number, channel_title) o None.
        """
        q = query.lower().strip()
        for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")]:
            q = q.replace(a, b)

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
            t_clean = title.lower()
            for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")]:
                t_clean = t_clean.replace(a, b)
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
            t_clean = title.lower()
            for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")]:
                t_clean = t_clean.replace(a, b)
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
            "message": f"¡De una, papá! Puse {ch_title} (Canal {ch_num}) en OnPlay."
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
            "message": "¡De una, fiera! Ahí te prendí la tele y te abrí OnPlay en TV en vivo."
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
