"""Fuente opcional: The Odds API (https://the-odds-api.com).

Si existe ``ODDS_API_KEY`` en el archivo .env, se usan sus cuotas (más frescas y de
más casas) para los partidos de las 5 grandes ligas. Cada llamada cuesta
``mercados × regiones`` créditos; con h2h+totals+spreads y 1 región = 3 créditos por
liga, por lo que se cachea la respuesta para no agotar los 500 créditos/mes del plan
gratuito.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

from .. import config
from .team_mapping import match_team

log = logging.getLogger("quantbet.odds_api")

BASE = "https://api.the-odds-api.com/v4/sports"
QUOTA_FILE = config.CACHE_DIR / "odds_api_quota.json"


def enabled() -> bool:
    return bool(config.ODDS_API_KEY)


def quota() -> dict:
    if QUOTA_FILE.exists():
        try:
            return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _save_quota(headers) -> None:
    data = {
        "remaining": headers.get("x-requests-remaining"),
        "used": headers.get("x-requests-used"),
        "last_cost": headers.get("x-requests-last"),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    QUOTA_FILE.write_text(json.dumps(data), encoding="utf-8")


def _get_events(sport_key: str, ttl_hours: float, force: bool) -> list[dict] | None:
    cache = config.CACHE_DIR / f"oddsapi_{sport_key}.json"
    if not force and cache.exists() and (time.time() - cache.stat().st_mtime) < ttl_hours * 3600:
        return json.loads(cache.read_text(encoding="utf-8"))
    params = urllib.parse.urlencode({
        "apiKey": config.ODDS_API_KEY,
        "regions": config.ODDS_API_REGION,
        "markets": "h2h,totals,spreads",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    })
    try:
        with urllib.request.urlopen(f"{BASE}/{sport_key}/odds?{params}", timeout=30) as resp:
            _save_quota(resp.headers)
            events = json.loads(resp.read().decode("utf-8"))
        cache.write_text(json.dumps(events), encoding="utf-8")
        return events
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        log.warning("The Odds API falló para %s: %s", sport_key, exc)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        return None


def _summ(prices: dict[str, list[tuple[float, str]]]) -> dict:
    best, avg, = {}, {}
    for sel, lst in prices.items():
        if not lst:
            continue
        p, book = max(lst, key=lambda x: x[0])
        best[sel] = p
        best[f"{sel}_book"] = book
        avg[sel] = round(statistics.mean(x[0] for x in lst), 3)
    return {"best": best, "avg": avg}


def event_to_odds(ev: dict) -> dict:
    """Convierte un evento de The Odds API al formato interno de cuotas."""
    home, away = ev["home_team"], ev["away_team"]
    h2h = {"H": [], "D": [], "A": []}
    ou = {"O": [], "U": []}
    spreads: dict[float, dict[str, list]] = {}
    books: dict[str, dict] = {}
    for bm in ev.get("bookmakers", []):
        title = bm.get("title", bm.get("key"))
        for mk in bm.get("markets", []):
            if mk["key"] == "h2h":
                for o in mk["outcomes"]:
                    sel = "H" if o["name"] == home else "A" if o["name"] == away else "D"
                    h2h[sel].append((o["price"], title))
                    books.setdefault(title, {})[sel] = o["price"]
            elif mk["key"] == "totals":
                for o in mk["outcomes"]:
                    if abs(float(o.get("point", 0)) - 2.5) < 1e-9:
                        sel = "O" if o["name"].lower() == "over" else "U"
                        ou[sel].append((o["price"], title))
            elif mk["key"] == "spreads":
                pts = {o["name"]: o for o in mk["outcomes"]}
                if home in pts and away in pts:
                    line = float(pts[home]["point"])
                    d = spreads.setdefault(line, {"H": [], "A": []})
                    d["H"].append((pts[home]["price"], title))
                    d["A"].append((pts[away]["price"], title))
    one_x_two = _summ(h2h)
    one_x_two["books"] = books
    ah = {"best": {}, "avg": {}, "line": None}
    if spreads:
        line = Counter({ln: len(v["H"]) for ln, v in spreads.items()}).most_common(1)[0][0]
        ah = _summ(spreads[line])
        ah["line"] = line
    return {"1x2": one_x_two, "ou25": _summ(ou), "ah": ah}


def fetch_league(div: str, known_teams: list[str], ttl_hours: float = 20,
                 force: bool = False) -> list[dict]:
    """Partidos próximos de una liga con cuotas, usando nombres de football-data."""
    if not enabled():
        return []
    sport_key = config.LEAGUES[div]["odds_api"]
    events = _get_events(sport_key, ttl_hours, force) or []
    out = []
    for ev in events:
        home = match_team(ev["home_team"], known_teams)
        away = match_team(ev["away_team"], known_teams)
        if not home or not away:
            log.info("Sin mapeo para %s vs %s", ev["home_team"], ev["away_team"])
            continue
        ko = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        out.append({"div": div, "kickoff": ko, "home": home, "away": away,
                    "odds": event_to_odds(ev), "source": "The Odds API"})
    return out
