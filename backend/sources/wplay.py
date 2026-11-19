"""Fuente directa para Colombia: Wplay.co (https://apuestas.wplay.co).

Extrae en vivo los partidos y cuotas reales de Wplay Colombia para:
- Amistosos Internacionales FIFA y Amistosos Élite
- UEFA Nations League
- CONCACAF Nations League
- Premier League, LaLiga, Serie A, Bundesliga y Ligue 1
- Además de la página individual del evento (`1X2`, `Over/Under 2.5`, `Ambos Anotan` y `Hándicap Asiático`).
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import config
from .team_mapping import match_team, normalize

log = logging.getLogger("quantbet.wplay")

BASE = "https://apuestas.wplay.co"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"

# URLs de torneos en Wplay.co asociados a cada código de competición
WPLAY_TOURNAMENTS: dict[str, list[str]] = {
    "INT_FR": [
        "/es/t/19287/Amistosos",
        "/es/t/2412787/Elite-International-Friendlies",
    ],
    "UEFA_NL": [
        "/es/t/556801/UEFA-Nations-League",
    ],
    "CONC_NL": [
        "/es/t/601779/CONCACAF-Liga-de-Naciones",
    ],
    "COL1": [
        "/es/t/29698/Colombia-Copa-Colombia",
        "/es/t/19311/Colombia-Primera-A",
    ],
    "MEX1": ["/es/t/48527/M%C3%A9xico-Liga-MX"],
    "ARG1": ["/es/t/19296/Argentina-Liga-Profesional"],
    "BRA1": ["/es/t/2400790/Brasil-Serie-A", "/es/t/58397/Brasil-Serie-A"],
    "CHI1": ["/es/t/19303/Chile-Primera-Divisi%C3%B3n"],
    "ECU1": ["/es/t/19373/Ecuador-Primera-A"],
    "PER1": ["/es/t/19340/Per%C3%BA-Primera-Divisi%C3%B3n"],
    "USA1": ["/es/t/19302/USA-MLS"],
    "E0": ["/es/t/19157/Inglaterra-Premier-League", "/es/t/48274/Inglaterra-Premier-League"],
    "SP1": ["/es/t/19160/La-Liga", "/es/t/48278/Espa%C3%B1a-La-Liga"],
    "I1": ["/es/t/19159/Serie-A", "/es/t/48296/Italia-Serie-A"],
    "D1": ["/es/t/19158/Bundesliga-1", "/es/t/48279/Alemania-Bundesliga"],
    "F1": ["/es/t/19327/Ligue-1", "/es/t/48295/Francia-Ligue-1"],
}

# Diccionario de nombres en español de Wplay -> inglés/estándar de ESPN/football-data
SPANISH_TO_EN = {
    "islas cook": "Cook Islands",
    "malasia": "Malaysia",
    "singapur": "Singapore",
    "brasil": "Brazil",
    "china prc": "China",
    "china": "China",
    "barein": "Bahrain",
    "kirguistan": "Kyrgyz Republic",
    "libano": "Lebanon",
    "palestina": "Palestine",
    "japon": "Japan",
    "catar": "Qatar",
    "qatar": "Qatar",
    "corea del sur": "South Korea",
    "rep de corea": "South Korea",
    "eau": "United Arab Emirates",
    "emiratos arabes unidos": "United Arab Emirates",
    "siria": "Syria",
    "syria": "Syria",
    "arabia saudita": "Saudi Arabia",
    "arabia saudi": "Saudi Arabia",
    "jordania": "Jordan",
    "rusia": "Russia",
    "irak": "Iraq",
    "republica dominicana": "Dominican Republic",
    "bosnia y herzegovina": "Bosnia-Herzegovina",
    "bosnia": "Bosnia-Herzegovina",
    "rumania": "Romania",
    "dinamarca": "Denmark",
    "noruega": "Norway",
    "hungria": "Hungary",
    "irlanda del norte": "Northern Ireland",
    "polonia": "Poland",
    "suecia": "Sweden",
    "irlanda": "Republic of Ireland",
    "republica de irlanda": "Republic of Ireland",
    "ucrania": "Ukraine",
    "gales": "Wales",
    "belice": "Belize",
    "san vicente y las granadinas": "St. Vincent and the Grenadines",
    "guayana francesa": "French Guiana",
    "estados unidos": "United States",
    "ee uu": "United States",
    "islas caiman": "Cayman Islands",
    "san cristobal y nieves": "St. Kitts and Nevis",
    "santa lucia": "St. Lucia",
}


def _to_standard_name(wplay_name: str, candidates: list[str]) -> str:
    n = normalize(wplay_name)
    mapped = SPANISH_TO_EN.get(n, wplay_name)
    hit = match_team(mapped, candidates)
    if hit:
        return hit
    hit2 = match_team(wplay_name, candidates)
    return hit2 or mapped


def _fetch_html(path: str, cache_key: str, ttl_hours: float = 12.0) -> str:
    cfile: Path = config.CACHE_DIR / f"wplay_{cache_key}.html"
    if cfile.exists() and (time.time() - cfile.stat().st_mtime) < max(ttl_hours, 2.0) * 3600:
        return cfile.read_text(encoding="utf-8", errors="replace")
    url = path if path.startswith("http") else f"{BASE}{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            text = resp.read().decode("utf-8", "replace")
        cfile.write_text(text, encoding="utf-8")
        return text
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log.warning("Wplay falló en %s: %s", url, exc)
        if cfile.exists():
            return cfile.read_text(encoding="utf-8", errors="replace")
        return ""


def _parse_hcap_str(s: str) -> float | None:
    """Convierte cadenas tipo '0 / -0.5', '+0', '-4 / -4.5' a número decimal (-0.25, 0.0, -4.25)."""
    s = s.strip().replace("+", "")
    if "/" in s:
        parts = [p.strip() for p in s.split("/") if p.strip()]
        try:
            vals = [float(p) for p in parts]
            # Si el primero es 0 y el segundo es negativo, ej. '0 / -0.5' -> -0.25
            return round(sum(vals) / len(vals), 2)
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_event_page(html: str) -> dict:
    """Extrae cuotas de 1X2, Over/Under 2.5, Ambos Equipos Anotan y Hándicap Asiático de la página de evento Wplay."""
    out: dict = {
        "1x2": {"best": {}, "avg": {}},
        "ou25": {"best": {}, "avg": {}},
        "btts": {"best": {}, "avg": {}},
        "ah": {"best": {}, "avg": {}, "line": None, "lines": []},
    }
    if not html:
        return out

    # 1. Resultado Tiempo Completo (1X2)
    m_res = re.search(r'Resultado Tiempo Completo</span>.*?<tbody>(.*?)</tbody>', html, re.S)
    if m_res:
        decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', m_res.group(1))
        if len(decs) >= 3:
            h, d, a = float(decs[0]), float(decs[1]), float(decs[2])
            out["1x2"] = {
                "best": {"H": h, "D": d, "A": a, "H_book": "Wplay.co", "D_book": "Wplay.co", "A_book": "Wplay.co"},
                "avg": {"H": h, "D": d, "A": a},
            }

    # 2. Ambos Equipos Anotan (BTTS)
    m_btts = re.search(r'Ambos Equipos Anotan</span>.*?<tbody>(.*?)</tbody>', html, re.S)
    if m_btts:
        decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', m_btts.group(1))
        if len(decs) >= 2:
            y, n = float(decs[0]), float(decs[1])
            out["btts"] = {
                "best": {"Y": y, "N": n, "Y_book": "Wplay.co", "N_book": "Wplay.co"},
                "avg": {"Y": y, "N": n},
            }

    # 3. Total Goles Más/Menos de 2.5
    m_tot = re.search(r'Total Goles Más/Menos de\s*</span>(.*?)(?:<div class="expander |$) ', html, re.S)
    if not m_tot:
        p = html.find("Total Goles M")
        tot_chunk = html[p:p + 5500] if p != -1 else ""
    else:
        tot_chunk = m_tot.group(1)
    if tot_chunk:
        for wrap in re.findall(r'<div class="seln-wrapper[^"]*"[^>]*>(.*?)</div>', tot_chunk, re.S):
            sort_vals = re.findall(r'<span class="seln-sort[^"]*">([^<]+)</span>', wrap)
            decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', wrap)
            if sort_vals and sort_vals[0].strip() == "2.5" and len(decs) >= 2:
                o, u = float(decs[0]), float(decs[1])
                out["ou25"] = {
                    "best": {"O": o, "U": u, "O_book": "Wplay.co", "U_book": "Wplay.co"},
                    "avg": {"O": o, "U": u},
                }
                break

    # 4. Handicap Asiático (elegimos la línea más equilibrada cercana a cuota 1.90 vs 1.90)
    p_ah = html.find("Handicap Asiático")
    if p_ah != -1:
        ah_chunk = html[p_ah:p_ah + 9000]
        m_tb = re.search(r'<tbody>(.*?)</tbody>', ah_chunk, re.S)
        if m_tb:
            candidates = []
            for row in re.findall(r'<tr>(.*?)</tr>', m_tb.group(1), re.S):
                hcaps = re.findall(r'<span class="seln-hcap">([^<]+)</span>', row)
                decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', row)
                if len(hcaps) >= 2 and len(decs) >= 2:
                    ln = _parse_hcap_str(hcaps[0])
                    if ln is not None:
                        oh, oa = float(decs[0]), float(decs[1])
                        candidates.append((abs(oh - oa), ln, oh, oa, hcaps[0].strip(), hcaps[1].strip()))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                _, best_ln, oh, oa, h_label, a_label = candidates[0]
                out["ah"] = {
                    "line": best_ln,
                    "wplay_h_label": h_label,
                    "wplay_a_label": a_label,
                    "best": {"H": oh, "A": oa, "H_book": "Wplay.co", "A_book": "Wplay.co"},
                    "avg": {"H": oh, "A": oa},
                    "lines": [{"line": c[1], "H": c[2], "A": c[3], "h_str": c[4], "a_str": c[5]} for c in candidates],
                }
    return out


def parse_nba_event_props(html: str) -> list[dict]:
    """Extrae Player Props de NBA desde la página de partido de Wplay (Puntos, Rebotes, Asistencias por jugador)."""
    if not html:
        return []
    props: list[dict] = []
    sections = [
        ("Puntos totales de jugador", "Puntos"),
        ("Total rebotes por jugador", "Rebotes"),
        ("Total asistencias del jugador", "Asistencias"),
    ]
    for title, cat in sections:
        p = html.find(title)
        if p == -1:
            continue
        chunk = html[p:p + 14000]
        # Cada bloque tiene players-name, players-team y dos botones (Más de / Menos de) con seln-hcap y price dec
        pattern = re.compile(
            r'<div class="players-name">([^<]+)</div>\s*<div class="players-team">([^<]+)</div>.*?'
            r'<span class="seln-hcap">([0-9.]+)</span>.*?<span class="price dec"[^>]*>([0-9.]+)</span>.*?'
            r'<span class="seln-hcap">[0-9.]+</span>.*?<span class="price dec"[^>]*>([0-9.]+)</span>',
            re.S,
        )
        for m in pattern.finditer(chunk):
            player, team_label, line_s, over_s, under_s = m.groups()
            try:
                line = float(line_s)
                o_odd = float(over_s)
                u_odd = float(under_s)
                props.append({
                    "category": cat,
                    "player": player.strip(),
                    "team": team_label.strip(),
                    "line": line,
                    "over_odds": o_odd,
                    "under_odds": u_odd,
                })
            except ValueError:
                continue
    return props


_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _parse_wplay_dt(date_str: str | None, time_str: str | None) -> datetime:
    """Convierte '17 Nov' y '18:30' (hora Colombia) a datetime UTC."""
    now_co = datetime.now(ZoneInfo("America/Bogota"))
    try:
        parts = (date_str or "").strip().split()
        day = int(parts[0])
        mon = _MONTHS_ES.get(parts[1][:3].lower(), now_co.month)
        hh, mm = [int(x) for x in (time_str or "18:00").strip().split(":")]
        dt_co = datetime(now_co.year, mon, day, hh, mm, tzinfo=ZoneInfo("America/Bogota"))
        return dt_co.astimezone(timezone.utc)
    except Exception:
        return now_co.astimezone(timezone.utc)


def fetch_division_odds(div: str, known_teams: list[str], ttl_hours: float = 1.5,
                        force: bool = False) -> dict[tuple[str, str], dict]:
    """Devuelve diccionario {(home, away): wplay_odds_dict} para una competición."""
    paths = WPLAY_TOURNAMENTS.get(div, [])
    if not paths:
        return {}
    ttl = 0.0 if force else ttl_hours

    event_links: dict[str, tuple[str, str, str, float, float, float, datetime]] = {}
    for idx, p in enumerate(paths):
        html = _fetch_html(p, f"comp_{div}_{idx}", ttl_hours=ttl)
        if not html:
            continue
        # Cada fila de partido en cupón tiene 3 botones (Local, Empate, Visitante) y link /es/e/<id>/<slug>
        for tr in re.findall(r'<tr class="mkt mkt_content[^"]*"[^>]*>(.*?)</tr>', html, re.S):
            ev_m = re.search(r'href="(/es/e/(\d+)/[^"]+)"', tr)
            names = re.findall(r'<span class="seln-name">([^<]+)</span>', tr)
            decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', tr)
            dt_m = re.search(r'<span class="date">([^<]+)</span>', tr)
            tm_m = re.search(r'<span class="time">([^<]+)</span>', tr)
            if ev_m and len(names) >= 2 and len(decs) >= 3:
                ev_url, ev_id = ev_m.group(1), ev_m.group(2)
                h_raw, a_raw = names[0].strip(), names[1].strip()
                home = _to_standard_name(h_raw, known_teams)
                away = _to_standard_name(a_raw, known_teams)
                ko = _parse_wplay_dt(dt_m.group(1) if dt_m else None, tm_m.group(1) if tm_m else None)
                event_links[ev_id] = (ev_url, home, away, float(decs[0]), float(decs[1]), float(decs[2]), ko)

    results: dict[tuple[str, str], dict] = {}

    def _load_one(item):
        ev_id, (ev_url, home, away, h_odd, d_odd, a_odd, ko) = item
        ev_html = _fetch_html(ev_url, f"ev_{ev_id}", ttl_hours=max(ttl, 1.0))
        parsed = parse_event_page(ev_html)
        if not parsed["1x2"]["best"]:
            parsed["1x2"] = {
                "best": {"H": h_odd, "D": d_odd, "A": a_odd, "H_book": "Wplay.co", "D_book": "Wplay.co", "A_book": "Wplay.co"},
                "avg": {"H": h_odd, "D": d_odd, "A": a_odd},
            }
        parsed["wplay_url"] = f"{BASE}{ev_url}"
        parsed["kickoff"] = ko
        return (home, away), parsed

    # Descarga en paralelo con pool pequeño para que sea veloz (~1-2 seg)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for key, data in ex.map(_load_one, list(event_links.items())[:15]):
            results[key] = data

    return results


def fetch_live_events() -> list[dict]:
    """Extrae en tiempo real (sin caché) los partidos EN VIVO en Wplay.co (Fútbol y Baloncesto)."""
    live_out: list[dict] = []
    seen_ids: set[str] = set()

    def _fetch_sport_live(args):
        sport_label, path = args
        url = f"{BASE}{path}"
        out = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", "replace")
        except Exception as exc:
            log.warning("Error leyendo en vivo Wplay %s: %s", sport_label, exc)
            return out

        for chunk in html.split('class="inline-scoreboard">')[1:]:
            if "inplay-banner" not in chunk[:1500]:
                continue
            ev_m = re.search(r'<a[^>]*href="(/es/e/(\d+)/[^"]+)"', chunk)
            if not ev_m:
                continue
            ev_url, ev_id = ev_m.groups()
            mk_idx = chunk.find('<div class="markets">')
            if mk_idx == -1:
                continue
            sb_html = chunk[:mk_idx]
            tb_end = chunk.find("</table>", mk_idx)
            mk_html = chunk[mk_idx:tb_end] if tb_end != -1 else chunk[mk_idx:mk_idx + 4000]
            scores = re.findall(r'data-team_prop="score_[ab]"[^>]*>([^<]+)<', sb_html)
            clock_m = re.search(r'<span class="clock[^"]*"[^>]*>([^<]+)</span>', sb_html)
            period_m = re.search(r'<span class="period"[^>]*>([^<]+)</span>', sb_html)
            clock_str = clock_m.group(1).strip() if clock_m else "EN VIVO"
            period_str = period_m.group(1).strip() if period_m else ""

            names = re.findall(r'<span class="seln-name">([^<]+)</span>', mk_html)
            decs = re.findall(r'<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', mk_html)
            if len(names) < 2 or len(decs) < 2:
                continue

            home = names[0].strip()
            away = names[1].strip()
            h_score = int(scores[0].strip()) if len(scores) >= 1 and scores[0].strip().isdigit() else 0
            a_score = int(scores[1].strip()) if len(scores) >= 2 and scores[1].strip().isdigit() else 0

            h_odd = float(decs[0])
            if len(decs) >= 3:
                d_odd, a_odd = float(decs[1]), float(decs[2])
            else:
                d_odd, a_odd = None, float(decs[1])

            out.append({
                "ev_id": ev_id,
                "sport": sport_label,
                "home": home,
                "away": away,
                "score": f"{h_score} - {a_score}",
                "h_score": h_score,
                "a_score": a_score,
                "clock": clock_str,
                "period": period_str,
                "odds": {"H": h_odd, "D": d_odd, "A": a_odd},
                "wplay_url": f"{BASE}{ev_url}",
            })
        return out

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for res in ex.map(_fetch_sport_live, [("Fútbol", "/es/s/FOOT/F%C3%BAtbol"), ("Baloncesto", "/es/s/BASK/Baloncesto")]):
            for ev in res:
                if ev["ev_id"] not in seen_ids:
                    seen_ids.add(ev["ev_id"])
                    live_out.append(ev)

    return live_out


def fetch_nba_fixtures(ttl_hours: float = 1.5, force: bool = False) -> list[dict]:
    """Extrae los partidos de NBA desde Wplay.co (/es/t/19172/NBA) con Handicap, Totales y Ganará (Moneyline)."""
    ttl = 0.0 if force else ttl_hours
    html = _fetch_html("/es/t/19172/NBA", "comp_NBA_main", ttl_hours=ttl)
    if not html:
        return []
    out: list[dict] = []
    # Cada partido en layout US de Wplay es un <tbody class=""> con 2 filas <tr> (Fila 1: Visitante '@', Fila 2: Local)
    for tbody in re.findall(r'<tbody[^>]*>(.*?)</tbody>', html, re.S):
        ev_m = re.search(r'data-ev_id="(\d+)"', tbody)
        url_m = re.search(r'href="(/es/e/\d+/[^"]+)"', tbody)
        dt_m = re.search(r'<span class="date">([^<]+)</span>', tbody)
        tm_m = re.search(r'<span class="time">([^<]+)</span>', tbody)
        if not ev_m or not url_m:
            continue
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody, re.S)
        if len(trs) < 2:
            continue

        def _parse_us_row(tr_html: str) -> dict:
            t_m = re.search(r'<div class="team-name">\s*<a[^>]*>([^<]+)</a>', tr_html, re.S)
            team = t_m.group(1).strip() if t_m else ""
            # Spread (mkt-sort-FHOT)
            sp_hcap, sp_dec = None, None
            m_sp = re.search(r'mkt-sort-FHOT.*?<span class="seln-hcap">([^<]+)</span>.*?<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', tr_html, re.S)
            if m_sp:
                try:
                    sp_hcap = float(m_sp.group(1).strip().replace("+", ""))
                    sp_dec = float(m_sp.group(2))
                except ValueError:
                    pass
            # Total (mkt-sort-FTPO)
            tot_line, tot_dec = None, None
            m_tot = re.search(r'mkt-sort-FTPO.*?<span class="seln-hcap">([^<]+)</span>.*?<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', tr_html, re.S)
            if m_tot:
                try:
                    tot_line = float(m_tot.group(1).strip())
                    tot_dec = float(m_tot.group(2))
                except ValueError:
                    pass
            # Moneyline (mkt-sort-H2HT)
            ml_dec = None
            m_ml = re.search(r'mkt-sort-H2HT.*?<span class="price dec"[^>]*>([0-9]+\.[0-9]+)</span>', tr_html, re.S)
            if m_ml:
                try:
                    ml_dec = float(m_ml.group(1))
                except ValueError:
                    pass
            return {"team": team, "sp_line": sp_hcap, "sp_odds": sp_dec, "tot_line": tot_line, "tot_odds": tot_dec, "ml_odds": ml_dec}

        away_row = _parse_us_row(trs[0])  # En formato US '@' la fila 1 es el Visitante
        home_row = _parse_us_row(trs[1])  # La fila 2 es el Local
        if not away_row["team"] or not home_row["team"]:
            continue

        ko = _parse_wplay_dt(dt_m.group(1) if dt_m else None, tm_m.group(1) if tm_m else None)
        odds_blk = {
            "h2h": {
                "best": {
                    "H": home_row["ml_odds"], "A": away_row["ml_odds"],
                    "H_book": "Wplay.co / BetPlay", "A_book": "Wplay.co / BetPlay",
                },
                "avg": {"H": home_row["ml_odds"], "A": away_row["ml_odds"]},
            },
            "spread": {
                "line": home_row["sp_line"],
                "best": {"H": home_row["sp_odds"], "A": away_row["sp_odds"], "H_book": "Wplay.co", "A_book": "Wplay.co"},
                "avg": {"H": home_row["sp_odds"], "A": away_row["sp_odds"]},
            },
            "total": {
                "line": away_row["tot_line"] or home_row["tot_line"],
                "best": {"O": away_row["tot_odds"], "U": home_row["tot_odds"], "O_book": "Wplay.co", "U_book": "Wplay.co"},
                "avg": {"O": away_row["tot_odds"], "U": home_row["tot_odds"]},
            },
        }
        out.append({
            "div": "NBA",
            "ev_id": ev_m.group(1),
            "ev_path": url_m.group(1),
            "kickoff": ko,
            "home": home_row["team"],
            "away": away_row["team"],
            "odds": odds_blk,
            "source": "Wplay.co + BetPlay / Consenso",
            "wplay_url": f"{BASE}{url_m.group(1)}",
        })

    def _enrich_props(item: dict) -> dict:
        ev_html = _fetch_html(item["ev_path"], f"nba_ev_{item['ev_id']}", ttl_hours=max(ttl, 4.0))
        item["player_props"] = parse_nba_event_props(ev_html)
        return item

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(_enrich_props, out[:12]))
    return out
