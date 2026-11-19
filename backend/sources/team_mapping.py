"""Normalización de nombres de equipos entre fuentes de datos."""
from __future__ import annotations

import difflib
import re
import unicodedata

# Nombres de The Odds API (u otras fuentes) -> nombres de football-data.co.uk
ALIASES = {
    "manchester united": "Man United", "manchester city": "Man City",
    "wolverhampton wanderers": "Wolves", "nottingham forest": "Nott'm Forest",
    "brighton and hove albion": "Brighton", "newcastle united": "Newcastle",
    "tottenham hotspur": "Tottenham", "west ham united": "West Ham",
    "leeds united": "Leeds", "coventry city": "Coventry", "hull city": "Hull",
    "ipswich town": "Ipswich", "leicester city": "Leicester", "luton town": "Luton",
    "sheffield united": "Sheffield United", "afc bournemouth": "Bournemouth",
    "atletico madrid": "Ath Madrid", "athletic bilbao": "Ath Bilbao",
    "athletic club": "Ath Bilbao", "real betis": "Betis", "celta vigo": "Celta",
    "espanyol": "Espanol", "rayo vallecano": "Vallecano", "real sociedad": "Sociedad",
    "deportivo alaves": "Alaves", "real oviedo": "Oviedo", "real valladolid": "Valladolid",
    "bayern munich": "Bayern Munich", "borussia monchengladbach": "M'gladbach",
    "bayer leverkusen": "Leverkusen", "eintracht frankfurt": "Ein Frankfurt",
    "st pauli": "St Pauli", "heidenheim": "Heidenheim", "vfb stuttgart": "Stuttgart",
    "borussia dortmund": "Dortmund", "koln": "FC Koln", "hamburger sv": "Hamburg",
    "tsg hoffenheim": "Hoffenheim", "mainz": "Mainz", "mainz 05": "Mainz",
    "fsv mainz 05": "Mainz", "werder bremen": "Werder Bremen", "freiburg": "Freiburg",
    "vfl wolfsburg": "Wolfsburg", "union berlin": "Union Berlin", "augsburg": "Augsburg",
    "paris saint germain": "Paris SG", "saint etienne": "St Etienne",
    "inter milan": "Inter", "inter": "Inter", "milan": "Milan",
    "hellas verona": "Verona", "roma": "Roma",
}

_STOP = {"fc", "afc", "cf", "ac", "as", "sc", "ssc", "us", "1", "club", "calcio", "de", "cd",
         "ud", "rc", "sv", "vfl", "tsg", "fsv", "sd", "ogc", "rcd", "stade", "olympique"}


def normalize(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[^a-z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _core(name: str) -> str:
    return " ".join(t for t in normalize(name).split() if t not in _STOP)


def match_team(name: str, known: list[str]) -> str | None:
    """Devuelve el nombre de ``known`` que corresponde a ``name`` (o None)."""
    if not known:
        return None
    if name in known:
        return name
    norm = normalize(name)
    for key in (norm, _core(name)):
        alias = ALIASES.get(key)
        if alias and alias in known:
            return alias
    by_norm = {normalize(k): k for k in known}
    if norm in by_norm:
        return by_norm[norm]
    by_core = {_core(k): k for k in known}
    core = _core(name)
    if core in by_core:
        return by_core[core]
    # Coincidencia por contención ("Brighton" dentro de "brighton hove albion")
    for c, original in by_core.items():
        if c and (c in core or core in c) and min(len(c), len(core)) >= 4:
            return original
    hit = difflib.get_close_matches(core, list(by_core), n=1, cutoff=0.6)
    return by_core[hit[0]] if hit else None
