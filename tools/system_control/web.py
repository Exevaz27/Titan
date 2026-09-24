"""Mixin web: clima, búsquedas, YouTube y servicios."""

from core.logger import log_info, log_warning

import ctypes


import os



from core.state_manager import state_mgr, AssistantState


from ._common import _timed

from core.process_utils import popen_silent

from typing import Any, Dict


class WebMixin:

    def get_weather(self, city: str = "Buenos Aires") -> Dict[str, Any]:
        """Consulta el clima y pronóstico actual en tiempo real para cualquier ciudad de Argentina o del mundo"""
        import urllib.request
        import urllib.parse
        import json
        
        coords = {
            "buenos aires": (-34.6118, -58.4173),
            "cordoba": (-31.4201, -64.1888),
            "rosario": (-32.9468, -60.6393),
            "mendoza": (-32.8908, -68.8272),
            "la plata": (-34.9214, -57.9545),
            "mar del plata": (-38.0055, -57.5562),
            "salta": (-24.7859, -65.4117),
            "tucuman": (-26.8241, -65.2226)
        }
        
        c_clean = city.lower().strip()
        # B-20: antes, si la ciudad no estaba en el diccionario y el geocoding
        # fallaba, se seguía con las coords de Buenos Aires pero el mensaje
        # decía "En {city}...": mentía con confianza. Ahora el nombre que se
        # informa es siempre el de las coordenadas que se usaron, y si no se
        # pudo ubicar la ciudad se devuelve un error honesto.
        resolved_name = city.strip() or "Buenos Aires"
        lat, lon = coords.get(c_clean, (None, None))

        if lat is None:
            try:
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city.strip())}&count=1&language=es&format=json"
                req = urllib.request.Request(geo_url, headers={'User-Agent': 'CheAsistente/1.0'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    geo_data = json.loads(resp.read().decode('utf-8'))
                    results = geo_data.get("results") or []
                    if not results:
                        return {"status": "error",
                                "message": f"No encontré ninguna ciudad llamada '{city.strip()}'. ¿Me la repetís?"}
                    lat = results[0]["latitude"]
                    lon = results[0]["longitude"]
                    resolved_name = results[0].get("name") or resolved_name
            except Exception:
                return {"status": "error",
                        "message": f"No pude ubicar '{city.strip()}' para el clima (falló la búsqueda). Probá de nuevo en un rato."}

        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            req = urllib.request.Request(url, headers={'User-Agent': 'CheAsistente/1.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                w = data.get("current_weather", {})
                temp = round(w.get("temperature", 0))
                wind = round(w.get("windspeed", 0))
                code = w.get("weathercode", 0)
                
                desc = "cielo despejado"
                if code in [1, 2, 3]: desc = "parcialmente nublado"
                elif code in [45, 48]: desc = "con neblina"
                elif code in [51, 53, 55, 61, 63, 65]: desc = "con lluvias aisladas"
                elif code in [80, 81, 82]: desc = "con chaparrones"
                elif code in [95, 96, 99]: desc = "con tormenta eléctrica"

                msg = f"En {resolved_name} tenemos {temp} grados, {desc}, y viento a {wind} kilómetros por hora."
                state_mgr.emit_tool_call("get_weather", {"city": resolved_name}, msg)
                return {"status": "success", "city": resolved_name, "temperature": temp, "description": desc, "wind_speed": wind, "message": msg}
        except Exception as e:
            return {"status": "error", "message": f"No pude consultar el clima: {e}"}

    @_timed
    def search_web(self, query: str = "") -> Dict[str, Any]:
        """Busca en internet información en tiempo real: próximos partidos, resultados deportivos, formaciones oficiales, noticias de hoy, etc."""
        import urllib.request
        import urllib.parse
        import xml.etree.ElementTree as ET
        import re
        import html
        import json
        from datetime import datetime, timedelta

        clean_q = (query or "").strip()
        if not clean_q:
            return {"status": "empty", "results": "No se especificó una consulta de búsqueda."}
        lower_q = clean_q.lower()
        now = datetime.now()

        # Si piden explícitamente y únicamente el próximo partido de Boca (cuándo juega Boca)
        is_fixture_request = any(k in lower_q for k in ["cuándo juega", "cuando juega", "a qué hora juega", "a que hora juega", "contra quién juega", "contra quien juega", "próximo partido", "proximo partido", "fixture de"])
        is_news_or_coach = any(k in lower_q for k in ["dt", "técnico", "tecnico", "entrenador", "presidente", "noticia", "refuerzo", "fichaje", "jugador", "quién", "quien", "por qué", "porque", "formación", "formacion", "titulares", "alineación", "alineacion"])

        if is_fixture_request and not is_news_or_coach:
            if any(k in lower_q for k in ["boca", "xeneize", "bombonera"]) and "superclásico" not in lower_q and "superclasico" not in lower_q:
                boca_res = self.get_boca_juniors_info(clean_q)
                return boca_res
            if any(k in lower_q for k in ["river", "superclásico", "superclasico", "racing", "san lorenzo", "independiente", "velez", "huracan"]):
                try:
                    soccer_data = self._get_argentine_soccer_fixture(clean_q)
                    if soccer_data:
                        state_mgr.emit_tool_call("search_web", {"query": clean_q}, "Fixture oficial consultado")
                        return {"status": "success", "results": soccer_data}
                except Exception:
                    pass

        results = []

        # 1. Fútbol: Partidos, resultados pasados, fichas técnicas y formaciones titulares oficiales (ESPN / FotMob)
        hist_lg, hist_dt = self._get_historical_final_dates(clean_q)
        is_historic = any(yr in lower_q for yr in ["2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017", "2016", "2015", "2007", "2000", "año pasado", "ano pasado", "año anterior"])
        is_soccer = hist_lg is not None or any(w in lower_q for w in [
            "partido", "jugó", "jugo", "juega", "boca", "river", "san pablo", "sao paulo",
            "racing", "independiente", "san lorenzo", "sudamericana", "libertadores", "mundial",
            "formación", "formacion", "alineación", "alineacion", "titulares", "once", "11",
            "quiénes jugaron", "quienes jugaron", "cómo formó", "como formo", "gol", "goles", "resultado"
        ])

        if is_soccer:
            # Si es una final histórica detectada, consultar inmediatamente la ficha oficial de ESPN
            if hist_lg and hist_dt:
                try:
                    sheet = self.get_soccer_match_sheet(clean_q, target_date=hist_dt, specific_league=hist_lg)
                    if sheet:
                        results.append(sheet)
                except Exception as e:
                    log_warning(f"Error consultando final histórica en search_web: {e}")

            elif any(k in lower_q for k in ["boca", "xeneize"]) and not is_historic:
                try:
                    fotmob_data = self._get_fotmob_boca_data()
                    is_last_match_q = any(k in lower_q for k in ["último", "ultimo", "pasado", "ayer", "anoche", "cómo salió", "como salio", "resultado", "ganó", "gano", "perdió", "perdio", "goles"])
                    is_next_match_q = any(k in lower_q for k in ["hoy", "esta noche", "próximo", "proximo", "cuándo", "cuando", "a qué hora", "a que hora"])

                    if (is_last_match_q or not is_next_match_q) and fotmob_data.get("last_match"):
                        lm = fotmob_data["last_match"]
                        lm_txt = [f"[FICHA OFICIAL DE FOTMOB - ÚLTIMO PARTIDO]:"]
                        lm_txt.append(f"- Partido: {lm['match']} ({lm['tournament']})")
                        lm_txt.append(f"- Disputado: {lm['display_date']}")
                        if lm.get('pageUrl'):
                            lu = self._get_fotmob_match_lineup(lm['pageUrl'])
                            if lu.get('goals'):
                                lm_txt.append(f"- Goles: {', '.join(lu['goals'])}")
                            if lu.get('starters'):
                                coach_t = f" - DT {lu['coach']}" if lu.get('coach') else ""
                                lm_txt.append(f"- 11 Titular oficial (Esquema {lu.get('formation', '')}{coach_t}):\n  {', '.join(lu['starters'])}")
                            if lu.get('subs'):
                                lm_txt.append(f"- Suplentes: {', '.join(lu['subs'][:8])}...")
                        results.append("\n".join(lm_txt))

                    if (is_next_match_q or "formación" in lower_q or "alineación" in lower_q) and fotmob_data.get("next_match"):
                        nm = fotmob_data["next_match"]
                        nm_txt = [f"[FICHA OFICIAL DE FOTMOB - PRÓXIMO PARTIDO]:"]
                        nm_txt.append(f"- Partido: Boca Juniors vs {nm['rival']} ({nm['tournament']})")
                        nm_txt.append(f"- Cuándo: {nm['display_date']} ({nm['condition']})")
                        if nm.get('pageUrl'):
                            lu = self._get_fotmob_match_lineup(nm['pageUrl'])
                            if lu.get('starters'):
                                if lu.get('is_confirmed'):
                                    coach_t = f" - DT {lu['coach']}" if lu.get('coach') else ""
                                    nm_txt.append(f"- 11 Titular oficial confirmado (Esquema {lu.get('formation', '')}{coach_t}):\n  {', '.join(lu['starters'])}")
                                else:
                                    prob_11 = self._get_boca_probable_lineup()
                                    if prob_11:
                                        nm_txt.append(f"- Formación: Planilla oficial pendiente (sale 1 hora antes). Novedades de Ezeiza: {prob_11}")
                                    else:
                                        nm_txt.append("- Formación: Planilla oficial pendiente (se confirma 1 hora antes en el vestuario).")
                            if lu.get('subs') and lu.get('is_confirmed'):
                                nm_txt.append(f"- Suplentes: {', '.join(lu['subs'][:8])}...")
                        results.append("\n".join(nm_txt))
                except Exception as e:
                    log_warning(f"Error consultando FotMob en search_web: {e}")

            else:
                team_match = "Boca"
                if "river" in lower_q: team_match = "River"
                elif "racing" in lower_q: team_match = "Racing"
                elif "san lorenzo" in lower_q: team_match = "San Lorenzo"
                elif "independiente" in lower_q: team_match = "Independiente"
                elif "argentina" in lower_q: team_match = "Argentina"
                elif "francia" in lower_q or "france" in lower_q: team_match = "Francia"
                elif "real madrid" in lower_q: team_match = "Real Madrid"
                elif "fluminense" in lower_q: team_match = "Fluminense"

                dias_semana = {
                    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
                    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
                }
                target_dt = None
                for d_nom, d_num in dias_semana.items():
                    if f"el {d_nom}" in lower_q or d_nom in lower_q:
                        diff = (now.weekday() - d_num) % 7
                        if diff == 0 and "pasado" in lower_q:
                            diff = 7
                        target_dt = now - timedelta(days=diff)
                        break
                if not target_dt:
                    if "ayer" in lower_q or "anoche" in lower_q:
                        target_dt = now - timedelta(days=1)
                    elif "el finde" in lower_q or "el fin de semana" in lower_q:
                        diff = (now.weekday() - 6) % 7
                        if diff == 0:
                            diff = 7
                        target_dt = now - timedelta(days=diff)

                try:
                    sheet = self.get_soccer_match_sheet(team_match, target_dt)
                    if sheet:
                        results.append(sheet)
                except Exception:
                    pass

        # 2. Google News RSS Argentina (noticias ultra frescas en tiempo real)
        try:
            url_news = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_q)}&hl=es-419&gl=AR&ceid=AR:es-419"
            req_news = urllib.request.Request(url_news, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req_news, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                items = root.findall(".//item")
                for it in items[:4]:
                    t = it.find("title").text if it.find("title") is not None else ""
                    clean_t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
                    desc = it.find("description").text if it.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_t:
                        results.append(f"[NOTICIA RECIENTE]: {clean_t} | Detalle: {clean_desc[:250]}")
        except Exception:
            pass

        # 3. Bing News RSS (titulares en tiempo real, marcadores de partidos y coberturas sin bloqueo)
        try:
            url_bing = f"https://www.bing.com/news/search?q={urllib.parse.quote(clean_q)}&format=rss"
            req_bing = urllib.request.Request(url_bing, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req_bing, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                raw_items = root.findall(".//item")
                prio_words = ['ganó', 'gano', 'venció', 'vencio', 'perdió', 'perdio', 'empató', 'empato', 'goles', 'gol', '1-0', '1 a 0', '2-0', '2-1', '0-0', 'triunfo', 'derrota', 'asumió', 'asumio', 'renunció', 'renuncio', 'interino']
                def _prio(it):
                    t_str = (it.find('title').text or '').lower()
                    d_str = (it.find('description').text or '').lower()
                    return -sum(1 for w in prio_words if w in t_str or w in d_str)
                sorted_items = sorted(raw_items, key=_prio)
                for it in sorted_items[:4]:
                    t = it.find("title").text if it.find("title") is not None else ""
                    clean_t = re.sub(r'\s*-\s*[^-]+$', '', t).strip()
                    desc = it.find("description").text if it.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_t:
                        results.append(f"[INFORMACIÓN WEB EN VIVO]: {clean_t} | Detalle: {clean_desc[:250]}")
        except Exception:
            pass

        # 4. Wikipedia para datos enciclopédicos, biografías o eventos históricos pasados
        if is_historic or any(w in lower_q for w in ["quién es", "quien es", "qué es", "que es", "historia", "biografía", "biografia", "presidente", "gobernador", "ministro", "mundial", "final"]) or len(results) < 2:
            try:
                url_wiki = f"https://es.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q)}&utf8=&format=json"
                req_wiki = urllib.request.Request(url_wiki, headers={"User-Agent": "TitanAssistant/1.0 (exevaz27)"})
                with urllib.request.urlopen(req_wiki, timeout=3.0) as r_w:
                    d_w = json.loads(r_w.read().decode("utf-8"))
                    s_items = d_w.get("query", {}).get("search", [])
                    if s_items:
                        top_it = s_items[0]
                        w_title = top_it.get("title", "")
                        url_ext = f"https://es.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(w_title)}&format=json"
                        req_ext = urllib.request.Request(url_ext, headers={"User-Agent": "TitanAssistant/1.0 (exevaz27)"})
                        with urllib.request.urlopen(req_ext, timeout=3.0) as r_ext:
                            d_ext = json.loads(r_ext.read().decode("utf-8"))
                            pages = d_ext.get("query", {}).get("pages", {})
                            for pid, pdata in pages.items():
                                ext = pdata.get("extract", "")
                                clean_ext = ext.replace('\u200b', '').strip()
                                if clean_ext:
                                    results.append(f"[ENCICLOPEDIA WIKIPEDIA - {w_title}]:\n{clean_ext[:500]}")
            except Exception:
                pass

        if results:
            result_text = "\n\n".join(results)
            state_mgr.emit_tool_call("search_web", {"query": clean_q}, f"Búsqueda web completada: {clean_q}")
            return {"status": "success", "results": result_text}
        return {"status": "empty", "results": "No se encontraron resultados específicos en la web."}

    def close_existing_youtube_windows(self):
        """Cierra cualquier ventana previa de YouTube en Brave para que las canciones no se reproduzcan encima."""
        try:
            import ctypes
            from ctypes import wintypes
            import psutil
            user32 = ctypes.windll.user32
            curr = 0
            while True:
                curr = user32.FindWindowExW(0, curr, "Chrome_WidgetWin_1", None)
                if not curr:
                    break
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(curr, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    if "brave" in p.name().lower():
                        length = user32.GetWindowTextLengthW(curr)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(curr, buf, length + 1)
                            t = buf.value.lower()
                            # B-25: antes era `"youtube" in t or "brave" in t` y como
                            # todo título de Brave termina en "- Brave", cerraba
                            # TODAS las ventanas de Brave aunque no fueran YouTube.
                            if "youtube" in t:
                                user32.PostMessageW(curr, 0x0010, 0, 0)  # WM_CLOSE
                except Exception:
                    pass
        except Exception:
            pass

    def _open_url_in_brave(self, url: str) -> bool:
        """Abre una URL explícitamente en Brave, nunca en el navegador por defecto.

        En la PC de Exequiel el navegador por defecto puede ser Chrome; YouTube
        (y la música) tienen que abrirse siempre en Brave. Retorna True si logró
        lanzar Brave. Solo tiene efecto real en Windows.
        """
        if os.name != 'nt':
            return False
        brave_paths = [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
        ]
        brave_args = f'--new-window --autoplay-policy=no-user-gesture-required --enable-features=HardwareMediaKeyHandling "{url}"'
        for b_path in brave_paths:
            if os.path.exists(b_path):
                try:
                    # ShellExecuteW con SW_SHOWNORMAL (1) fuerza a Windows a mostrar la ventana en primer plano
                    ret = ctypes.windll.shell32.ShellExecuteW(
                        None, "open", b_path, brave_args, os.path.dirname(b_path), 1
                    )
                    if ret > 32:
                        log_info(f"URL abierta en primer plano con Brave (ShellExecuteW): {url}")
                        return True
                except Exception as b_err:
                    log_warning(f"Error abriendo con ShellExecuteW ({b_path}): {b_err}")
                try:
                    popen_silent(
                        [b_path, "--new-window", "--autoplay-policy=no-user-gesture-required", "--enable-features=HardwareMediaKeyHandling", url],
                        cwd=os.path.dirname(b_path)
                    )
                    log_info(f"URL abierta con Brave (popen_silent): {url}")
                    return True
                except Exception as b_err:
                    log_warning(f"Error abriendo con Brave ({b_path}): {b_err}")
        return False

    def play_youtube(self, query: str) -> Dict[str, Any]:
        """Busca y reproduce un video o canción en YouTube directamente en el navegador Brave en primer plano, reemplazando cualquier reproducción anterior."""
        import urllib.request
        import urllib.parse
        import re
        import webbrowser
        import os
        import subprocess
        import ctypes
        import time

        raw_q = query.strip()
        clean_q = raw_q

        # 1. Limpieza de saludos, nombres del asistente y prefijos
        prefixes = [
            "cuautitlan", "cuautitlán", "ehu titan", "ehu titán", "eu titan", "eu titán",
            "titan", "titán", "el titan", "el titán", "che titan", "che titán", "che", "eu", "eh", "ey",
            "pone en youtube", "poné en youtube", "pon en youtube", "poneme en youtube", "ponéme en youtube",
            "reproducir en youtube", "reproduci en youtube", "reproducí en youtube", "reproducime en youtube",
            "buscar en youtube", "busca en youtube", "buscá en youtube", "buscame en youtube", "abrir youtube", "abri youtube",
            "pone", "poné", "pon", "poneme", "ponéme", "reproducir", "reproduci", "reproducí", "reproducime",
            "toca", "tocá", "tocame", "tocáme", "escuchar", "escucha", "buscar", "busca", "buscá", "abrir", "abri",
            "poner", "cambia a", "cambiá a", "pone otra cancion", "poné otra cancion"
        ]

        low_q = clean_q.lower()
        # Limpiar prefijos de manera iterativa por si se combinan ("che titán pon...")
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

        # 2. Limpieza de sufijos ("en youtube", etc.)
        for suffix in ["en youtube", "de youtube", "por youtube", "youtube"]:
            if low_q.endswith(" " + suffix):
                clean_q = clean_q[:-len(suffix)-1].strip()
                low_q = clean_q.lower()
            elif low_q == suffix:
                clean_q = ""
                low_q = ""
                break

        # 3. Limpieza de rellenos iniciales ("el tema de", "la cancion de", etc.)
        fillers = [
            "el tema de", "el tema del", "la cancion de", "la canción de", "la cancion del", "la canción del",
            "el video de", "el video del", "el videoclip de", "el videoclip del",
            "la musica de", "la música de", "la musica del", "la música del",
            "un tema de", "un tema del", "una cancion de", "una canción de", "una cancion del", "una canción del",
            "el tema", "la cancion", "la canción", "el video", "la musica", "la música",
            "un tema", "una cancion", "una canción", "del", "de", "el", "la"
        ]
        for f in fillers:
            if low_q.startswith(f + " "):
                clean_q = clean_q[len(f):].strip()
                low_q = clean_q.lower()
                break

        if not clean_q:
            clean_q = raw_q

        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Poniendo en YouTube: {clean_q}")

        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_q)}"
        target_url = search_url

        try:
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "es-419,es;q=0.9,en;q=0.8"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                html_content = response.read().decode("utf-8", errors="ignore")
                # 1ra opción: buscar videoId dentro de videoRenderer (videos musicales reales, descartando anuncios/noticias)
                video_ids = re.findall(r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', html_content)
                if not video_ids:
                    video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html_content)
                if not video_ids:
                    video_ids = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html_content)
                
                if video_ids:
                    selected_id = video_ids[0]
                    target_url = f"https://www.youtube.com/watch?v={selected_id}&autoplay=1"
                    log_info(f"Video ID de YouTube resuelto con éxito: {selected_id}")
        except Exception as e:
            log_warning(f"Error resolviendo ID de YouTube ({clean_q}): {e}")

        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux(
                "play_youtube",
                {"query": clean_q, "url": target_url},
                f"Reproduciendo '{clean_q}' en YouTube en la compu."
            )
            if remote_res:
                return remote_res

        # 4. REEMPLAZO LIMPIO: cortar sonido anterior y cerrar ventana previa de YouTube
        self.close_existing_youtube_windows()
        time.sleep(0.35)

        opened = self._open_url_in_brave(target_url)

        # Asegurar que el audio de la nueva canción esté habilitado y no herede mute
        def _unmute_watcher():
            import time
            for _ in range(12):
                time.sleep(0.5)
                try:
                    from pycaw.pycaw import AudioUtilities
                    for s in AudioUtilities.GetAllSessions():
                        if s.Process and "brave" in s.Process.name().lower():
                            if s.SimpleAudioVolume.GetMute():
                                s.SimpleAudioVolume.SetMute(0, None)
                except Exception:
                    pass
        import threading
        threading.Thread(target=_unmute_watcher, daemon=True).start()

        if not opened:
            try:
                webbrowser.open(target_url)
            except Exception:
                try:
                    ctypes.windll.shell32.ShellExecuteW(None, "open", target_url, None, None, 1)
                except Exception:
                    pass

        # Intentar restaurar y traer la ventana de Brave al frente si estaba minimizada
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            def enum_wnd(hwnd, _):
                if user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        t = buf.value.lower()
                        if "brave" in t or "youtube" in t:
                            user32.ShowWindow(hwnd, 9) # SW_RESTORE
                            user32.SwitchToThisWindow(hwnd, True)
                            user32.SetForegroundWindow(hwnd)
                            user32.BringWindowToTop(hwnd)
                return True
            cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_wnd)
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

        msg = f"Reproduciendo '{clean_q}' en YouTube."
        state_mgr.emit_tool_call("play_youtube", {"query": clean_q, "url": target_url}, msg)
        log_info(f"YouTube reproducido: {target_url}")
        return {"status": "success", "message": msg, "url": target_url}

    def search_google(self, query: str) -> Dict[str, Any]:
        """Busca directamente una consulta en Google en el navegador predeterminado"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("search_google", {"query": query}, f"Busqué '{query}' en Google en la compu.")
            if remote_res:
                return remote_res
        import webbrowser, urllib.parse
        clean_q = query.strip()
        url = f"https://www.google.com/search?q={urllib.parse.quote(clean_q)}"
        webbrowser.open(url)
        msg = f"Buscando '{clean_q}' en Google."
        state_mgr.emit_tool_call("search_google", {"query": clean_q}, msg)
        return {"status": "success", "message": msg, "url": url}

    def open_web_service(self, service: str) -> Dict[str, Any]:
        """Abre servicios web directos como WhatsApp, Mercado Libre, Gmail o YouTube"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("open_web_service", {"service": service}, f"Abrí {service} en la compu.")
            if remote_res:
                return remote_res
        import webbrowser
        urls = {
            "whatsapp": "https://web.whatsapp.com",
            "mercadolibre": "https://www.mercadolibre.com.ar",
            "gmail": "https://mail.google.com",
            "reddit": "https://www.reddit.com",
            "twitter": "https://twitter.com",
            "youtube": "https://www.youtube.com",
        }
        key = service.lower().strip()
        target_url = urls.get(key)
        if target_url is None:
            # S-9: sin fallback a https://www.{service}.com. Un error de
            # tipeo por voz ("abrí spotifi") abría un dominio arbitrario
            # que cualquiera puede registrar (typosquatting).
            known = ", ".join(sorted(urls))
            msg = f"No tengo registrado el servicio '{service}'. Los que conozco son: {known}."
            return {"status": "error", "message": msg}
        if key == "youtube":
            # YouTube SIEMPRE en Brave, nunca en el navegador por defecto (podría ser Chrome)
            if self._open_url_in_brave(target_url):
                msg = "Abriendo Youtube en Brave."
                state_mgr.emit_tool_call("open_web_service", {"service": service, "url": target_url, "browser": "brave"}, msg)
                return {"status": "success", "message": msg, "url": target_url, "browser": "brave"}
            log_warning("[open_web_service] No se encontró Brave; se abre YouTube con el navegador por defecto.")
        webbrowser.open(target_url)
        msg = f"Abriendo {service.capitalize()}."
        state_mgr.emit_tool_call("open_web_service", {"service": service, "url": target_url}, msg)
        return {"status": "success", "message": msg, "url": target_url}
