"""Mixin de Spotify y teclas multimedia."""

from core.logger import log_info, log_warning

import ctypes

import os

from core.process_utils import run_silent, popen_silent

from core.state_manager import state_mgr, AssistantState

import subprocess

import time

from typing import Any, Dict

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


class SpotifyMixin:

    def _get_spotify_cli_path(self) -> str:
        p = os.path.expandvars(r"%APPDATA%\Spotify\spotify_cli.exe")
        return p if os.path.exists(p) else ""

    def _get_spotify_exe_path(self) -> str:
        p = os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
        return p if os.path.exists(p) else ""

    def _bring_spotify_window_to_front(self) -> bool:
        """Busca la ventana de Spotify en el escritorio interactivo y la restaura al frente"""
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)

            target_hwnd = None
            def enum_cb(hwnd, _):
                nonlocal target_hwnd
                if user32.IsWindow(hwnd):
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    length = user32.GetWindowTextLengthW(hwnd)
                    title_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, title_buf, length + 1)
                    t_lower = title_buf.value.lower()
                    if "spotify" in t_lower or "spotify" in cls_buf.value.lower():
                        target_hwnd = hwnd
                        return False
                return True

            CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)(enum_cb)
            user32.EnumWindows(CB, 0)

            if target_hwnd:
                user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
                user32.SetForegroundWindow(target_hwnd)
                user32.BringWindowToTop(target_hwnd)
                return True
        except Exception:
            pass
        return False

    def _ensure_spotify_running(self) -> bool:
        cli_path = self._get_spotify_cli_path()
        exe_path = self._get_spotify_exe_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower() or "logged in: yes" in res.stdout.lower():
                    self._bring_spotify_window_to_front()
                    return True
            except Exception:
                pass

        # B-28: antes se creaba una tarea schtasks programada a las 23:59 para
        # lanzar Spotify (frágil: depende del Programador de tareas y de una
        # hora arbitraria). Ahora lanzamiento directo con Popen, probado en B-5.
        if self._launch_spotify_exe():
            if cli_path:
                for _ in range(12):
                    time.sleep(0.4)
                    try:
                        res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                        if "is running" in res.stdout.lower():
                            self._bring_spotify_window_to_front()
                            return True
                    except Exception:
                        pass
            else:
                time.sleep(1.5)
                self._bring_spotify_window_to_front()
                return True
        return False

    def _launch_spotify_exe(self) -> bool:
        """Lanza el ejecutable de Spotify directamente.

        B-5: NO usar app_launcher aquí. El método no existe como
        ``app_launcher.launch`` (es ``launch_app``) y llamarlo de todos
        modos causaría recursión infinita: launch_app("spotify") reentra
        a system_control.play_spotify("").
        """
        exe_path = self._get_spotify_exe_path()
        if exe_path and os.path.exists(exe_path):
            try:
                subprocess.Popen(
                    [exe_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                log_info(f"[Spotify] Lanzado directamente: {exe_path}")
                return True
            except Exception as e:
                log_warning(f"[Spotify] No se pudo lanzar {exe_path}: {e}")
        return False

    def _send_media_key(self, vk_code: int):
        import time
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

    def media_play_pause(self) -> Dict[str, Any]:
        """Pausa o reanuda la música/video dando prioridad a Spotify y luego a YouTube en Brave"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_play_pause", {}, "Play/Pausa enviado a la compu, che.")
            if remote_res:
                return remote_res

        # 1. Spotify si está activo
        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res_np = run_silent([cli_path, "now-playing"], capture_output=True, text=True, timeout=2)
                if "status: playing" in res_np.stdout.lower():
                    run_silent([cli_path, "pause"], capture_output=True)
                    msg = "Puse pausa a la música en Spotify."
                    state_mgr.emit_tool_call("media_play_pause", {"target": "spotify", "action": "pause"}, msg)
                    return {"status": "success", "message": msg}
                elif "status: paused" in res_np.stdout.lower() or "status: stopped" in res_np.stdout.lower():
                    run_silent([cli_path, "resume"], capture_output=True)
                    msg = "Reanudé la música en Spotify."
                    state_mgr.emit_tool_call("media_play_pause", {"target": "spotify", "action": "resume"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        # 2. Si no es Spotify, enviar la tecla multimedia del sistema (pausa YouTube/video sin mutear el navegador)
        self._send_media_key(VK_MEDIA_PLAY_PAUSE)
        msg = "Play/Pausa enviado."
        state_mgr.emit_tool_call("media_play_pause", {}, msg)
        return {"status": "success", "message": msg}

    def stop_music(self) -> Dict[str, Any]:
        """Detiene la música por completo pausando Spotify o cerrando YouTube en Brave"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("stop_music", {}, "Listo, detuve la música en la compu.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                run_silent([cli_path, "pause"], capture_output=True)
            except Exception:
                pass
        run_silent(["taskkill", "/F", "/IM", "brave.exe"], capture_output=True)
        msg = "Listo, detuve la música."
        state_mgr.emit_tool_call("stop_music", {}, msg)
        return {"status": "success", "message": msg}

    def media_next(self) -> Dict[str, Any]:
        """Pasa a la siguiente canción"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_next", {}, "Puse la siguiente canción en la compu, crack.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower():
                    run_silent([cli_path, "next"], capture_output=True)
                    msg = "Puse la siguiente canción en Spotify."
                    state_mgr.emit_tool_call("media_next", {"target": "spotify", "action": "next"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        self._send_media_key(VK_MEDIA_NEXT_TRACK)
        msg = "Puse la siguiente pista."
        state_mgr.emit_tool_call("media_next", {}, msg)
        return {"status": "success", "message": msg}

    def media_prev(self) -> Dict[str, Any]:
        """Vuelve a la canción anterior"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("media_prev", {}, "Volví al tema anterior en la compu.")
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "status"], capture_output=True, text=True, timeout=2)
                if "is running" in res.stdout.lower():
                    run_silent([cli_path, "previous"], capture_output=True)
                    msg = "Volví a la canción anterior en Spotify."
                    state_mgr.emit_tool_call("media_prev", {"target": "spotify", "action": "previous"}, msg)
                    return {"status": "success", "message": msg}
            except Exception:
                pass

        self._send_media_key(VK_MEDIA_PREV_TRACK)
        msg = "Volví a la pista anterior."
        state_mgr.emit_tool_call("media_prev", {}, msg)
        return {"status": "success", "message": msg}

    def get_current_song(self) -> Dict[str, Any]:
        """Obtiene el nombre de la canción o tema que está reproduciéndose actualmente"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("get_current_song", {}, "Chequeé qué suena en la compu.")
            if remote_res:
                return remote_res
        cli_path = self._get_spotify_cli_path()
        if cli_path:
            try:
                res = run_silent([cli_path, "now-playing"], capture_output=True, text=True, timeout=2)
                if res.stdout and ("spotify:track:" in res.stdout or "—" in res.stdout or "-" in res.stdout):
                    lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                    raw_info = lines[0] if lines else ""
                    # Quitar el URI si está al final
                    clean_info = raw_info.split("spotify:")[0].strip()
                    # B-19: partir solo por el PRIMER separador (con espacios
                    # primero). Antes split("-") cortaba por todos los guiones
                    # y "AC-DC - Back In Black" quedaba "'AC' de DC".
                    sep = next((c for c in (" — ", " - ", "—", "-") if c in clean_info), None)
                    if sep:
                        title, artist = (p.strip() for p in clean_info.split(sep, 1))
                        track_info = f"'{title}' de {artist}" if artist else f"'{title}'"
                    else:
                        track_info = clean_info or "música en Spotify"

                    msg = f"Está sonando {track_info} en Spotify, fiera."
                    state_mgr.emit_tool_call("get_current_song", {"target": "spotify", "track": track_info}, msg)
                    return {"status": "success", "message": msg, "track": track_info}
            except Exception:
                pass
        return {"status": "error", "message": "No tengo información de qué tema está sonando ahora."}

    def play_spotify(self, query: str = "") -> Dict[str, Any]:
        """Busca y reproduce una canción, artista, álbum o playlist en Spotify directamente en la computadora."""
        import urllib.parse
        import ctypes
        import time
        import os
        import json
        import subprocess

        raw_q = (query or "").strip()
        clean_q = raw_q

        # Limpiar prefijos comunes
        prefixes = [
            "cuautitlan", "cuautitlán", "ehu titan", "ehu titán", "eu titan", "eu titán",
            "titan", "titán", "el titan", "el titán", "che titan", "che titán", "che", "eu", "eh", "ey",
            "pone en spotify", "poné en spotify", "pon en spotify", "poneme en spotify", "ponéme en spotify",
            "reproducir en spotify", "reproduci en spotify", "reproducí en spotify", "reproducime en spotify",
            "buscar en spotify", "busca en spotify", "buscá en spotify", "buscame en spotify",
            "abrir spotify y poner", "abrí spotify y poné", "abrir spotify", "abri spotify", "abrí spotify",
            "pone", "poné", "pon", "poner", "poneme", "ponéme", "reproducir", "reproduci", "reproducí", "reproducime",
            "toca", "tocá", "tocame", "tocáme", "escuchar", "escucha", "buscar", "busca", "buscá", "abrir", "abri", "abrí",
            "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
            "la canción de", "la canción del", "la canción",
            "la musica de", "la musica del", "la musica", "la música de", "la música del", "la música",
            "musica", "música", "disco de", "album de", "álbum de"
        ]

        low_q = clean_q.lower()
        changed = True
        while changed:
            changed = False
            for p in prefixes:
                if low_q.startswith(p + " "):
                    clean_q = clean_q[len(p):].strip()
                    low_q = clean_q.lower()
                    changed = True
                    break
                elif low_q == p:
                    clean_q = ""
                    low_q = ""
                    break

        # Limpiar sufijos
        for suffix in ["en spotify", "de spotify", "por spotify", "spotify"]:
            if low_q.endswith(" " + suffix):
                clean_q = clean_q[:-len(suffix)-1].strip()
                low_q = clean_q.lower()
            elif low_q == suffix:
                clean_q = ""
                low_q = ""
                break

        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "play_spotify",
                {"query": clean_q},
                f"Ahí te puse '{clean_q}' en Spotify en la compu, fiera." if clean_q else "Ahí te abrí Spotify en la compu, fiera."
            )
            if remote_res:
                return remote_res

        cli_path = self._get_spotify_cli_path()
        exe_path = self._get_spotify_exe_path()

        # Asegurar que Spotify esté iniciado
        is_running = self._ensure_spotify_running()
        if not is_running:
            # B-5: lanzamiento directo (app_launcher.launch no existe y
            # launch_app("spotify") reentraría a play_spotify en loop).
            if not self._launch_spotify_exe():
                msg = "No pude abrir Spotify en la PC: no está corriendo y no logré iniciarlo."
                log_warning(f"[Spotify] {msg}")
                state_mgr.emit_tool_call("play_spotify", {"query": query}, msg)
                return {"status": "error", "message": msg}

        # Si no hay término de búsqueda, solo reanudar Spotify
        if not clean_q:
            if cli_path:
                # B-29: antes se disparaban "open" + "resume". El "open" sobra:
                # _ensure_spotify_running ya trajo la ventana al frente; solo
                # queda asegurarse de que suene.
                run_silent([cli_path, "resume"], capture_output=True)
                self._bring_spotify_window_to_front()
            elif not self._launch_spotify_exe():
                # B-5: idem arriba, sin CLI solo queda el ejecutable directo.
                msg = "No pude abrir Spotify en la PC."
                log_warning(f"[Spotify] {msg}")
                state_mgr.emit_tool_call("play_spotify", {"query": query}, msg)
                return {"status": "error", "message": msg}
            msg = "Ahí te abrí Spotify, fiera."
            state_mgr.emit_tool_call("play_spotify", {"query": ""}, msg)
            return {"status": "success", "message": msg}

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Poniendo en Spotify: {clean_q}")
        log_info(f"[Spotify] Buscando y reproduciendo: {clean_q}")

        target_uri = None
        target_title = f"'{clean_q}'"

        # 1. Búsqueda directa en catálogo de Spotify mediante Spotify CLI (100% invisible)
        if cli_path:
            try:
                res = run_silent([cli_path, "search", clean_q, "--limit", "3", "--format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
                if res.stdout:
                    data = json.loads(res.stdout)
                    if data.get("tracks"):
                        t = data["tracks"][0]
                        target_uri = t.get("uri")
                        artists = ", ".join(t.get("artists", []))
                        target_title = f"'{t.get('name')}' de {artists}" if artists else f"'{t.get('name')}'"
                    elif data.get("artists"):
                        a = data["artists"][0]
                        target_uri = a.get("uri")
                        target_title = f"música de {a.get('name')}"
                    elif data.get("playlists"):
                        pl = data["playlists"][0]
                        target_uri = pl.get("uri")
                        target_title = f"la playlist '{pl.get('name')}'"
            except Exception as e:
                log_warning(f"[Spotify] Error buscando en catálogo CLI: {e}")

        # Fallback a URI de búsqueda si no se obtuvo URI específico
        if not target_uri:
            target_uri = f"spotify:search:{urllib.parse.quote(clean_q)}"

        # 2. Ejecutar reproducción (completamente en segundo plano sin ventanas)
        if cli_path:
            # B-29: antes se disparaban "play" + "navigate --play" + "open"
            # a la vez y se pisaban entre sí. Ahora un solo comando: se prueba
            # en orden y se frena en el primero que funcione.
            for cmd in (["play", target_uri],
                        ["navigate", target_uri, "--play"],
                        ["open", target_uri]):
                try:
                    res = run_silent([cli_path] + cmd, capture_output=True,
                                     text=True, timeout=8)
                    if res.returncode == 0:
                        break
                except Exception:
                    continue
            self._bring_spotify_window_to_front()
        else:
            uri = f"spotify:search:{urllib.parse.quote(clean_q)}"
            popen_silent(["explorer.exe", uri])


        msg = f"Ahí te puse {target_title} en Spotify, fiera."
        state_mgr.emit_tool_call("play_spotify", {"query": clean_q, "uri": target_uri}, msg)
        log_info(f"Spotify reproducido: {clean_q} -> {target_uri}")
        return {"status": "success", "message": msg, "query": clean_q, "uri": target_uri}
