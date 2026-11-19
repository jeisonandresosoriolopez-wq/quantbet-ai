"""Fuente principal: football-data.co.uk.

Ofrece CSV gratuitos (sin API key) con resultados, xG, tiros y cuotas de apertura
y de cierre de varias casas, además de un archivo ``fixtures.csv`` con los próximos
partidos y sus cuotas.
"""
from __future__ import annotations

import csv
import io
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import config

log = logging.getLogger("quantbet.football_data")

BASE = "https://www.football-data.co.uk"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantBet/1.0"

BOOKMAKERS = {
    "B365": "Bet365", "BW": "Bwin", "BV": "BetVictor", "BFD": "Betfred",
    "PP": "Paddy Power", "SKB": "Sky Bet", "BFE": "Betfair Exchange",
    "PS": "Pinnacle", "WH": "William Hill", "1XB": "1xBet",
}


# --------------------------------------------------------------------------- #
# Descarga con caché
# --------------------------------------------------------------------------- #
def _fetch(url: str, cache_name: str, ttl_hours: float) -> str | None:
    path: Path = config.CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < max(ttl_hours, 6.0) * 3600:
        return path.read_text(encoding="utf-8")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8-sig", "replace")
        if "HomeTeam" not in text[:2000]:
            raise ValueError("respuesta inesperada")
        path.write_text(text, encoding="utf-8")
        return text
    except (urllib.error.URLError, ValueError, TimeoutError) as exc:
        log.warning("No se pudo descargar %s (%s); usando caché si existe", url, exc)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None


def cache_age_hours(cache_name: str) -> float | None:
    path = config.CACHE_DIR / cache_name
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 3600


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _f(row: dict, key: str) -> float | None:
    val = row.get(key)
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _i(row: dict, key: str) -> int | None:
    v = _f(row, key)
    return None if v is None else int(v)


def _kickoff(row: dict) -> datetime | None:
    d, t = row.get("Date", ""), row.get("Time") or "15:00"
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            naive = datetime.strptime(f"{d} {t}", fmt)
            return naive.replace(tzinfo=ZoneInfo(config.SOURCE_TZ))
        except ValueError:
            continue
    return None


def _best(row: dict, suffixes: list[str], closing: bool) -> dict:
    """Mejor cuota y cuota media para un conjunto de selecciones."""
    c = "C" if closing else ""
    best, avg, books = {}, {}, {}
    for sel_key, sfx in suffixes:
        mx = _f(row, f"Max{c}{sfx}")
        av = _f(row, f"Avg{c}{sfx}")
        book_best, book_name = None, None
        for code, name in BOOKMAKERS.items():
            if code == "BFE":  # el exchange cobra comisión; no lo usamos como "mejor cuota"
                continue
            v = _f(row, f"{code}{c}{sfx}")
            if v:
                books.setdefault(name, {})[sel_key] = v
                if book_best is None or v > book_best:
                    book_best, book_name = v, name
        if mx is None:
            mx = book_best
        best[sel_key] = mx
        avg[sel_key] = av if av else book_best
        if book_name:
            best[f"{sel_key}_book"] = book_name if (mx is None or abs(mx - book_best) < 1e-9) else "Mejor del mercado"
    return {"best": best, "avg": avg, "books": books}


def _odds_block(row: dict, closing: bool) -> dict:
    c = "C" if closing else ""
    one_x_two = _best(row, [("H", "H"), ("D", "D"), ("A", "A")], closing)
    exch = {k: _f(row, f"BFE{c}{k}") for k in ("H", "D", "A")}
    if all(exch.values()):
        one_x_two["exchange"] = exch
    ou = _best(row, [("O", ">2.5"), ("U", "<2.5")], closing)
    ah_line = _f(row, "AHCh" if closing else "AHh")
    ah = _best(row, [("H", "AHH"), ("A", "AHA")], closing)
    ah["line"] = ah_line
    return {"1x2": one_x_two, "ou25": ou, "ah": ah}


def _parse(text: str, divs: set[str] | None = None) -> list[dict]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if not row.get("HomeTeam") or not row.get("AwayTeam"):
            continue
        div = row.get("Div", "")
        if divs and div not in divs:
            continue
        ko = _kickoff(row)
        if ko is None:
            continue
        out.append({
            "div": div,
            "kickoff": ko,
            "home": row["HomeTeam"].strip(),
            "away": row["AwayTeam"].strip(),
            "fthg": _i(row, "FTHG"), "ftag": _i(row, "FTAG"),
            "hxg": _f(row, "HxG"), "axg": _f(row, "AxG"),
            "hs": _i(row, "HS"), "as": _i(row, "AS"),
            "hst": _i(row, "HST"), "ast": _i(row, "AST"),
            "hc": _i(row, "HC"), "ac": _i(row, "AC"),
            "hf": _i(row, "HF"), "af": _i(row, "AF"),
            "hy": _i(row, "HY"), "ay": _i(row, "AY"),
            "hr": _i(row, "HR"), "ar": _i(row, "AR"),
            "odds": _odds_block(row, closing=False),
            "closing": _odds_block(row, closing=True),
        })
    return out


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def season_results(div: str, season: str, ttl_hours: float = 6) -> list[dict]:
    """Partidos de una liga y temporada (jugados y con cuotas de cierre)."""
    if div not in config.CLUB_LEAGUES:
        return []
    text = _fetch(f"{BASE}/mmz4281/{season}/{div}.csv", f"{div}_{season}.csv", ttl_hours)
    if not text:
        return []
    rows = _parse(text)
    return [r for r in rows if r["fthg"] is not None and r["ftag"] is not None]


def upcoming_fixtures(ttl_hours: float = 3) -> list[dict]:
    """Próximos partidos (de las ligas soportadas) con cuotas pre-partido."""
    text = _fetch(f"{BASE}/fixtures.csv", "fixtures.csv", ttl_hours)
    if not text:
        return []
    return _parse(text, set(config.LEAGUES))
