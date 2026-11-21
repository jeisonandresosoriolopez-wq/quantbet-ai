"""Fuente de lesiones y ausencias confirmadas en tiempo real (ESPN NBA + API-Football).

- NBA: ESPN API (gratuita, caché 30 min).
- Fútbol: API-Football v3 (v3.football.api-sports.io/injuries?date=YYYY-MM-DD,
  caché en disco 6 horas -> solo ~2-4 peticiones/día del límite de 100/día).
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import urllib.request
from datetime import datetime
from typing import Any

from .. import config

log = logging.getLogger("quantbet.injuries")

NBA_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
API_FOOTBALL_INJURIES_URL = "https://v3.football.api-sports.io/injuries"

_nba_inj_cache: dict[str, Any] = {"ts": 0.0, "data": {}}
_fb_inj_mem_cache: dict[str, tuple[float, dict[str, list[dict]]]] = {}

# Alias comunes entre football-data / Wplay y API-Football
_TEAM_ALIASES = {
    "man city": "manchester city",
    "man united": "manchester united",
    "man utd": "manchester united",
    "spurs": "tottenham",
    "wolves": "wolverhampton",
    "nott'm forest": "nottingham forest",
    "ath bilbao": "athletic club",
    "athletic bilbao": "athletic club",
    "ath madrid": "atletico madrid",
    "espanol": "espanyol",
    "sociedad": "real sociedad",
    "vallecano": "rayo vallecano",
    "betis": "real betis",
    "psg": "paris saint germain",
    "bayern munich": "bayern munchen",
    "ein frankfurt": "eintracht frankfurt",
    "m'gladbach": "borussia monchengladbach",
    "dortmund": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "inter": "inter",
    "ac milan": "ac milan",
    "milan": "ac milan",
    "verona": "hellas verona",
    "cologne": "fc koln",
    "koln": "fc koln",
}


def _norm_team(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower().strip()
    s = re.sub(r"\b(fc|cf|sc|ac|cd|ud|sd|rc|ca|as|ss|sv|vfl|vfb|rb|1\.)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _TEAM_ALIASES.get(s, s)


# --------------------------------------------------------------------------- #
# NBA (ESPN)
# --------------------------------------------------------------------------- #
def fetch_nba_injuries(force: bool = False) -> dict[str, list[dict]]:
    """Retorna diccionario { 'Team Display Name': [ {player, status, comment} ] }."""
    if not force and _nba_inj_cache["data"] and (time.time() - _nba_inj_cache["ts"]) < 1800:
        return _nba_inj_cache["data"]

    req = urllib.request.Request(
        NBA_INJURIES_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantBet/1.0"},
    )
    out_map: dict[str, list[dict]] = {}
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        for team_blk in raw.get("injuries", []):
            tname = team_blk.get("displayName", "").strip()
            if not tname:
                continue
            plist = []
            for item in team_blk.get("injuries", []):
                ath = item.get("athlete", {})
                pname = ath.get("displayName", "").strip()
                status = item.get("status", "Questionable").strip()
                comment = item.get("shortComment", "") or ""
                if pname:
                    plist.append({
                        "player": pname,
                        "status": status,
                        "reason": comment[:120],
                        "comment": comment[:120],
                    })
            if plist:
                out_map[tname] = plist
        _nba_inj_cache["ts"] = time.time()
        _nba_inj_cache["data"] = out_map
    except Exception as exc:
        log.warning("No se pudo obtener parte de lesiones NBA (%s)", exc)
    return _nba_inj_cache["data"]


def get_team_injuries(team_name: str, inj_map: dict[str, list[dict]] | None = None) -> list[dict]:
    if inj_map is None:
        inj_map = fetch_nba_injuries()
    if team_name in inj_map:
        return inj_map[team_name]
    low = team_name.lower()
    for k, v in inj_map.items():
        if low in k.lower() or k.lower() in low:
            return v
    return []


def is_player_out(player_name: str, inj_list: list[dict]) -> bool:
    low = player_name.lower().strip()
    for item in inj_list:
        if low in item["player"].lower() or item["player"].lower() in low:
            if item["status"].lower() in ("out", "doubtful", "suspended", "missing fixture"):
                return True
    return False


# --------------------------------------------------------------------------- #
# Fútbol (API-Football v3 con caché en disco de 6 horas)
# --------------------------------------------------------------------------- #
def _parse_fb_injuries(raw: dict) -> dict[str, list[dict]]:
    by_team: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for item in raw.get("response", []):
        team_name = (item.get("team") or {}).get("name", "").strip()
        p = item.get("player") or {}
        pname = p.get("name", "").strip()
        if not team_name or not pname:
            continue
        nk = _norm_team(team_name)
        if (nk, pname.lower()) in seen:
            continue
        seen.add((nk, pname.lower()))
        by_team.setdefault(nk, []).append({
            "player": pname,
            "status": p.get("type") or "Missing Fixture",
            "reason": p.get("reason") or "Lesión/Baja",
        })
    return by_team


def fetch_football_injuries(date_str: str, force: bool = False) -> dict[str, list[dict]]:
    """Obtiene todas las bajas de fútbol de una fecha (YYYY-MM-DD) en 1 sola consulta cacheada 6h."""
    if not config.API_FOOTBALL_KEY:
        return {}

    now = time.time()
    if not force and date_str in _fb_inj_mem_cache:
        ts, cached_map = _fb_inj_mem_cache[date_str]
        if (now - ts) < 6 * 3600:
            return cached_map

    cache_file = config.CACHE_DIR / f"api_football_injuries_{date_str}.json"
    if not force and cache_file.exists() and (now - cache_file.stat().st_mtime) < 6 * 3600:
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            parsed = _parse_fb_injuries(raw)
            _fb_inj_mem_cache[date_str] = (now, parsed)
            return parsed
        except Exception:
            pass

    url = f"{API_FOOTBALL_INJURIES_URL}?date={date_str}"
    req = urllib.request.Request(
        url,
        headers={
            "x-apisports-key": config.API_FOOTBALL_KEY,
            "User-Agent": "Mozilla/5.0 QuantBet/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            text = resp.read().decode("utf-8")
        raw = json.loads(text)
        if raw.get("errors"):
            log.warning("API-Football devolvió error para %s: %s", date_str, raw.get("errors"))
            return {}
        cache_file.write_text(text, encoding="utf-8")
        parsed = _parse_fb_injuries(raw)
        _fb_inj_mem_cache[date_str] = (now, parsed)
        log.info("API-Football lesiones %s: %d equipos con bajas", date_str, len(parsed))
        return parsed
    except Exception as exc:
        log.warning("Error consultando API-Football lesiones (%s): %s", date_str, exc)
        if cache_file.exists():
            try:
                parsed = _parse_fb_injuries(json.loads(cache_file.read_text(encoding="utf-8")))
                _fb_inj_mem_cache[date_str] = (now, parsed)
                return parsed
            except Exception:
                pass
        return {}


def get_football_team_injuries(team_name: str, kickoff: datetime | str | None) -> list[dict]:
    """Devuelve lista de bajas confirmadas para un equipo de fútbol en la fecha de su partido."""
    if not config.API_FOOTBALL_KEY or not kickoff:
        return []
    if isinstance(kickoff, datetime):
        date_str = kickoff.strftime("%Y-%m-%d")
    else:
        date_str = str(kickoff)[:10]
    inj_map = fetch_football_injuries(date_str)
    if not inj_map:
        return []
    nk = _norm_team(team_name)
    if nk in inj_map:
        return inj_map[nk]
    for k, v in inj_map.items():
        if len(nk) >= 4 and (nk in k or k in nk):
            return v
    return []
