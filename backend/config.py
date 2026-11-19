"""Configuración global de QuantBet."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "quantbet.db"
FRONTEND_DIR = ROOT / "frontend"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)


def _load_env() -> None:
    """Carga un archivo .env simple (KEY=VALUE) sin dependencias externas."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "").strip()
ODDS_API_REGION = os.environ.get("ODDS_API_REGION", "eu").strip() or "eu"
LOCAL_TZ = os.environ.get("LOCAL_TZ", "America/Bogota")
SOURCE_TZ = "Europe/London"  # football-data.co.uk publica horas del Reino Unido
PORT = int(os.environ.get("PORT", "8000"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "Pablo2026+").strip()
SECRET_SALT = os.environ.get("SECRET_SALT", "quantbet-super-secret-salt-2026").strip()

# Ligas y competiciones soportadas.
LEAGUES = {
    "E0": {"name": "Premier League", "country": "Inglaterra", "flag": "🏴",
           "odds_api": "soccer_epl", "espn": "eng.1", "kind": "club"},
    "SP1": {"name": "LaLiga", "country": "España", "flag": "🇪🇸",
            "odds_api": "soccer_spain_la_liga", "espn": "esp.1", "kind": "club"},
    "I1": {"name": "Serie A", "country": "Italia", "flag": "🇮🇹",
           "odds_api": "soccer_italy_serie_a", "espn": "ita.1", "kind": "club"},
    "D1": {"name": "Bundesliga", "country": "Alemania", "flag": "🇩🇪",
           "odds_api": "soccer_germany_bundesliga", "espn": "ger.1", "kind": "club"},
    "F1": {"name": "Ligue 1", "country": "Francia", "flag": "🇫🇷",
           "odds_api": "soccer_france_ligue_one", "espn": "fra.1", "kind": "club"},
    "INT_FR": {"name": "Amistosos Internacionales FIFA", "country": "Internacional", "flag": "🌍",
               "odds_api": "soccer_fifa_world_cup", "espn": "fifa.friendly", "kind": "intl"},
    "UEFA_NL": {"name": "UEFA Nations League", "country": "Europa", "flag": "🇪🇺",
                "odds_api": "soccer_uefa_nations_league", "espn": "uefa.nations", "kind": "intl"},
    "CONC_NL": {"name": "CONCACAF Nations League", "country": "CONCACAF", "flag": "🌎",
                "odds_api": "soccer_concacaf_nations_league", "espn": "concacaf.nations.league", "kind": "intl"},
    "COL1": {"name": "Colombia · Liga BetPlay & Copa", "country": "Colombia", "flag": "🇨🇴",
             "odds_api": "soccer_colombia_primera_a", "espn": None, "kind": "intl"},
    "MEX1": {"name": "México · Liga MX", "country": "México", "flag": "🇲🇽",
             "odds_api": "soccer_mexico_ligamx", "espn": "mex.1", "kind": "intl"},
    "ARG1": {"name": "Argentina · Liga Profesional", "country": "Argentina", "flag": "🇦🇷",
             "odds_api": "soccer_argentina_primera_division", "espn": "arg.1", "kind": "intl"},
    "BRA1": {"name": "Brasil · Brasileirão Serie A", "country": "Brasil", "flag": "🇧🇷",
             "odds_api": "soccer_brazil_campeonato", "espn": "bra.1", "kind": "intl"},
    "CHI1": {"name": "Chile · Primera División", "country": "Chile", "flag": "🇨🇱",
             "odds_api": "soccer_chile_campeonato", "espn": None, "kind": "intl"},
    "ECU1": {"name": "Ecuador · LigaPro Serie A", "country": "Ecuador", "flag": "🇪🇨",
             "odds_api": "soccer_ecuador_serie_a", "espn": None, "kind": "intl"},
    "PER1": {"name": "Perú · Liga 1", "country": "Perú", "flag": "🇵🇪",
             "odds_api": "soccer_peru_primera_division", "espn": None, "kind": "intl"},
    "USA1": {"name": "EE. UU. · MLS", "country": "EE. UU.", "flag": "🇺🇸",
             "odds_api": "soccer_usa_mls", "espn": "usa.1", "kind": "intl"},
    "NBA": {"name": "NBA Baloncesto", "country": "EE. UU.", "flag": "🏀",
            "odds_api": "basketball_nba", "espn": "nba", "kind": "nba"},
}

CLUB_LEAGUES = {k for k, v in LEAGUES.items() if v["kind"] == "club"}
INTL_LEAGUES = {k for k, v in LEAGUES.items() if v["kind"] == "intl"}
NBA_LEAGUES = {k for k, v in LEAGUES.items() if v["kind"] == "nba"}

# Parámetros por defecto (editables desde la pantalla de Ajustes).
DEFAULT_SETTINGS = {
    "bankroll": 20000.0,          # COP
    "currency": "COP",
    "kelly_fraction": 0.25,       # 1/4 Kelly
    "max_stake_pct": 0.02,        # tope duro del 2 %
    "min_ev": 0.03,               # umbral VALUE
    "model_weight": 0.35,         # peso del modelo vs. probabilidad del mercado (consenso Bayesiano)
    "min_bet": 1000.0,            # apuesta mínima típica de casas en Colombia (COP)
    "price_basis": "best",        # evaluar contra la mejor cuota disponible entre casas
}


def season_code(d: date | None = None, offset: int = 0) -> str:
    """Código de temporada de football-data.co.uk (ej. '2627' para 2026/27)."""
    d = d or date.today()
    start = d.year if d.month >= 7 else d.year - 1
    start += offset
    return f"{start % 100:02d}{(start + 1) % 100:02d}"
