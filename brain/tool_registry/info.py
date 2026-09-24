"""Herramientas de información: clima, fútbol, web, YouTube, Spotify."""

from tools.system_control import system_control



def get_weather(city: str = "Buenos Aires") -> str:

    """Consulta el pronóstico y clima actual de cualquier ciudad (temperatura, lluvia, viento)."""

    res = system_control.get_weather(city)

    return res.get("message", str(res))


def get_soccer_info(query: str = "", team: str = "", date: str = "") -> str:

    """Fútbol de cualquier equipo EXCEPTO Boca Juniors (para TODO lo de Boca usá SIEMPRE get_boca_juniors_info, nunca esta herramienta) y EXCEPTO fixture/resultados/formaciones de equipos argentinos mapeados (para esos usá SIEMPRE get_fotmob_team_info). Pasá la pregunta COMPLETA en 'query' (ejemplo: query='Cuándo juega River'); 'team' es opcional y solo desambigua el equipo; 'date' solo para un partido de una fecha puntual. Resuelve internamente qué fuente usar: otros equipos o finales históricas por ficha oficial de ESPN; y como último recurso, búsqueda web. Llamá a esta herramienta una sola vez por pregunta: ella elige la fuente, no llames a search_web en paralelo para lo mismo."""

    res = system_control.get_soccer_info(query=query, team=team, date=date)

    return res.get("results", str(res))


def get_fotmob_team_info(query: str = "", team: str = "") -> str:

    """Es la ÚNICA herramienta para fixture, resultados y formaciones de los equipos argentinos mapeados en FotMob: River, Racing, Independiente, San Lorenzo, Vélez, Huracán, Estudiantes, Lanús, Rosario Central, Argentinos Juniors, Banfield, Colón, Platense, Instituto, Belgrano, Chacarita, Atlético Rafaela, Nueva Chicago y Gimnasia Jujuy (próximo partido, agenda futura / partido después del próximo, último resultado, 11 titular, 'la ida'). Para TODO lo de estos equipos usá SIEMPRE esta herramienta y nunca get_soccer_info, search_web ni get_soccer_match_sheet. Para Boca Juniors usá SIEMPRE get_boca_juniors_info. Para DT, noticias o historia de estos equipos usá get_soccer_info. Pasá la pregunta completa en 'query' ('team' es opcional y solo desambigua)."""

    res = system_control.get_fotmob_team_info(query=query, team=team)

    return res.get("results", str(res))


def search_web(query: str = "") -> str:

    """Busca en internet en tiempo real (Google / Bing / ESPN / Wikipedia) para verificar cualquier información actual o deportiva del mundo: partidos de fútbol pasados o recientes (resultados, ficha técnica y formación titular oficial del 11 con suplentes de cualquier fecha o rival), directores técnicos de cualquier club, fichajes, noticias de hoy, personas, autoridades, cotizaciones, historia y cualquier hecho fáctico. Para TODO lo de Boca Juniors (fixture, formaciones, resultados) usá get_boca_juniors_info, no esta herramienta."""

    res = system_control.search_web(query)

    return res.get("results", str(res))


def get_boca_juniors_info(topic: str = "todo") -> str:

    """Es la ÚNICA herramienta para todo lo de Boca Juniors (no uses get_soccer_info ni search_web para Boca). Consulta en tiempo real: fixture y próximo partido oficial confirmado (cuándo juega, fecha, hora, rival, estadio, torneo y alineación), agenda de próximos partidos (para 'después del de hoy' / 'el del finde' / 'el siguiente'), último partido jugado, Y partidos anteriores específicos: la ida/vuelta de una llave (ej. 'el 11 de la ida vs San Pablo'), la formación titular de un partido pasado contra un rival nombrado, o cómo salió un partido anterior. Para partidos de hace más de ~4 meses, usá search_web."""

    res = system_control.get_boca_juniors_info(topic)

    return res.get("results", str(res))


def play_youtube(query: str) -> str:

    """Busca y reproduce inmediatamente una canción, video o artista en YouTube en la computadora."""

    res = system_control.play_youtube(query)

    return res.get("message", str(res))


def play_spotify(query: str = "") -> str:

    """Busca y reproduce inmediatamente una canción, artista, álbum o playlist en Spotify en la computadora."""

    res = system_control.play_spotify(query)

    return res.get("message", str(res))


def get_current_song() -> str:

    """Obtiene el nombre de la canción o artista que está reproduciéndose actualmente en Spotify."""

    res = system_control.get_current_song()

    return res.get("message", str(res))


def empty_recycle_bin() -> str:

    """Vacía la papelera de reciclaje de Windows por completo."""

    from brain.local_intents import local_intents
    return local_intents.request_confirmation("empty_recycle_bin")


def search_google(query: str) -> str:

    """Abre el navegador predeterminado y busca una consulta directamente en Google."""

    res = system_control.search_google(query)

    return res.get("message", str(res))


def open_web_service(service: str) -> str:

    """Abre un servicio web popular en el navegador como 'whatsapp', 'mercadolibre', 'gmail', 'reddit' o 'twitter'."""

    res = system_control.open_web_service(service)

    return res.get("message", str(res))
