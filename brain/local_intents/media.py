"""Volumen, YouTube y Spotify.."""

from ._common import _mip
import re
from core.config import config
from tools.system_control import system_control

from typing import Optional

def handle_volume(engine, text, clean, norm) -> "Optional[str]":
    """6. MINIMIZAR Y VOLUMEN."""
    if any(_mip(norm, p) for p in ["minimiza todo", "minimizame todo", "mostrame el escritorio", "ir al escritorio"]):
        res = system_control.minimize_all()
        return res.get("message", "Escritorio a la vista, papá.")

    if any(_mip(norm, p) for p in ["subi el volumen", "sube el volumen", "mas volumen"]):
        res = system_control.volume_up(15)
        return res.get("message", "Volumen arriba, papá.")

    if any(_mip(norm, p) for p in ["baja el volumen", "baja el volumen", "menos volumen"]):
        res = system_control.volume_down(15)
        return res.get("message", "Volumen bajado, che.")

    if any(_mip(norm, p) for p in ["silencio", "mute", "mutea", "silencia"]):
        res = system_control.mute()
        return res.get("message", "Audio muteado.")

    # 6b. CONTROL MULTIMEDIA (PLAY, PAUSA, PARAR, SIGUIENTE, ANTERIOR)
    # Acciones para DETENER / CERRAR completamente YouTube/Brave:
    if any(_mip(norm, p) for p in [
        "para la musica", "pará la musica", "corta la musica", "cortá la musica",
        "para el video", "pará el video", "corta el video", "cortá el video",
        "detener video", "detener el video", "detene el video", "detené el video",
        "apaga la musica", "apagá la musica", "cerra youtube", "cerrá youtube", "cerrar youtube",
        "cerra brave", "cerrá brave", "cerrar brave", "cerrar musica", "cerra musica", "cerrá la musica",
        "detener la musica", "detene la musica", "detené la musica"
    ]):
        res = system_control.stop_music()
        return res.get("message", "Listo, cerré Brave y la música.")

    # Acciones para PAUSAR / REANUDAR (afectan a Brave sin despausar Chrome):
    if any(_mip(norm, p) for p in [
        "pone pausa", "poné pausa", "pausa", "pausar", "pausalo", "pausala", "ponele pausa", "ponéle pausa",
        "dale play", "play", "reanudar", "continua", "continuar", "despausa", "despausar", "pone play", "poné play",
        "frena la musica", "frená la musica", "frena", "frená", "frenalo", "frenálo", "paralo", "parálo", "detener", "detene", "detené", "stop"
    ]):
        res = system_control.media_play_pause()
        return res.get("message", "Play/Pausa enviado, che.")

    if any(_mip(norm, p) for p in ["siguiente tema", "siguiente cancion", "pasa de tema", "pasa la cancion", "otro tema", "siguiente pista", "siguiente", "cambia de tema", "cambiá de tema"]):
        res = system_control.media_next()
        return "Puse el tema siguiente, crack."

    if any(_mip(norm, p) for p in ["tema anterior", "cancion anterior", "anterior tema", "volver al tema anterior", "anterior pista", "cancion previa", "tema previo"]):
        res = system_control.media_prev()
        return "Volví al tema anterior."

    if any(_mip(norm, p) for p in ["que cancion es", "que cancion está sonando", "que tema es", "que tema esta sonando", "que esta sonando", "que musica esta sonando", "como se llama este tema", "como se llama esta cancion"]):
        res = system_control.get_current_song()
        return res.get("message", "No pude identificar qué tema está sonando ahora, che.")

    # Configuración de reproductor predeterminado
    if any(_mip(norm, p) for p in ["usa spotify por defecto", "usá spotify por defecto", "spotify por defecto", "spotify como predeterminado", "pone la musica en spotify", "poné la musica en spotify"]):
        config.set_default_music_player("spotify")
        return "Listo, fiera: de ahora en más reproduzco toda la música en Spotify."

    if any(_mip(norm, p) for p in ["usa youtube por defecto", "usá youtube por defecto", "youtube por defecto", "youtube como predeterminado", "pone la musica en youtube", "poné la musica en youtube"]):
        config.set_default_music_player("youtube")
        return "Listo, fiera: de ahora en más reproduzco toda la música en YouTube."


def handle_youtube(engine, text, clean, norm) -> "Optional[str]":
    """7. REPRODUCCIÓN O APERTURA DE YOUTUBE (Brave / YouTube App)."""
    is_yt = "youtube" in norm
    is_sp = "spotify" in norm
    is_music_request = (
        any(norm.startswith(p) for p in [
            "pone el tema", "poné el tema", "pon el tema",
            "pone la cancion", "poné la cancion", "pon la cancion",
            "pone la cumbia", "poné la cumbia", "pon la cumbia",
            "pone musica", "poné musica", "pon musica",
            "pone un tema", "poné un tema", "pon un tema",
            "reproduci el tema", "reproducí el tema", "reproduci la cancion", "reproducí la cancion",
            "escuchar el tema", "escucha el tema", "escuchar la cancion", "escucha la cancion"
        ])
        or any(_mip(norm, k) for k in ["cumbia de los trapos", "entre el cielo vos y yo"])
        or ((norm.startswith("pone ") or norm.startswith("poné ") or norm.startswith("pon ") or norm.startswith("reproduci ") or norm.startswith("reproducí "))
            and any(_mip(norm, g) for g in ["cumbia", "cancion", "tema", "musica", "rock", "trap", "rap", "cuarteto", "reggaeton"]))
    )

    if is_yt or (is_music_request and config.default_music_player != "spotify" and not is_sp):
        yt_lnk = r"C:\Users\Exevaz27\Desktop\YouTube.lnk"
        import os
        # Si solo pide abrir YouTube sin especificar tema o canción
        if any(_mip(norm, w) for w in ["abri youtube", "abrir youtube", "pone youtube", "iniciar youtube"]) and not any(_mip(norm, k) for k in ["pone en youtube", "reproduci", "tema", "cancion", "video", "musica"]):
            if os.path.exists(yt_lnk):
                os.startfile(yt_lnk)
                return "Ahí te abrí la app de YouTube, fiera."
            if os.name != 'nt':
                # B-2: en el servidor Linux (DDR3) el .lnk de Windows no existe; se abre YouTube
                # en la PC vía satélite RPC (open_web_service). Si el satélite no está conectado,
                # open_web_service devuelve un aviso honesto en vez de tragar el pedido en silencio.
                res = system_control.open_web_service("youtube")
                return res.get("message", "Ahí te abrí YouTube, fiera.")

        yt_query = norm
        for phrase in [
            "pone en youtube", "poné en youtube", "pon en youtube", "poneme en youtube", "poner en youtube",
            "reproducir en youtube", "reproduci en youtube", "reproducí en youtube", "reproducime en youtube",
            "buscar en youtube", "busca en youtube", "buscá en youtube", "buscame en youtube", "en youtube",
            "de youtube", "por youtube", "youtube"
        ]:
            yt_query = yt_query.replace(phrase, "")
        yt_query = yt_query.strip()
        for p in ["el titan", "titan", "che titan", "che", "abri youtube", "abrir youtube", "eu titan", "ey titan", "oye titan"]:
            if yt_query.startswith(p):
                yt_query = yt_query[len(p):].strip()
        for start_word in [
            "pone", "poné", "pon", "poner", "poneme", "ponéme",
            "reproducir", "reproduci", "reproducí", "reproducime",
            "buscar", "busca", "buscá", "buscame",
            "escuchar", "escucha", "toca", "tocá",
            "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
            "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
        ]:
            if yt_query.startswith(start_word + " "):
                yt_query = yt_query[len(start_word):].strip()

        if yt_query:
            res = system_control.play_youtube(yt_query)
            return res.get("message", f"Ahí te puse {yt_query} en YouTube con Brave.")
        elif os.path.exists(yt_lnk):
            os.startfile(yt_lnk)
            return "Ahí te abrí la app de YouTube, fiera."
        elif os.name != 'nt':
            # B-2: mismo caso en el servidor Linux (DDR3): YouTube se abre en la PC vía satélite RPC.
            res = system_control.open_web_service("youtube")
            return res.get("message", "Ahí te abrí YouTube, fiera.")

    elif is_music_request and config.default_music_player == "spotify" and not is_yt:
        music_query = norm
        for p in ["el titan", "titan", "che titan", "che", "eu titan", "ey titan", "oye titan"]:
            if music_query.startswith(p):
                music_query = music_query[len(p):].strip()
        for start_word in [
            "pone", "poné", "pon", "poner", "poneme", "ponéme",
            "reproducir", "reproduci", "reproducí", "reproducime",
            "buscar", "busca", "buscá", "buscame",
            "escuchar", "escucha", "toca", "tocá",
            "el tema de", "el tema del", "el tema", "la cancion de", "la cancion del", "la cancion",
            "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
        ]:
            if music_query.startswith(start_word + " "):
                music_query = music_query[len(start_word):].strip()
        res = system_control.play_spotify(music_query)
        return res.get("message", f"Ahí te puse {music_query} en Spotify.")


def handle_spotify(engine, text, clean, norm) -> "Optional[str]":
    """8. REPRODUCCIÓN / BÚSQUEDA EN SPOTIFY."""
    # (OJO: "cerra spotify" NO es un pedido de música. Si la frase trae
    # verbo de cierre + spotify, se excluye para que caiga a Gemini, que
    # lo resuelve con kill_process + confirmación. Antes caía acá y
    # play_spotify("cerra") ponía cualquier tema al azar.)
    _pide_cerrar_spotify = "spotify" in norm and re.search(
        r"\b(cerra\w*|cierra|cierres?|apaga\w*|mata\w*)", norm
    )
    if "spotify" in norm and not _pide_cerrar_spotify:
        sp_query = norm
        for phrase in [
            "pone en spotify", "poné en spotify", "pon en spotify", "poneme en spotify", "ponéme en spotify",
            "reproducir en spotify", "reproduci en spotify", "reproducí en spotify", "reproducime en spotify",
            "buscar en spotify", "busca en spotify", "buscá en spotify", "buscame en spotify",
            "abrir spotify y poner", "abrí spotify y poné", "abri spotify y pone", "abrir spotify", "abrí spotify", "abri spotify",
            "escuchar en spotify", "escucha en spotify", "en spotify", "de spotify", "por spotify", "spotify"
        ]:
            sp_query = sp_query.replace(phrase, " ")
        sp_query = " ".join(sp_query.split()).strip()

        for p in ["el titan", "titan", "che titan", "che", "eu titan", "ey titan", "oye titan"]:
            if sp_query.startswith(p):
                sp_query = sp_query[len(p):].strip()

        changed = True
        while changed:
            changed = False
            for start_word in [
                "pone", "poné", "pon", "poner", "poneme", "ponéme",
                "reproducir", "reproduci", "reproducí", "reproducime",
                "toca", "tocá", "tocame", "tocáme",
                "escuchar", "escucha", "buscar", "busca", "buscá",
                "una cancion de", "una cancion del", "una canción de", "una canción del",
                "un tema de", "un tema del", "un tema", "una cancion", "una canción",
                "el tema de", "el tema del", "el tema",
                "la cancion de", "la cancion del", "la cancion",
                "la canción de", "la canción del", "la canción",
                "la musica de", "la musica del", "la musica", "musica", "del", "de", "el", "la", "a"
            ]:
                if sp_query.startswith(start_word + " "):
                    sp_query = sp_query[len(start_word):].strip()
                    changed = True
                    break

        res = system_control.play_spotify(sp_query)
        return res.get("message", f"Ahí te puse {sp_query} en Spotify.")
