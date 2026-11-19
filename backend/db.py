"""Persistencia SQLite: ajustes, picks (paper trading y apuestas manuales) y su liquidación."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    div TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    line REAL,
    name TEXT NOT NULL,
    odds REAL NOT NULL,
    p_model REAL, p_market REAL, p_real REAL,
    ev REAL,
    stake_pct REAL,
    stake_amount REAL,
    source TEXT NOT NULL DEFAULT 'auto',   -- auto (paper trading) | manual
    bookmaker TEXT,
    status TEXT NOT NULL DEFAULT 'open',   -- open | won | lost | push | half_won | half_lost
    score TEXT,
    profit REAL,
    closing_odds REAL,
    clv REAL,
    created_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(match_id, market, selection, source)
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock, connect() as conn:
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------- #
# Ajustes
# --------------------------------------------------------------------------- #
def get_settings() -> dict:
    settings = dict(config.DEFAULT_SETTINGS)
    settings.setdefault("price_basis", "avg")
    with _lock, connect() as conn:
        for row in conn.execute("SELECT key, value FROM settings"):
            settings[row["key"]] = json.loads(row["value"])
    return settings


ALLOWED = {
    "bankroll": (float, 1, 1e12), "kelly_fraction": (float, 0.05, 1.0),
    "max_stake_pct": (float, 0.001, 0.05), "min_ev": (float, 0.0, 0.5),
    "model_weight": (float, 0.0, 1.0), "min_bet": (float, 0, 1e9),
    "price_basis": (str, None, None), "currency": (str, None, None),
}


def save_settings(new: dict) -> dict:
    with _lock, connect() as conn:
        for key, val in new.items():
            if key not in ALLOWED:
                continue
            typ, lo, hi = ALLOWED[key]
            if typ is float:
                val = min(max(float(val), lo), hi)
            elif key == "price_basis" and val not in ("avg", "best"):
                continue
            conn.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, json.dumps(val)))
    return get_settings()


# --------------------------------------------------------------------------- #
# Picks
# --------------------------------------------------------------------------- #
def add_pick(match: dict, sel: dict, source: str = "auto", odds: float | None = None,
             stake_amount: float | None = None, bookmaker: str | None = None) -> bool:
    """Registra un pick. Devuelve False si ya existía."""
    with _lock, connect() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO picks (match_id, div, kickoff, home, away, market, selection,
               line, name, odds, p_model, p_market, p_real, ev, stake_pct, stake_amount, source,
               bookmaker, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (match["id"], match["div"], match["kickoff"], match["home"], match["away"],
             sel["market"], sel["selection"], sel.get("line"), sel["name"],
             odds or sel["odds"], sel["p_model"], sel.get("p_market"), sel["p_real"],
             sel["p_real"] * (odds or sel["odds"]) - 1, sel.get("stake_pct"),
             stake_amount if stake_amount is not None else sel.get("stake_amount"),
             source, bookmaker or sel.get("odds_source"),
             datetime.now().isoformat(timespec="seconds")))
        return cur.rowcount > 0


def open_picks() -> list[dict]:
    with _lock, connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM picks WHERE status='open'")]


def settle_pick(pick_id: int, status: str, score: str, profit: float,
                closing_odds: float | None, clv: float | None) -> None:
    with _lock, connect() as conn:
        conn.execute("""UPDATE picks SET status=?, score=?, profit=?, closing_odds=?, clv=?,
                        settled_at=? WHERE id=?""",
                     (status, score, profit, closing_odds, clv,
                      datetime.now().isoformat(timespec="seconds"), pick_id))


def delete_pick(pick_id: int) -> None:
    with _lock, connect() as conn:
        conn.execute("DELETE FROM picks WHERE id=?", (pick_id,))


def all_picks() -> list[dict]:
    with _lock, connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM picks ORDER BY kickoff DESC, id DESC")]
