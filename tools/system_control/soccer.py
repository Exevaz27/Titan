"""Mixin de fútbol: FotMob, ESPN y Boca."""

from core.logger import log_info, log_warning



from core.state_manager import state_mgr


from ._common import _timed

from typing import Any, Dict

# NOTA: los atributos de clase viven en el mixin; la clase final los hereda.


class SoccerMixin:
    # Mapa de equipos -> ID de FotMob (descubiertos 2026-09-15).
    # FotMob no tiene búsqueda por nombre usable, así que cada equipo se registra una vez.
    # Formato: (id_fotmob, nombre_para_mostrar, clave_corta_para_detectar_localia, [alias_en_minusculas_sin_acentos])
    FOTMOB_TEAMS = [
        (10077, "Boca Juniors", "Boca", ["boca", "boca juniors", "xeneize", "xeneizes"]),
        (10076, "River Plate", "River", ["river", "river plate", "millonario", "millonarios"]),
        (10080, "Racing Club", "Racing", ["racing", "racing club", "academia"]),
        (10078, "Independiente", "Independiente", ["independiente", "rojo", "diablo"]),
        (10083, "San Lorenzo", "San Lorenzo", ["san lorenzo", "casla", "ciclon"]),
        (10079, "Vélez Sarsfield", "Vélez", ["velez", "velez sarsfield", "fortin"]),
        (10081, "Huracán", "Huracán", ["huracan", "globo"]),
        (10082, "Lanús", "Lanús", ["lanus", "granate"]),
        (10084, "Rosario Central", "Rosario Central", ["rosario central", "central", "canalla", "canallas"]),
        (10086, "Argentinos Juniors", "Argentinos", ["argentinos", "argentinos juniors", "bicho"]),
        (10087, "Banfield", "Banfield", ["banfield", "taladro"]),
        (10088, "Colón", "Colón", ["colon", "sabalero"]),
        (10089, "Platense", "Platense", ["platense", "calamar"]),
        (10090, "Instituto", "Instituto", ["instituto", "gloria"]),
        (10092, "Belgrano", "Belgrano", ["belgrano", "pirata", "celeste"]),
        (10093, "Chacarita Juniors", "Chacarita", ["chacarita", "funebrero"]),
        (10094, "Estudiantes", "Estudiantes", ["estudiantes", "pincha", "pincharrata"]),
        (10085, "Atlético Rafaela", "Rafaela", ["rafaela", "atletico rafaela"]),
        (10091, "Nueva Chicago", "Nueva Chicago", ["nueva chicago", "chicago", "torito"]),
        (10095, "Gimnasia Jujuy", "Gimnasia", ["gimnasia jujuy", "gimnasia de jujuy", "lobo jujeno"]),
    ]
    # Índice alias -> (id, display, match_key), con alias largos primero para que
    # "rosario central" gane sobre "central".
    _FOTMOB_ALIAS_INDEX = None


    @classmethod
    def _fotmob_alias_index(cls):
        if cls._FOTMOB_ALIAS_INDEX is None:
            idx = {}
            for tid, display, mkey, aliases in cls.FOTMOB_TEAMS:
                for a in aliases:
                    idx[a] = (tid, display, mkey)
            cls._FOTMOB_ALIAS_INDEX = idx
        return cls._FOTMOB_ALIAS_INDEX

    @classmethod
    def match_fotmob_team(cls, query: str):
        """Devuelve (id, display, match_key) del equipo de FotMob mencionado en la consulta,
        o None si no hay ninguno mapeado. Insensible a acentos y mayúsculas."""
        import unicodedata
        q = unicodedata.normalize("NFKD", query or "")
        q = "".join(c for c in q if not unicodedata.combining(c)).lower()
        best = None
        for alias, info in cls._fotmob_alias_index().items():
            if alias in q:
                if best is None or len(alias) > len(best[0]):
                    best = (alias, info)
        return best[1] if best else None

    def _get_argentine_soccer_fixture(self, query: str) -> str:
        """Consulta directamente la API deportiva de la Liga Argentina de Fútbol (ESPN) para datos exactos de partidos en paralelo"""
        import urllib.request
        import json
        from datetime import datetime, timedelta
        from concurrent.futures import ThreadPoolExecutor

        today = datetime.now()
        dates = [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(-1, 6)]

        def fetch_date(d: str):
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/arg.1/scoreboard?dates={d}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=2.5) as r:
                    data = json.loads(r.read().decode("utf-8"))
                    evs = []
                    for ev in data.get("events", []):
                        name = ev.get("name", "")
                        dt_raw = ev.get("date", "")
                        tz_conv = self._format_utc_to_argentina(dt_raw)
                        fecha_bonita = tz_conv.get('display', dt_raw)
                        comp = ev.get("competitions", [{}])[0]
                        status = comp.get("status", {}).get("type", {}).get("description", "")
                        venue = comp.get("venue", {})
                        stadium = venue.get("fullName", "Estadio a confirmar")
                        city = venue.get("address", {}).get("city", "")
                        loc_vis = []
                        for team in comp.get("competitors", []):
                            t_name = team.get("team", {}).get("displayName", "")
                            ha = "Local" if team.get("homeAway") == "home" else "Visitante"
                            loc_vis.append(f"{t_name} ({ha})")
                        cond_str = " vs ".join(loc_vis)
                        evs.append({
                            "name": name,
                            "date_str": fecha_bonita,
                            "status": status,
                            "stadium": stadium,
                            "city": city,
                            "condition": cond_str
                        })
                    return evs
            except Exception:
                return []

        try:
            with ThreadPoolExecutor(max_workers=5) as ex:
                results = list(ex.map(fetch_date, dates))
            matches = [ev for sub in results for ev in sub]
        except Exception:
            matches = []

        q_lower = query.lower()
        ignore_words = {"contra", "quien", "juega", "partido", "partidos", "domingo", "sabado", "fecha", "hora", "cuando", "cancha", "estadio", "donde", "local", "visitante", "juegan"}
        keywords = [w for w in q_lower.split() if len(w) > 3 and w not in ignore_words]
        if keywords:
            filtered = [m for m in matches if any(k in m["name"].lower() for k in keywords)]
        else:
            filtered = matches

        target = filtered if filtered else matches[:15]
        if target:
            lines = [f"- {m['name']}: {m['date_str']}. Cancha/Estadio: {m['stadium']} en {m['city']}. Condición: {m['condition']} (Estado: {m['status']})" for m in target]
            return "Fixture Oficial de la Liga Argentina:\n" + "\n".join(lines)
        return ""

    def _get_historical_final_dates(self, query: str):
        """Detecta finales históricas para consultar la fecha y torneo exacto en ESPN."""
        q = (query or "").lower()
        finals = [
            ({"libertadores", "2023"}, "conmebol.libertadores", "20231104"),
            ({"fluminense", "2023"}, "conmebol.libertadores", "20231104"),
            ({"madrid", "2018"}, "conmebol.libertadores", "20181209"),
            ({"river", "boca", "2018"}, "conmebol.libertadores", "20181209"),
            ({"libertadores", "2018"}, "conmebol.libertadores", "20181209"),
            ({"qatar", "2022"}, "fifa.world", "20221218"),
            ({"mundial", "2022"}, "fifa.world", "20221218"),
            ({"francia", "2022"}, "fifa.world", "20221218"),
            ({"copa america", "2021"}, "conmebol.america", "20210710"),
            ({"maracana", "2021"}, "conmebol.america", "20210710"),
            ({"copa america", "2024"}, "conmebol.america", "20240714"),
            ({"colombia", "2024"}, "conmebol.america", "20240714"),
            ({"champions", "2024"}, "uefa.champions", "20240601"),
            ({"champions", "2023"}, "uefa.champions", "20230610"),
            ({"champions", "2022"}, "uefa.champions", "20220528"),
        ]
        for keywords, league, date_str in finals:
            if all(k in q for k in keywords):
                return league, date_str
        return None, None

    @_timed
    def get_soccer_match_sheet(self, team_query: str = "Boca", target_date = None, specific_league: str = None) -> str:
        """Obtiene la ficha técnica oficial de ESPN (resultado, goles, 11 titular oficial y suplentes) para cualquier equipo o final histórica."""
        import urllib.request
        import json
        import time
        from datetime import datetime, timedelta
        import re

        t0 = time.time()
        
        # Detect historical finals if not specified
        hist_lg, hist_dt = self._get_historical_final_dates(team_query)
        if hist_lg and not specific_league:
            specific_league = hist_lg
        if hist_dt and not target_date:
            target_date = hist_dt

        leagues = [specific_league] if specific_league else [
            'conmebol.libertadores', 'arg.1', 'conmebol.sudamericana', 'arg.copa',
            'fifa.world', 'conmebol.america', 'uefa.champions', 'esp.1', 'eng.1', 'ita.1'
        ]
        
        now = datetime.now()
        if target_date:
            if isinstance(target_date, str):
                clean_d = re.sub(r'[^\d]', '', target_date)
                if len(clean_d) == 8:
                    dates_to_check = [clean_d]
                else:
                    dates_to_check = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]
            else:
                dates_to_check = [
                    target_date.strftime("%Y%m%d"),
                    (target_date + timedelta(days=1)).strftime("%Y%m%d"),
                    (target_date - timedelta(days=1)).strftime("%Y%m%d"),
                ]
        else:
            dates_to_check = [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]
            
        found_ev = None
        found_league = None
        
        # Clean keywords from team_query
        clean_team = team_query.lower()
        for w in ["formacion", "formación", "de", "del", "final", "vs", "contra", "alineacion", "alineación", "titulares", "once", "equipo", "partido"]:
            clean_team = clean_team.replace(w, " ")
        clean_team = clean_team.strip()
        if not clean_team:
            clean_team = team_query.lower()
        search_terms = [t for t in clean_team.split() if len(t) > 3]

        for d_str in dates_to_check:
            for lg in leagues:
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={d_str}"
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.81.0'})
                    with urllib.request.urlopen(req, timeout=3.0) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        for ev in data.get('events', []):
                            name = ev.get('name', '').lower()
                            if any(t in name for t in search_terms) or clean_team in name:
                                found_ev = ev
                                found_league = lg
                                break
                except Exception:
                    pass
                if found_ev:
                    break
            if found_ev:
                break
                
        if not found_ev:
            return ""
            
        event_id = found_ev.get('id')
        event_name = found_ev.get('name', '')
        
        url_sum = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{found_league}/summary?event={event_id}"
        try:
            req_sum = urllib.request.Request(url_sum, headers={'User-Agent': 'curl/7.81.0'})
            with urllib.request.urlopen(req_sum, timeout=3.5) as r:
                sum_data = json.loads(r.read().decode('utf-8'))
        except Exception:
            return ""
            
        header = sum_data.get('header', {})
        comp = header.get('competitions', [{}])[0]
        status = comp.get('status', {}).get('type', {}).get('description', '')
        
        teams = comp.get('competitors', found_ev.get('competitions', [{}])[0].get('competitors', []))
        score_lines = []
        for t in teams:
            score_lines.append(f"{t.get('team', {}).get('displayName', '')} {t.get('score', '0')}")
            
        goals = []
        for ev in sum_data.get('keyEvents', []):
            text = ev.get('text', '')
            clock = ev.get('clock', {}).get('displayValue', '')
            ev_type = ev.get('type', {}).get('text', '').lower()
            if 'goal' in ev_type:
                goals.append(f"{clock} {text}")
        if not goals:
            for d in sum_data.get('details', []):
                if d.get('type', {}).get('text') in ['Goal', 'Penalty - Scored']:
                    athlete = d.get('athletesInvolved', [{}])[0].get('displayName', '')
                    clock = d.get('clock', {}).get('displayValue', '')
                    team_g = d.get('team', {}).get('displayName', '')
                    if athlete:
                        goals.append(f"{athlete} ({clock}' - {team_g})")
                
        lineups_txt = []
        for roster in sum_data.get('rosters', []):
            tname = roster.get('team', {}).get('displayName', '')
            starters = [p.get('athlete', {}).get('displayName', '') for p in roster.get('roster', []) if p.get('starter', False)]
            subs = [p.get('athlete', {}).get('displayName', '') for p in roster.get('roster', []) if not p.get('starter', False)]
            if starters:
                lineups_txt.append(f"• 11 Titular oficial de {tname} ({len(starters)} jugadores):\n  {', '.join(starters)}")
            if subs:
                lineups_txt.append(f"• Suplentes de {tname}: {', '.join(subs[:8])}...")
                
        elapsed = time.time() - t0
        report = [f"[FICHA TÉCNICA OFICIAL EN VIVO - ESPN ({elapsed:.2f}s)]:"]
        report.append(f"- Partido: {event_name} (Torneo: {found_league})")
        ev_date_raw = comp.get('date', '')
        if ev_date_raw:
            date_conv = self._format_utc_to_argentina(ev_date_raw)
            if date_conv.get('display'):
                report.append(f"- Fecha y Hora oficial: {date_conv['display']}")
        report.append(f"- Estado y Marcador: {status} | {' vs '.join(score_lines)}")
        if goals:
            report.append(f"- Goles del partido: {'; '.join(goals)}")
        if lineups_txt:
            report.append("- Formaciones titulares oficiales:\n  " + '\n  '.join(lineups_txt))
            
        state_mgr.emit_tool_call("get_soccer_match_sheet", {"team": team_query, "date": dates_to_check[0]}, f"Ficha oficial ESPN: {event_name}")
        return "\n".join(report)

    def _format_utc_to_argentina(self, utc_time_str: str) -> Dict[str, Any]:
        """Convierte de forma infalible una fecha/hora UTC (ISO) a hora oficial de Argentina (UTC-3),
        calculando la fecha local, hora, día de la semana y estado relativo ('HOY', 'MAÑANA', 'AYER', etc.)."""
        from datetime import datetime, timezone, timedelta
        import re

        if not utc_time_str:
            return {}
        
        clean_str = re.sub(r'\.\d+', '', str(utc_time_str)).replace('Z', '+00:00')
        if '+' not in clean_str and '-' not in clean_str[10:]:
            clean_str += '+00:00'
        
        try:
            dt_utc = datetime.fromisoformat(clean_str)
        except Exception:
            return {}
            
        tz_arg = timezone(timedelta(hours=-3))
        dt_arg = dt_utc.astimezone(tz_arg)
        
        now_arg = datetime.now(tz_arg)
        today_arg = now_arg.date()
        match_date = dt_arg.date()
        
        dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        
        dia_nombre = dias_semana[dt_arg.weekday()]
        mes_nombre = meses[dt_arg.month]
        hora_str = dt_arg.strftime("%H:%M")
        
        days_diff = (match_date - today_arg).days
        
        if days_diff == 0:
            relative_day = "HOY"
            display = f"HOY {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == 1:
            relative_day = "MAÑANA"
            display = f"MAÑANA {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == -1:
            relative_day = "AYER"
            display = f"AYER {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff == 2:
            relative_day = f"Pasado mañana ({dia_nombre})"
            display = f"Pasado mañana {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        elif days_diff < 0:
            relative_day = f"El {dia_nombre} pasado"
            display = f"El {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
        else:
            relative_day = f"El {dia_nombre}"
            display = f"El {dia_nombre} {dt_arg.day} de {mes_nombre} a las {hora_str} hs"
            
        return {
            "dt_arg": dt_arg,
            "date_str": dt_arg.strftime("%Y-%m-%d"),
            "time_str": hora_str,
            "day_name": dia_nombre,
            "month_name": mes_nombre,
            "relative_day": relative_day,
            "display": display,
            "is_today": days_diff == 0,
            "is_tomorrow": days_diff == 1,
            "is_yesterday": days_diff == -1,
            "days_diff": days_diff
        }

    @_timed
    def _get_fotmob_boca_data(self) -> Dict[str, Any]:
        """Wrapper legacy: datos de Boca con la MISMA técnica y formato de siempre.
        No cambiar su comportamiento: es el camino probado en producción."""
        return self._get_fotmob_team_data(10077, "Boca", home_stadium="en La Bombonera",
                                          slug="boca-juniors")

    def _get_fotmob_team_data(self, team_id: int, team_name: str,
                              home_stadium: str = "", slug: str = "x") -> Dict[str, Any]:
        """Extrae de FotMob en tiempo real (vía SSR Next.js __NEXT_DATA__) el próximo partido,
        último partido, fixture reciente Y agenda futura de CUALQUIER equipo mapeado.
        Misma técnica que el fetcher original de Boca; solo se parametriza el equipo.
        FIX 2026-09-15: además de recent_fixtures extrae upcoming_fixtures (partidos con
        notStarted=true, ordenados por fecha, hora ya convertida a Argentina): es la
        fuente para 'el partido después del de hoy' / 'el del finde'. Viene en la misma
        página: cero pedidos HTTP extra."""
        import urllib.request
        import json
        import re
        import unicodedata

        def norm(s):
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower()

        team_key = norm(team_name)
        url = f"https://www.fotmob.com/teams/{team_id}/overview/{slug}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as r:
                html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">({.*?})</script>', html)
            if not m:
                return {}
            data = json.loads(m.group(1))
            team_data = data.get('props', {}).get('pageProps', {}).get('fallback', {}).get(f'team-{team_id}', {})
            overview = team_data.get('overview', {})
            
            next_m = overview.get('nextMatch', {})
            next_info = None
            if next_m:
                utc = next_m.get('status', {}).get('utcTime', '')
                tz_conv = self._format_utc_to_argentina(utc)
                home = next_m.get('home', {}).get('name', '')
                away = next_m.get('away', {}).get('name', '')
                is_home = team_key in norm(home)
                rival = away if is_home else home
                if is_home:
                    cond = f"Local ({home_stadium})" if home_stadium else "Local"
                else:
                    cond = f"Visitante (en cancha de {rival})"
                tournament = next_m.get('tournament', {}).get('name', 'Torneo Oficial')
                next_info = {
                    "id": next_m.get('id'),
                    "pageUrl": next_m.get('pageUrl'),
                    "rival": rival,
                    "condition": cond,
                    "tournament": tournament,
                    "display_date": tz_conv.get('display', ''),
                    "relative_day": tz_conv.get('relative_day', ''),
                    "is_today": tz_conv.get('is_today', False),
                    "is_tomorrow": tz_conv.get('is_tomorrow', False),
                    "time_str": tz_conv.get('time_str', ''),
                    "utc_time": utc
                }
                
            last_m = overview.get('lastMatch', {})
            last_info = None
            if last_m:
                utc = last_m.get('status', {}).get('utcTime', '')
                tz_conv = self._format_utc_to_argentina(utc)
                home = last_m.get('home', {}).get('name', '')
                away = last_m.get('away', {}).get('name', '')
                home_score = last_m.get('home', {}).get('score', 0)
                away_score = last_m.get('away', {}).get('score', 0)
                score_str = last_m.get('status', {}).get('scoreStr', f"{home_score} - {away_score}")
                tournament = last_m.get('tournament', {}).get('name', 'Torneo Oficial')
                last_info = {
                    "id": last_m.get('id'),
                    "pageUrl": last_m.get('pageUrl'),
                    "match": f"{home} {score_str} {away}",
                    "home": home,
                    "away": away,
                    "score": score_str,
                    "tournament": tournament,
                    "display_date": tz_conv.get('display', ''),
                    "relative_day": tz_conv.get('relative_day', ''),
                    "utc_time": utc
                }
                
            # FIX 2026-09-15: lista de partidos recientes (para "la ida", "el 11 vs X", etc.).
            # Viene en la misma página de FotMob: cero pedidos HTTP extra.
            recent_fixtures = []
            try:
                all_fx = team_data.get('fixtures', {}).get('allFixtures', {}).get('fixtures', [])
                for fx in all_fx:
                    f_utc = fx.get('status', {}).get('utcTime', '')
                    f_home = fx.get('home', {}).get('name', '')
                    f_away = fx.get('away', {}).get('name', '')
                    if not f_home or not f_away:
                        continue
                    f_is_home = team_key in norm(f_home)
                    f_rival = f_away if f_is_home else f_home
                    f_tz = self._format_utc_to_argentina(f_utc)
                    f_hs = fx.get('home', {}).get('score', 0)
                    f_as = fx.get('away', {}).get('score', 0)
                    f_score = fx.get('status', {}).get('scoreStr', f"{f_hs} - {f_as}")
                    recent_fixtures.append({
                        "pageUrl": fx.get('pageUrl'),
                        "home": f_home,
                        "away": f_away,
                        "rival": f_rival,
                        "tournament": fx.get('tournament', {}).get('name', 'Torneo Oficial'),
                        "utc_time": f_utc,
                        "display_date": f_tz.get('display', ''),
                        "score": f_score,
                        "not_started": fx.get('notStarted', False),
                    })
            except Exception:
                recent_fixtures = []

            # FIX 2026-09-15: agenda futura (para "después del de hoy" / "el del finde").
            # FotMob trae los próximos partidos con notStarted=true en el mismo fixture.
            try:
                upcoming_fixtures = sorted(
                    [f for f in recent_fixtures if f.get("not_started") and f.get("utc_time")],
                    key=lambda f: f["utc_time"],
                )
            except Exception:
                upcoming_fixtures = []

            return {
                "next_match": next_info,
                "last_match": last_info,
                "recent_fixtures": recent_fixtures,
                "upcoming_fixtures": upcoming_fixtures,
            }
        except Exception as e:
            log_warning(f"Error consultando FotMob overview: {e}")
            return {}

    def _build_upcoming_agenda(self, fotmob_data: Dict[str, Any], team_key: str,
                               home_label: str = "") -> list:
        """Devuelve líneas de agenda futura ('después del de hoy' / 'el del finde') a partir de
        upcoming_fixtures de FotMob. Saltea el primer elemento (= nextMatch, ya informado
        aparte) y lista los siguientes. team_key: nombre normalizado del equipo para
        calcular local/visitante. home_label: texto de estadio para el local (ej. Boca)."""
        import unicodedata

        def norm(s):
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower()

        upcoming = fotmob_data.get("upcoming_fixtures") or []
        tkey = norm(team_key)
        lines = []
        for fx in upcoming[1:5]:
            home = fx.get("home", "")
            away = fx.get("away", "")
            is_home = tkey in norm(home)
            rival = away if is_home else home
            if is_home:
                cond = f"Local ({home_label})" if home_label else "Local"
            else:
                cond = f"Visitante (cancha de {rival})"
            lines.append(
                f"- {fx.get('display_date', '')}: {home} vs {away} "
                f"({cond}, {fx.get('tournament', '')})"
            )
        return lines

    def _is_second_match_question(self, query: str) -> bool:
        """Detecta si preguntan por el partido DESPUÉS del próximo ('después del de hoy',
        'el siguiente', 'el del finde', etc.)."""
        import unicodedata

        def norm(s):
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower()

        q = norm(query)
        signals = [
            "despues del de hoy", "despues de hoy", "despues del partido de hoy",
            "despues de este partido", "despues de este", "despues del partido",
            "el siguiente", "el que sigue", "el proximo despues", "el otro partido",
            "fin de semana", "finde", "este finde", "el finde",
            "y despues", "que viene despues", "cual sigue",
        ]
        return any(s in q for s in signals)

    def _find_team_past_fixture(self, query: str, fotmob_data: Dict[str, Any]) -> Dict[str, Any]:
        """Busca en el fixture reciente de FotMob un partido JUGADO específico
        pedido por el usuario (ej: 'la ida', 'el 11 contra San Pablo', 'la formación del partido anterior').
        Funciona para cualquier equipo (el fixture ya viene del equipo consultado).
        Devuelve el fixture (rival, torneo, fecha, pageUrl) o {} si no se identifica uno concreto."""
        import unicodedata
        from datetime import datetime, timezone

        def norm(s):
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower().strip()

        # Alias: lo que el usuario dice en español vs lo que dice FotMob
        RIVAL_ALIASES = {
            "san pablo": "sao paulo",
            "sao paulo": "sao paulo",
        }

        def canon(name):
            n = norm(name)
            for alias, canonical in RIVAL_ALIASES.items():
                if alias in n:
                    return canonical
            return n

        q = norm(query)
        fixtures = fotmob_data.get("recent_fixtures") or []
        if not fixtures:
            return {}
        next_m = fotmob_data.get("next_match") or {}

        # Señales de que se pregunta por un partido ya jugado (no el próximo)
        past_signals = ["ida", "vuelta", "anterior", "pasado", "pasada", "ayer",
                        "anteayer", "fue", "fueron", "jugo", "jugaron"]
        if not any(s in q for s in past_signals):
            return {}

        target_rival = ""
        target_tournament = ""
        if "ida" in q or "vuelta" in q:
            # "la ida" = el otro partido contra el rival del próximo, mismo torneo
            target_rival = canon(next_m.get("rival", ""))
            target_tournament = norm(next_m.get("tournament", ""))
        else:
            for fx in fixtures:
                r = canon(fx.get("rival", ""))
                if r and r in q:
                    target_rival = r
                    break
            for fx in fixtures:
                t = norm(fx.get("tournament", ""))
                if t and len(t) > 4 and t in q:
                    target_tournament = t
                    break

        if not target_rival:
            return {}

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for fx in sorted(fixtures, key=lambda f: f.get("utc_time", ""), reverse=True):
            if fx.get("utc_time", "")[:10] >= today:
                continue  # todavía no se jugó
            if canon(fx.get("rival", "")) != target_rival:
                continue
            if target_tournament and norm(fx.get("tournament", "")) != target_tournament:
                continue
            return fx
        return {}

    def _get_fotmob_match_lineup(self, page_url: str, team_name: str = "Boca") -> Dict[str, Any]:
        """Extrae la formación oficial de un partido en FotMob (titulares, suplentes, técnico, goles).
        team_name selecciona de qué lado de la planilla se extrae (por defecto Boca, como siempre)."""
        import urllib.request
        import json
        import re
        import unicodedata

        def norm(s):
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s.lower()

        team_key = norm(team_name)

        if not page_url:
            return {}
        full_url = f"https://www.fotmob.com{page_url}" if page_url.startswith('/') else page_url
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
        try:
            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">({.*?})</script>', html)
            if not m:
                return {}
            data = json.loads(m.group(1))
            content = data.get('props', {}).get('pageProps', {}).get('content', {})
            lineup_data = content.get('lineup', {})
            match_facts = content.get('matchFacts', {})
            
            lineup_type = lineup_data.get('lineupType', '')
            source = lineup_data.get('source', '')
            is_confirmed = (lineup_type == 'standard' or source in ['optaSdapi', 'official']) and lineup_type != 'lastStarting11'
            
            home = lineup_data.get('homeTeam', {})
            away = lineup_data.get('awayTeam', {})
            side = home if team_key in norm(home.get('name', '')) else (away if team_key in norm(away.get('name', '')) else home)

            starters = [f"#{p.get('shirtNumber', p.get('shirt', ''))} {p.get('name', '')}" for p in side.get('starters', [])]
            subs = [f"#{p.get('shirtNumber', p.get('shirt', ''))} {p.get('name', '')}" for p in side.get('subs', [])]
            coach = side.get('coach', {}).get('name', '')
            formation = side.get('formation', '')
            
            goals = []
            events = match_facts.get('events', {}).get('events', [])
            for ev in events:
                if ev.get('type') == 'Goal':
                    player = ev.get('player', {}).get('name', '') or ev.get('nameStr', '')
                    time_m = ev.get('time', '')
                    score = ev.get('newScore', [])
                    score_txt = f"({score[0]}-{score[1]})" if score else ""
                    goals.append(f"{player} {time_m}' {score_txt}".strip())
                    
            return {
                "team": side.get('name', team_name),
                "formation": formation,
                "coach": coach,
                "starters": starters,
                "subs": subs,
                "goals": goals,
                "is_confirmed": is_confirmed,
                "lineup_type": lineup_type,
                "source": source
            }
        except Exception as e:
            log_warning(f"Error consultando FotMob lineup: {e}")
            return {}

    def _get_boca_probable_lineup(self) -> str:
        """Extrae de Olé, TyC o coberturas de la práctica de Ezeiza el 11 probable si se filtró en las noticias."""
        import urllib.request
        import xml.etree.ElementTree as ET
        import re
        import html

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            url_news = "https://news.google.com/rss/search?q=Boca+Juniors+posible+formacion+OR+probables+titulares+OR+equipo+practica&hl=es-419&gl=AR&ceid=AR:es-419"
            req = urllib.request.Request(url_news, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5) as r:
                root = ET.fromstring(r.read())
                for item in root.findall(".//item")[:5]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    clean_title = re.sub(r'\s*-\s*[^-]+$', '', title).strip()
                    desc = item.find("description").text if item.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if any(k in clean_title.lower() for k in ["formación", "formacion", "titulares", "once", "equipo"]):
                        if clean_desc and len(clean_desc) > 30:
                            return f"Novedad de Ezeiza según la prensa: '{clean_title}'. {clean_desc[:180]}"
                        return f"Novedad de Ezeiza: '{clean_title}'"
        except Exception as e:
            log_warning(f"Error consultando noticias de 11 probable: {e}")
        return ""

    @_timed
    def get_boca_juniors_info(self, topic: str = "todo") -> Dict[str, Any]:
        """Obtiene información deportiva oficial y en tiempo real de Boca Juniors: próximo partido (fecha, hora argentina, estadio, torneo) desde FotMob, formación oficial confirmada, últimos resultados, actualidad de Ezeiza, agenda de próximos partidos (para 'después del de hoy' / 'el del finde') Y partidos anteriores específicos (la ida/vuelta de una llave como 'el 11 de la ida vs San Pablo', o la formación titular de un partido pasado contra un rival nombrado). Para partidos jugados usa la planilla oficial confirmada de FotMob y, si no la tiene, la ficha oficial de ESPN como respaldo."""
        import os
        import urllib.request
        import json
        import xml.etree.ElementTree as ET
        import time
        import re
        import html
        from datetime import datetime, timedelta

        clean_q = (topic or "").strip()

        # 0. Instrucción crítica de fechas y personalidad (se usa en todos los caminos de respuesta)
        instruction = (
            "[REGLA CRÍTICA DE FECHA Y HORARIO]:\n"
            "La fecha y hora indicada arriba YA ESTÁ CONVERTIDA AL HUSO HORARIO DE ARGENTINA (UTC-3).\n"
            "Si el próximo partido dice 'HOY' (ej: 'HOY Viernes 11 de septiembre a las 21:30 hs'), respondé con total seguridad que Boca juega HOY. NUNCA digas que juega mañana.\n\n"
            "[INSTRUCCIÓN CRÍTICA DE RESPUESTA Y PERTINENCIA]:\n"
            "- Respondé ÚNICAMENTE a lo que te preguntó el usuario.\n"
            "- Si te preguntan cuándo juega Boca, contra quién, la hora o el estadio: hablá del próximo partido confirmado.\n"
            "- Si te preguntan por el partido DESPUÉS del de hoy (el siguiente, el que sigue, el del finde/fin de semana): hablá del bloque EL PARTIDO SIGUIENTE DE BOCA de abajo, NO del próximo inmediato.\n"
            "- Si te preguntan por la agenda o los próximos partidos en general: mencioná el próximo y los 2 o 3 que siguen.\n"
            "- Si te preguntan cómo forma Boca, quiénes juegan o la formación del próximo partido antes de que esté confirmada la planilla oficial (1 hora antes): explicá que la formación oficial sale 1 hora antes del partido en el vestuario, comentá las novedades de las prácticas o el 11 de referencia, y jamás inventes nombres de jugadores.\n"
            "- Si te preguntan por cómo salió el partido anterior: da el resultado exacto, los goles y quiénes jugaron.\n"
            "- Cero citas a diarios o páginas web: hablá en primera persona como el compinche xeneize más apasionado.\n"
            "- Respondé con pasión de potrero, al hueso y con ritmo oral (generalmente entre 2 y 3 oraciones)."
        )

        report = []

        # 1. Consulta en tiempo real a FotMob (Fixture + Último partido + Planilla oficial)
        fotmob_data = self._get_fotmob_boca_data()
        next_m = fotmob_data.get("next_match")
        last_m = fotmob_data.get("last_match")

        # 1b. FIX 2026-09-15: partido anterior específico ("la ida", "el 11 vs San Pablo"...).
        # Antes solo se miraban próximo y último: si hubo un partido en el medio,
        # la ida no tenía de dónde salir y Gemini respondía "no la tengo".
        past_fx = self._find_team_past_fixture(clean_q, fotmob_data)
        if past_fx and past_fx.get("pageUrl"):
            past_lu = self._get_fotmob_match_lineup(past_fx["pageUrl"])
            # FIX2 2026-09-15: FotMob a veces NO tiene la planilla real del partido
            # jugado (lineupType 'lastStarting11' = el 11 del ÚLTIMO partido de cada
            # equipo, no el de este). Solo se presenta como oficial si is_confirmed.
            if past_lu.get("is_confirmed") and past_lu.get("starters"):
                report.append(
                    f"PARTIDO ANTERIOR CONSULTADO (Fuente oficial en vivo: FotMob):\n"
                    f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']}\n"
                    f"- Torneo: {past_fx['tournament']}\n"
                    f"- Disputado: {past_fx['display_date']}"
                )
                coach_txt = f" - DT {past_lu['coach']}" if past_lu.get("coach") else ""
                report.append(
                    f"• 11 TITULAR DE BOCA EN ESE PARTIDO (Esquema {past_lu.get('formation', '')}{coach_txt}):\n"
                    f"  {', '.join(past_lu['starters'])}"
                )
                if past_lu.get("subs"):
                    report.append(f"• Suplentes: {', '.join(past_lu['subs'][:8])}...")
                if past_lu.get("goals"):
                    report.append(f"• Goles del partido: {', '.join(past_lu['goals'])}")
                report.append(instruction)
                final_text = "\n\n".join(report)
                state_mgr.emit_tool_call("get_boca_juniors_info", {"topic": topic}, f"Partido anterior vs {past_fx['rival']} (FotMob)")
                return {"status": "success", "results": final_text}
            # Fallback: ficha oficial de ESPN para ese partido (fecha ±1 día por zona horaria).
            espn_report = ""
            try:
                from datetime import datetime as _dt
                fx_dt = None
                try:
                    fx_dt = _dt.fromisoformat((past_fx.get("utc_time", "") or "").replace("Z", "+00:00"))
                except Exception:
                    fx_dt = None
                t_low = (past_fx.get("tournament", "") or "").lower()
                espn_league = None
                for _k, _v in {"sudamericana": "conmebol.sudamericana",
                               "libertadores": "conmebol.libertadores",
                               "liga profesional": "arg.1",
                               "copa argentina": "arg.copa"}.items():
                    if _k in t_low:
                        espn_league = _v
                        break
                if fx_dt:
                    espn_report = self.get_soccer_match_sheet(team_query="boca", target_date=fx_dt, specific_league=espn_league)
            except Exception:
                espn_report = ""
            if espn_report:
                final_text = (
                    f"PARTIDO ANTERIOR CONSULTADO (Fuente oficial en vivo: ESPN):\n"
                    f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']}\n"
                    f"- Torneo: {past_fx['tournament']}\n"
                    f"- Disputado: {past_fx['display_date']}\n"
                    f"- Nota: FotMob no publicó la planilla real de este partido; se usa la ficha oficial de ESPN.\n\n"
                    f"{espn_report}\n\n{instruction}"
                )
                state_mgr.emit_tool_call("get_boca_juniors_info", {"topic": topic}, f"Partido anterior vs {past_fx['rival']} (ESPN)")
                return {"status": "success", "results": final_text}
            final_text = (
                f"PARTIDO ANTERIOR CONSULTADO:\n"
                f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']} ({past_fx['tournament']}, {past_fx['display_date']})\n"
                f"- No se pudo obtener la planilla oficial de este partido (ni FotMob ni ESPN la tienen). "
                f"Decí que no conseguiste la formación exacta y NO inventes un 11 titular."
            )
            state_mgr.emit_tool_call("get_boca_juniors_info", {"topic": topic}, f"Partido anterior vs {past_fx['rival']} (sin planilla)")
            return {"status": "success", "results": final_text}

        if next_m:
            report.append(
                f"PRÓXIMO COMPROMISO CONFIRMADO DE BOCA (Fuente oficial en vivo: FotMob):\n"
                f"- Cuándo: {next_m['display_date']}\n"
                f"- Rival: {next_m['rival']}\n"
                f"- Condición y Estadio: {next_m['condition']}\n"
                f"- Torneo: {next_m['tournament']}"
            )
            if next_m.get('pageUrl'):
                next_lu = self._get_fotmob_match_lineup(next_m['pageUrl'])
                if next_lu.get('starters'):
                    if next_lu.get('is_confirmed'):
                        coach_txt = f" - DT {next_lu['coach']}" if next_lu.get('coach') else ""
                        report.append(
                            f"FORMACIÓN TITULAR OFICIAL CONFIRMADA PARA ESTE PARTIDO (Planilla oficial - Esquema {next_lu.get('formation', '4-3-3')}{coach_txt}):\n"
                            f"• Titulares: {', '.join(next_lu['starters'])}\n"
                            f"• Suplentes: {', '.join(next_lu['subs'][:8])}..."
                        )
                    else:
                        probable_11 = self._get_boca_probable_lineup()
                        ref_txt = f"\n• Último 11 de referencia que jugó el partido anterior:\n  {', '.join(next_lu['starters'])}" if next_lu.get('starters') else ""
                        if probable_11:
                            prob_info = f"• Novedades de la práctica / 11 rumoreado:\n  {probable_11}"
                        else:
                            prob_info = "• El cuerpo técnico aún no definió públicamente el 11 en los entrenamientos."
                        report.append(
                            f"ESTADO DE LA FORMACIÓN DEL PRÓXIMO PARTIDO:\n"
                            f"La planilla oficial todavía NO fue confirmada (se entrega en el vestuario 1 hora antes del partido).\n"
                            f"{prob_info}{ref_txt}"
                        )

        # 1c. FIX 2026-09-15: agenda futura de FotMob ("después del de hoy" / "el del finde").
        # upcoming_fixtures[0] es el nextMatch ya informado; [1] es el siguiente.
        upcoming = fotmob_data.get("upcoming_fixtures") or []
        if self._is_second_match_question(clean_q) and len(upcoming) >= 2:
            sec = upcoming[1]
            sec_home, sec_away = sec.get("home", ""), sec.get("away", "")
            sec_cond = "Local (en La Bombonera)" if "boca" in sec_home.lower() else f"Visitante (cancha de {sec_home})"
            report.append(
                f"EL PARTIDO SIGUIENTE DE BOCA (después del de hoy - Fuente oficial en vivo: FotMob):\n"
                f"- Cuándo: {sec['display_date']}\n"
                f"- Partido: {sec_home} vs {sec_away} ({sec_cond})\n"
                f"- Torneo: {sec['tournament']}"
            )
        agenda_lines = self._build_upcoming_agenda(fotmob_data, "boca", home_label="en La Bombonera")
        if agenda_lines:
            report.append(
                "AGENDA DE PRÓXIMOS PARTIDOS DE BOCA (Fuente oficial en vivo: FotMob):\n"
                + "\n".join(agenda_lines)
            )

        if last_m:
            report.append(
                f"ÚLTIMO PARTIDO JUGADO DE BOCA (FotMob):\n"
                f"- Resultado: {last_m['match']}\n"
                f"- Torneo: {last_m['tournament']}\n"
                f"- Disputado: {last_m['display_date']}"
            )
            if last_m.get('pageUrl'):
                last_lu = self._get_fotmob_match_lineup(last_m['pageUrl'])
                if last_lu.get('goals'):
                    report.append(f"• Goles del último partido: {', '.join(last_lu['goals'])}")
                if last_lu.get('starters'):
                    coach_txt = f" - DT {last_lu['coach']}" if last_lu.get('coach') else ""
                    report.append(
                        f"• 11 Titular que jugó ese partido (Esquema {last_lu.get('formation', '')}{coach_txt}):\n"
                        f"  {', '.join(last_lu['starters'])}"
                    )

        # 2. Novedades de Ezeiza (Google News RSS Argentina)
        try:
            url_news = "https://news.google.com/rss/search?q=Boca+Juniors+posible+formacion+OR+alineacion+OR+titulares&hl=es-419&gl=AR&ceid=AR:es-419"
            req_news = urllib.request.Request(url_news, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_news, timeout=3.0) as r:
                root = ET.fromstring(r.read())
                items = root.findall(".//item")
                notes = []
                for item in items[:3]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    clean_title = re.sub(r'\s*-\s*[^-]+$', '', title).strip()
                    desc = item.find("description").text if item.find("description") is not None else ""
                    clean_desc = html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()
                    if clean_title:
                        notes.append(f"• Titular: {clean_title} | Detalle: {clean_desc[:140]}")
                if notes:
                    report.append("REPORTES DE LA PRÁCTICA EN EZEIZA:\n" + "\n".join(notes))
        except Exception:
            pass

        # 3. Instrucción crítica de fechas y personalidad (definida al inicio de la función)
        report.append(instruction)

        final_text = "\n\n".join(report)
        state_mgr.emit_tool_call("get_boca_juniors_info", {"topic": topic}, "Datos de Boca Juniors (FotMob + Ezeiza)")
        return {"status": "success", "results": final_text}

    def _espn_league_for_tournament(self, tournament: str):
        """Mapea el nombre del torneo de FotMob al ID de liga de ESPN (para el fallback)."""
        t_low = (tournament or "").lower()
        for _k, _v in {"sudamericana": "conmebol.sudamericana",
                       "libertadores": "conmebol.libertadores",
                       "liga profesional": "arg.1",
                       "copa argentina": "arg.copa"}.items():
            if _k in t_low:
                return _v
        return None

    def _build_team_fotmob_report(self, team_id: int, display_name: str, match_key: str, query: str) -> str:
        """Reporte en vivo de FotMob para un equipo mapeado que NO es Boca: próximo partido,
        agenda futura ('después del de hoy' / 'el del finde'),
        último resultado y partido anterior específico ('la ida', 'el 11 vs X').
        Usa la planilla confirmada de FotMob y la ficha de ESPN como respaldo.
        Tono neutro: la voz xeneize apasionada es solo para Boca."""
        from datetime import datetime as _dt

        clean_q = (query or "").strip()
        fotmob_data = self._get_fotmob_team_data(team_id, match_key)
        next_m = fotmob_data.get("next_match")
        last_m = fotmob_data.get("last_match")
        if not next_m and not last_m and not fotmob_data.get("recent_fixtures"):
            return ""

        instruction = (
            "[INSTRUCCIÓN DE RESPUESTA]:\n"
            "- Respondé ÚNICAMENTE a lo que te preguntó el usuario.\n"
            "- Si preguntan por el partido DESPUÉS del próximo (el siguiente, el del finde): respondé con el bloque EL PARTIDO SIGUIENTE, no con el próximo inmediato.\n"
            "- La fecha y hora indicada YA ESTÁ CONVERTIDA AL HUSO HORARIO DE ARGENTINA (UTC-3).\n"
            "- Si la formación oficial todavía no está confirmada (se confirma 1 hora antes del partido), decilo claramente y JAMÁS inventes nombres de jugadores.\n"
            "- Respondé en 2 o 3 oraciones, al hueso y con ritmo oral."
        )
        report = []

        # 1. Partido anterior específico ("la ida", "el 11 vs X", "la formación del partido pasado").
        past_fx = self._find_team_past_fixture(clean_q, fotmob_data)
        if past_fx and past_fx.get("pageUrl"):
            past_lu = self._get_fotmob_match_lineup(past_fx["pageUrl"], team_name=match_key)
            if past_lu.get("is_confirmed") and past_lu.get("starters"):
                report.append(
                    f"PARTIDO ANTERIOR CONSULTADO (Fuente oficial en vivo: FotMob):\n"
                    f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']}\n"
                    f"- Torneo: {past_fx['tournament']}\n"
                    f"- Disputado: {past_fx['display_date']}"
                )
                coach_txt = f" - DT {past_lu['coach']}" if past_lu.get("coach") else ""
                report.append(
                    f"• 11 TITULAR DE {display_name.upper()} EN ESE PARTIDO (Esquema {past_lu.get('formation', '')}{coach_txt}):\n"
                    f"  {', '.join(past_lu['starters'])}"
                )
                if past_lu.get("subs"):
                    report.append(f"• Suplentes: {', '.join(past_lu['subs'][:8])}...")
                if past_lu.get("goals"):
                    report.append(f"• Goles del partido: {', '.join(past_lu['goals'])}")
                report.append(instruction)
                return "\n\n".join(report)
            # Fallback: ficha oficial de ESPN para ese partido (fecha ±1 día por zona horaria).
            espn_report = ""
            try:
                fx_dt = None
                try:
                    fx_dt = _dt.fromisoformat((past_fx.get("utc_time", "") or "").replace("Z", "+00:00"))
                except Exception:
                    fx_dt = None
                if fx_dt:
                    espn_report = self.get_soccer_match_sheet(
                        team_query=display_name,
                        target_date=fx_dt,
                        specific_league=self._espn_league_for_tournament(past_fx.get("tournament", "")))
            except Exception:
                espn_report = ""
            if espn_report:
                return (
                    f"PARTIDO ANTERIOR CONSULTADO (Fuente oficial en vivo: ESPN):\n"
                    f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']}\n"
                    f"- Torneo: {past_fx['tournament']}\n"
                    f"- Disputado: {past_fx['display_date']}\n"
                    f"- Nota: FotMob no publicó la planilla real de este partido; se usa la ficha oficial de ESPN.\n\n"
                    f"{espn_report}\n\n{instruction}"
                )
            return (
                f"PARTIDO ANTERIOR CONSULTADO:\n"
                f"- Partido: {past_fx['home']} {past_fx['score']} {past_fx['away']} ({past_fx['tournament']}, {past_fx['display_date']})\n"
                f"- No se pudo obtener la planilla oficial de este partido (ni FotMob ni ESPN la tienen). "
                f"Decí que no conseguiste la formación exacta y NO inventes un 11 titular.\n\n{instruction}"
            )

        # 2. Próximo partido.
        if next_m:
            report.append(
                f"PRÓXIMO PARTIDO DE {display_name.upper()} (Fuente oficial en vivo: FotMob):\n"
                f"- Cuándo: {next_m['display_date']}\n"
                f"- Rival: {next_m['rival']}\n"
                f"- Condición: {next_m['condition']}\n"
                f"- Torneo: {next_m['tournament']}"
            )
            if next_m.get('pageUrl'):
                next_lu = self._get_fotmob_match_lineup(next_m['pageUrl'], team_name=match_key)
                if next_lu.get('starters'):
                    if next_lu.get('is_confirmed'):
                        coach_txt = f" - DT {next_lu['coach']}" if next_lu.get('coach') else ""
                        report.append(
                            f"FORMACIÓN TITULAR OFICIAL CONFIRMADA (Esquema {next_lu.get('formation', '')}{coach_txt}):\n"
                            f"• Titulares: {', '.join(next_lu['starters'])}\n"
                            f"• Suplentes: {', '.join(next_lu['subs'][:8])}..."
                        )
                    else:
                        report.append(
                            "FORMACIÓN: la planilla oficial todavía no fue confirmada "
                            "(se confirma 1 hora antes del partido)."
                        )

        # 2b. FIX 2026-09-15: agenda futura de FotMob ("después del de hoy" / "el del finde").
        upcoming = fotmob_data.get("upcoming_fixtures") or []
        if self._is_second_match_question(clean_q) and len(upcoming) >= 2:
            sec = upcoming[1]
            sec_home, sec_away = sec.get("home", ""), sec.get("away", "")
            import unicodedata as _ud
            _norm = lambda x: "".join(c for c in _ud.normalize("NFKD", x or "") if not _ud.combining(c)).lower()
            sec_is_home = _norm(match_key) in _norm(sec_home)
            sec_cond = "Local" if sec_is_home else f"Visitante (cancha de {sec_home})"
            report.append(
                f"EL PARTIDO SIGUIENTE DE {display_name.upper()} (después del próximo - FotMob):\n"
                f"- Cuándo: {sec['display_date']}\n"
                f"- Partido: {sec_home} vs {sec_away} ({sec_cond})\n"
                f"- Torneo: {sec['tournament']}"
            )
        agenda_lines = self._build_upcoming_agenda(fotmob_data, match_key)
        if agenda_lines:
            report.append(
                f"AGENDA DE PRÓXIMOS PARTIDOS DE {display_name.upper()} (FotMob):\n"
                + "\n".join(agenda_lines)
            )

        # 3. Último partido jugado.
        if last_m:
            report.append(
                f"ÚLTIMO PARTIDO DE {display_name.upper()} (FotMob):\n"
                f"- Resultado: {last_m['match']}\n"
                f"- Torneo: {last_m['tournament']}\n"
                f"- Disputado: {last_m['display_date']}"
            )
            if last_m.get('pageUrl'):
                last_lu = self._get_fotmob_match_lineup(last_m['pageUrl'], team_name=match_key)
                if last_lu.get('goals'):
                    report.append(f"• Goles del último partido: {', '.join(last_lu['goals'])}")
                if last_lu.get('starters'):
                    coach_txt = f" - DT {last_lu['coach']}" if last_lu.get('coach') else ""
                    report.append(
                        f"• 11 Titular que jugó ese partido (Esquema {last_lu.get('formation', '')}{coach_txt}):\n"
                        f"  {', '.join(last_lu['starters'])}"
                    )

        report.append(instruction)
        return "\n\n".join(report)

    @_timed
    def get_soccer_info(self, query: str = "", team: str = "", date: str = "") -> Dict[str, Any]:
        """Consulta datos de fútbol (fichas técnicas, formaciones oficiales, goles, resultados históricos o recientes) de cualquier equipo o final."""
        log_info(f"[TOOLS] get_soccer_info llamado con query={query!r} team={team!r} date={date!r}")
        clean_q = (query or team or "").strip()
        
        # 1. Finales históricas detectadas
        hist_lg, hist_dt = self._get_historical_final_dates(clean_q)
        if hist_lg and hist_dt:
            sheet = self.get_soccer_match_sheet(team_query=clean_q, target_date=hist_dt, specific_league=hist_lg)
            if sheet:
                state_mgr.emit_tool_call("get_soccer_info", {"query": clean_q, "date": hist_dt}, "Ficha histórica ESPN")
                return {"status": "success", "results": sheet}

        # 2. Si es Boca y piden próximo o último partido.
        # Se mira query+team COMBINADOS: el modelo a veces pasa el equipo solo en
        # 'team' (ej. query="cuál es el próximo partido después del de hoy",
        # team="Boca"), y con (query or team) el team se perdía.
        lower_q = clean_q.lower()
        team_text = f"{query or ''} {team or ''}".strip().lower()
        if any(b in team_text for b in ["boca", "xeneize", "bombonera"]) and not any(yr in lower_q for yr in ["2024", "2023", "2022", "2021", "2020", "2018", "2007", "2000"]):
            return self.get_boca_juniors_info(clean_q)

        # 2b. Delegación a FotMob para equipos argentinos mapeados (no Boca).
        # La implementación vive en get_fotmob_team_info, con la misma filosofía
        # que get_boca_juniors_info: el equipo sale de un mapa hard-codeado,
        # sin adivinar intenciones. Si hay fecha puntual se deja a ESPN (paso 3).
        if not (date or "").strip():
            fotmob_res = self.get_fotmob_team_info(query=query, team=team)
            if fotmob_res.get("status") == "success":
                state_mgr.emit_tool_call("get_soccer_info", {"query": clean_q}, "FotMob (delegado)")
                return fotmob_res
        # Si no es un equipo mapeado (o es Boca, o FotMob falló), se sigue al
        # flujo normal (ESPN -> search_web).

        # 3. Match sheet de ESPN para cualquier equipo / fecha
        sheet = self.get_soccer_match_sheet(team_query=clean_q, target_date=date if date else None)
        if sheet:
            state_mgr.emit_tool_call("get_soccer_info", {"query": clean_q, "date": date}, "Ficha oficial ESPN")
            return {"status": "success", "results": sheet}

        # 4. Fallback a búsqueda web
        return self.search_web(clean_q)

    def get_fotmob_team_info(self, query: str = "", team: str = "") -> Dict[str, Any]:
        """Reporte en vivo de FotMob (próximo partido, último resultado, formación)
        para equipos argentinos mapeados (NO Boca: ese tiene su herramienta propia).
        Vía Boca-like: el equipo se resuelve de query+team contra el mapa
        hard-codeado FOTMOB_TEAMS, sin adivinar intenciones ni parámetros."""
        log_info(f"[TOOLS] get_fotmob_team_info llamado con query={query!r} team={team!r}")
        text = f"{query or ''} {team or ''}".strip()
        found = self.match_fotmob_team(text)
        if not found:
            return {"status": "not_mapped",
                    "results": ("Ese equipo no está en el mapa de FotMob. "
                                "Usá get_soccer_info (ESPN/web).")}
        tid, display, mkey = found
        if display == "Boca Juniors":
            return {"status": "not_mapped",
                    "results": ("Para Boca Juniors usá SIEMPRE get_boca_juniors_info, "
                                "nunca esta herramienta.")}
        log_info(f"[FotMob] equipo detectado: {display} (id {tid})")
        try:
            report = self._build_team_fotmob_report(tid, display, mkey, text)
        except Exception as e:
            log_warning(f"[FotMob] falló para {display}: {e}")
            report = None
        if report:
            state_mgr.emit_tool_call("get_fotmob_team_info", {"query": text}, f"FotMob {display}")
            return {"status": "success", "results": report}
        return {"status": "empty",
                "results": (f"No se pudo obtener datos en vivo de {display} en FotMob. "
                            "Usá get_soccer_info.")}
