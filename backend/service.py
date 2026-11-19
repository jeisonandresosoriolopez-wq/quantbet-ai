"""Orquestación: carga de datos, análisis diario, liquidación de picks y backtest."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config, db
from .model import nba, poisson, value
from .model.analysis import analyze, match_id
from .model.ratings import Ratings, fit, team_profile
from .sources import espn, football_data, odds_api, wplay

log = logging.getLogger("quantbet.service")

_lock = threading.RLock()
_league_cache: dict[str, tuple[float, list[dict], list[dict]]] = {}
_analysis_cache: dict = {"ts": 0, "settings": None, "data": None}
_backtest_cache: dict = {}
STATE = {"last_run": None, "last_error": None, "running": False}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Datos de liga
# --------------------------------------------------------------------------- #
def league_data(div: str, max_age_s: float = 3 * 3600, force: bool = False):
    with _lock:
        hit = _league_cache.get(div)
        if hit and not force and time.time() - hit[0] < max_age_s:
            return hit[1], hit[2]
        current = football_data.season_results(div, config.season_code(), ttl_hours=0 if force else 6)
        previous = football_data.season_results(div, config.season_code(offset=-1), ttl_hours=24 * 30)
        _league_cache[div] = (time.time(), current, previous)
        return current, previous


def ratings_for(div: str, as_of: datetime | None = None) -> tuple[Ratings | None, list[dict]]:
    current, previous = league_data(div)
    return fit(current, previous, as_of or now_utc()), current


def teams(div: str) -> list[str]:
    r, _ = ratings_for(div)
    return r.teams if r else []


# --------------------------------------------------------------------------- #
# Partidos próximos (Amistosos FIFA, Nations League y 5 Grandes Ligas)
# --------------------------------------------------------------------------- #
def upcoming(force: bool = False) -> list[dict]:
    fixtures = football_data.upcoming_fixtures(ttl_hours=0 if force else 3)
    for f in fixtures:
        f["source"] = "football-data.co.uk"
    by_key = {(f["div"], f["home"], f["away"]): f for f in fixtures}

    # 1. Integrar calendario y cuotas en vivo desde ESPN Scoreboard (Amistosos + Nations League + Ligas)
    for div, meta in config.LEAGUES.items():
        if meta["kind"] == "nba":
            for nba_ev in wplay.fetch_nba_fixtures(force=force):
                by_key[("NBA", nba_ev["home"], nba_ev["away"])] = nba_ev
            continue
        known = teams(div) if meta["kind"] == "club" else None
        for ev in espn.fetch_upcoming_events(div, known_club_teams=known, days_ahead=6, force=force):
            if ev.get("state") == "post":
                continue
            key = (div, ev["home"], ev["away"])
            if key in by_key:
                base = by_key[key]
                for mk, blk in ev["odds"].items():
                    if not base["odds"].get(mk, {}).get("best") and blk.get("best"):
                        base["odds"][mk] = blk
            else:
                by_key[key] = ev

    # 2. Integrar cuotas oficiales de Wplay.co (Colombia) en paralelo para máxima velocidad
    import concurrent.futures
    def _load_wplay_div(div):
        div_teams = sorted({t for (d, h, a) in by_key if d == div for t in (h, a)})
        return div, wplay.fetch_division_odds(div, div_teams, force=force)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        wplay_results = list(ex.map(_load_wplay_div, list(config.LEAGUES.keys())))

    for div, wplay_map in wplay_results:
        for (wh, wa), wodds in wplay_map.items():
            # Buscar tanto en orden directo como invertido (algunos amistosos figuran con localía invertida en Wplay)
            key = (div, wh, wa)
            inv_key = (div, wa, wh)
            if key in by_key:
                base = by_key[key]
                for mk in ("1x2", "ou25", "btts", "ah"):
                    w_blk = wodds.get(mk, {})
                    if w_blk.get("best"):
                        old_best = (base["odds"].get(mk) or {}).get("best") or {}
                        merged_best = dict(w_blk["best"])
                        for sel_k, w_price in list(w_blk["best"].items()):
                            if sel_k.endswith("_book") or not isinstance(w_price, (int, float)):
                                continue
                            alt_price = old_best.get(sel_k)
                            if alt_price and alt_price > w_price:
                                merged_best[sel_k] = alt_price
                                merged_best[f"{sel_k}_book"] = f"BetPlay/Consenso ({alt_price:.2f}) vs Wplay ({w_price:.2f})"
                            else:
                                merged_best[f"{sel_k}_book"] = f"Wplay.co ({w_price:.2f})"
                        w_copy = dict(w_blk)
                        w_copy["best"] = merged_best
                        base["odds"][mk] = w_copy
                base["source"] = "Wplay.co + BetPlay / Consenso"
                base["wplay_url"] = wodds.get("wplay_url")
            elif inv_key in by_key:
                base = by_key[inv_key]
                # Invertimos H y A porque Wplay listó los equipos al revés
                b1 = wodds.get("1x2", {}).get("best") or {}
                if b1:
                    base["odds"]["1x2"] = {
                        "best": {"H": b1["A"], "D": b1["D"], "A": b1["H"],
                                 "H_book": "Wplay.co", "D_book": "Wplay.co", "A_book": "Wplay.co"},
                        "avg": {"H": b1["A"], "D": b1["D"], "A": b1["H"]},
                    }
                for mk in ("ou25", "btts"):
                    if wodds.get(mk, {}).get("best"):
                        base["odds"][mk] = wodds[mk]
                ah_b = wodds.get("ah", {}).get("best") or {}
                if ah_b and wodds["ah"].get("line") is not None:
                    base["odds"]["ah"] = {
                        "line": -float(wodds["ah"]["line"]),
                        "best": {"H": ah_b["A"], "A": ah_b["H"], "H_book": "Wplay.co", "A_book": "Wplay.co"},
                        "avg": {"H": ah_b["A"], "A": ah_b["H"]},
                    }
                base["source"] = "Wplay.co (Colombia)"
                base["wplay_url"] = wodds.get("wplay_url")
            else:
                # Partido presente directamente en Wplay.co (ej. Liga BetPlay / Copa Colombia)
                by_key[key] = {
                    "div": div,
                    "kickoff": wodds.get("kickoff") or now_utc(),
                    "home": wh,
                    "away": wa,
                    "odds": {mk: wodds.get(mk, {}) for mk in ("1x2", "ou25", "btts", "ah")},
                    "source": "Wplay.co (Colombia)",
                    "wplay_url": wodds.get("wplay_url"),
                    "home_form": [],
                    "away_form": [],
                }

    # 3. Integrar The Odds API si el usuario configuró clave
    if odds_api.enabled():
        for div in config.CLUB_LEAGUES:
            for ev in odds_api.fetch_league(div, teams(div), force=force):
                key = (div, ev["home"], ev["away"])
                if key in by_key:
                    base = by_key[key]
                    merged = dict(base["odds"])
                    for mk, blk in ev["odds"].items():
                        if blk.get("best"):
                            merged[mk] = blk
                    base["odds"] = merged
                    base["source"] = "The Odds API + football-data"
                else:
                    by_key[key] = ev

    lo, hi = now_utc() - timedelta(hours=3), now_utc() + timedelta(days=7)
    return sorted((f for f in by_key.values() if lo <= f["kickoff"] <= hi),
                  key=lambda f: f["kickoff"])


def _intl_dummy_ratings(home: str, away: str, lh: float, la: float) -> Ratings:
    return Ratings(
        mu_home=1.40,
        mu_away=1.18,
        att={home: lh / 1.40, away: la / 1.18},
        defn={home: 1.0, away: 1.0},
        teams=[home, away],
        uses_xg=True,
        n_matches={home: 10, away: 10},
    )


def analyze_upcoming(force: bool = False) -> dict:
    settings = db.get_settings()
    with _lock:
        c = _analysis_cache
        if (not force and c["data"] is not None and c["settings"] == settings
                and time.time() - c["ts"] < 1800):
            return c["data"]
        odds_age = football_data.cache_age_hours("fixtures.csv")
        matches, rating_cache = [], {}
        upcoming_list = upcoming(force=force)
        is_recent_round = False

        for f in upcoming_list:
            div = f["div"]
            meta = config.LEAGUES[div]
            if meta["kind"] == "nba":
                res = nba.analyze_nba_match(f, settings)
                matches.append(res)
            elif meta["kind"] == "intl":
                h_form_str = "".join(f.get("home_form") or [])
                a_form_str = "".join(f.get("away_form") or [])
                lh, la = espn.estimate_intl_lambdas(f.get("odds") or {}, h_form_str, a_form_str)
                ratings = _intl_dummy_ratings(f["home"], f["away"], lh, la)
                profiles = {
                    f["home"]: {"team": f["home"], "played": 10, "form": f.get("home_form") or [], "record": f.get("home_record")},
                    f["away"]: {"team": f["away"], "played": 10, "form": f.get("away_form") or [], "record": f.get("away_record")},
                }
                res = analyze(f, ratings, profiles, settings, None, override_lambdas=(lh, la))
                res["league"] = meta
                matches.append(res)
            else:
                if div not in rating_cache:
                    rating_cache[div] = ratings_for(div)
                ratings, current = rating_cache[div]
                if ratings is None:
                    continue
                as_of = now_utc()
                profiles = {t: team_profile(t, current, as_of) for t in (f["home"], f["away"])}
                age = None if "ESPN" in f.get("source", "") or "Odds API" in f.get("source", "") else odds_age
                res = analyze(f, ratings, profiles, settings, age)
                res["league"] = meta
                matches.append(res)

        data = {
            "generated_at": now_utc().isoformat(),
            "is_recent_round": is_recent_round,
            "matches": matches,
            "value_count": sum(1 for m in matches if m["has_value"]),
            "settings": settings,
        }
        _analysis_cache.update(ts=time.time(), settings=settings, data=data)
        return data


def find_match(mid: str) -> dict | None:
    data = analyze_upcoming()
    return next((m for m in data["matches"] if m["id"] == mid), None)


# --------------------------------------------------------------------------- #
# Enfrentamiento libre (con cuotas manuales opcionales)
# --------------------------------------------------------------------------- #
def manual_odds_block(manual: dict | None) -> dict:
    """Convierte cuotas digitadas por el usuario al formato interno."""
    out = {}
    if not manual:
        return out
    for mk, sels in (("1x2", ["H", "D", "A"]), ("ou25", ["O", "U"]), ("btts", ["Y", "N"]),
                     ("ah", ["H", "A"])):
        m = manual.get(mk) or {}
        prices = {s: float(m[s]) for s in sels if m.get(s) and float(m[s]) > 1}
        if not prices:
            continue
        blk = {"best": {**prices, **{f"{s}_book": "Tu casa" for s in prices}},
               "avg": prices if len(prices) == len(sels) else {}}
        if mk == "ah":
            if m.get("line") in (None, ""):
                continue
            blk["line"] = float(m["line"])
        out[mk] = blk
    return out


def matchup(div: str, home: str, away: str, manual: dict | None = None) -> dict:
    meta = config.LEAGUES[div]
    settings = dict(db.get_settings())
    settings["price_basis"] = "best"  # con cuotas manuales usamos exactamente la cuota digitada
    as_of = now_utc()
    odds_blk = manual_odds_block(manual)
    fixture = {"div": div, "home": home, "away": away, "kickoff": as_of,
               "odds": odds_blk, "source": "Cuotas manuales"}
    if meta["kind"] == "intl":
        lh, la = espn.estimate_intl_lambdas(odds_blk, None, None)
        ratings = _intl_dummy_ratings(home, away, lh, la)
        profiles = {home: {"team": home, "played": 10}, away: {"team": away, "played": 10}}
        res = analyze(fixture, ratings, profiles, settings, override_lambdas=(lh, la))
        res["league"] = meta
        return res
    ratings, current = ratings_for(div)
    if ratings is None:
        raise ValueError("No hay datos suficientes para esta liga")
    profiles = {t: team_profile(t, current, as_of) for t in (home, away)}
    res = analyze(fixture, ratings, profiles, settings)
    res["league"] = meta
    return res


# --------------------------------------------------------------------------- #
# Liquidación
# --------------------------------------------------------------------------- #
def outcome(market: str, selection: str, line: float | None, hg: int, ag: int) -> str:
    if market == "1x2":
        res = "H" if hg > ag else "A" if ag > hg else "D"
        return "won" if res == selection else "lost"
    if market == "ou25":
        over = hg + ag > 2.5
        return "won" if (over and selection == "O") or (not over and selection == "U") else "lost"
    if market == "btts":
        yes = hg > 0 and ag > 0
        return "won" if (yes and selection == "Y") or (not yes and selection == "N") else "lost"
    if market == "ah":
        home_line = line if selection == "H" else -line
        o = poisson.ah_outcomes({hg - ag: 1.0}, home_line, selection)
        return {"win": "won", "half_win": "half_won", "push": "push",
                "half_loss": "half_lost", "loss": "lost"}[max(o, key=o.get)]
    raise ValueError(market)


def unit_return(status: str, odds: float) -> float:
    return {"won": odds - 1, "half_won": (odds - 1) / 2, "push": 0.0,
            "half_lost": -0.5, "lost": -1.0}.get(status, 0.0)


def closing_fair(closing: dict, market: str, selection: str, line: float | None) -> float | None:
    """Probabilidad justa de cierre (sin margen) de una selección, para medir CLV."""
    sels = {"1x2": ["H", "D", "A"], "ou25": ["O", "U"], "ah": ["H", "A"]}.get(market)
    blk = closing.get(market) if closing else None
    if not sels or not blk:
        return None
    if market == "ah":
        cl = blk.get("line")
        own = cl if selection == "H" else (-cl if cl is not None else None)
        if own is None or line is None or abs(own - line) > 1e-9:
            return None
    odds = [(blk.get("avg") or {}).get(s) for s in sels]
    if not all(odds):
        return None
    return dict(zip(sels, value.devig(odds)))[selection]


def settle_open() -> int:
    settled = 0
    for p in db.open_picks():
        ko = datetime.fromisoformat(p["kickoff"])
        if now_utc() < ko + timedelta(hours=2, minutes=15):
            continue
        current, _ = league_data(p["div"])
        res = next((m for m in current if m["home"] == p["home"] and m["away"] == p["away"]
                    and abs((m["kickoff"] - ko).total_seconds()) < 3 * 86400), None)
        if not res:
            continue
        status = outcome(p["market"], p["selection"], p["line"], res["fthg"], res["ftag"])
        profit = unit_return(status, p["odds"]) * (p["stake_amount"] or 0)
        pc = closing_fair(res["closing"], p["market"], p["selection"], p["line"])
        clv = p["odds"] * pc - 1 if pc else None
        close_odds = 1 / pc if pc else None
        db.settle_pick(p["id"], status, f"{res['fthg']}-{res['ftag']}", profit, close_odds, clv)
        settled += 1
    return settled


# --------------------------------------------------------------------------- #
# Ejecución diaria
# --------------------------------------------------------------------------- #
def run_daily(force: bool = True) -> dict:
    if STATE["running"]:
        return {"ok": False, "message": "Ya hay una ejecución en curso"}
    STATE["running"] = True
    try:
        for div in config.CLUB_LEAGUES:
            league_data(div, force=force)
        data = analyze_upcoming(force=True)
        new = 0
        for m in data["matches"]:
            bp = m["best_pick"]
            if bp and bp["label"] == "VALUE" and datetime.fromisoformat(m["kickoff"]) > now_utc():
                new += db.add_pick(m, bp, source="auto")
        settled = settle_open()
        STATE.update(last_run=now_utc().isoformat(), last_error=None)
        return {"ok": True, "matches": len(data["matches"]), "value": data["value_count"],
                "new_picks": new, "settled": settled}
    except Exception as exc:  # noqa: BLE001
        log.exception("Error en la ejecución diaria")
        STATE["last_error"] = str(exc)
        return {"ok": False, "message": str(exc)}
    finally:
        STATE["running"] = False


# --------------------------------------------------------------------------- #
# Historial y métricas
# --------------------------------------------------------------------------- #
def history() -> dict:
    picks = db.all_picks()
    settings = db.get_settings()
    settled = sorted((p for p in picks if p["status"] != "open"), key=lambda p: p["kickoff"])
    staked = sum(p["stake_amount"] or 0 for p in settled)
    profit = sum(p["profit"] or 0 for p in settled)
    units = [unit_return(p["status"], p["odds"]) for p in settled]
    clvs = [p["clv"] for p in settled if p["clv"] is not None]
    curve, bank = [], settings["bankroll"]
    for p in settled:
        bank += p["profit"] or 0
        curve.append({"t": p["kickoff"], "bankroll": round(bank, 2)})
    wins = sum(1 for p in settled if p["status"] in ("won", "half_won"))
    return {
        "picks": picks,
        "summary": {
            "total": len(picks), "open": len(picks) - len(settled), "settled": len(settled),
            "hit_rate": wins / len(settled) if settled else None,
            "staked": staked, "profit": profit,
            "roi": profit / staked if staked else None,
            "flat_roi": sum(units) / len(units) if units else None,
            "avg_clv": sum(clvs) / len(clvs) if clvs else None,
            "avg_ev": sum(p["ev"] or 0 for p in picks) / len(picks) if picks else None,
        },
        "curve": curve,
        "start_bankroll": settings["bankroll"],
    }


# --------------------------------------------------------------------------- #
# Backtest walk-forward sobre la temporada actual
# --------------------------------------------------------------------------- #
def backtest(basis: str = "avg", min_matches: int = 5) -> dict:
    settings = dict(db.get_settings())
    settings["price_basis"] = basis
    key = (basis, tuple(sorted(settings.items())))
    if key in _backtest_cache and time.time() - _backtest_cache[key]["ts"] < 6 * 3600:
        return _backtest_cache[key]["data"]

    bets, brier_model, brier_mkt, brier_real, n_cal = [], 0.0, 0.0, 0.0, 0
    calib_bins = [[0, 0.0, 0.0] for _ in range(10)]  # n, sum_p, sum_hits
    for div in config.CLUB_LEAGUES:
        current, previous = league_data(div)
        by_day: dict[str, list[dict]] = {}
        for m in current:
            by_day.setdefault(m["kickoff"].strftime("%Y-%m-%d"), []).append(m)
        for day in sorted(by_day):
            day_matches = by_day[day]
            as_of = min(m["kickoff"] for m in day_matches) - timedelta(minutes=1)
            ratings = fit(current, previous, as_of)
            if ratings is None:
                continue
            for m in day_matches:
                n = min(ratings.n_matches.get(m["home"], 0), ratings.n_matches.get(m["away"], 0))
                if n < min_matches:
                    continue
                profiles = {t: team_profile(t, current, as_of) for t in (m["home"], m["away"])}
                res = analyze(m, ratings, profiles, settings)
                # Calibración 1X2
                actual = "H" if m["fthg"] > m["ftag"] else "A" if m["ftag"] > m["fthg"] else "D"
                sels = {s["selection"]: s for s in res["selections"] if s["market"] == "1x2"}
                if all(sels[s]["p_market"] is not None for s in "HDA"):
                    n_cal += 1
                    for s in "HDA":
                        y = 1.0 if s == actual else 0.0
                        brier_model += (sels[s]["p_model"] - y) ** 2
                        brier_mkt += (sels[s]["p_market"] - y) ** 2
                        brier_real += (sels[s]["p_real"] - y) ** 2
                        b = min(int(sels[s]["p_model"] * 10), 9)
                        calib_bins[b][0] += 1
                        calib_bins[b][1] += sels[s]["p_model"]
                        calib_bins[b][2] += y
                bp = res["best_pick"]
                if not bp or bp["label"] != "VALUE" or bp["market"] == "btts":
                    continue
                status = outcome(bp["market"], bp["selection"], bp.get("line"), m["fthg"], m["ftag"])
                pc = closing_fair(m["closing"], bp["market"], bp["selection"], bp.get("line"))
                bets.append({
                    "date": day, "div": div, "match": f"{m['home']} vs {m['away']}",
                    "pick": bp["name"], "market": bp["market_name"], "odds": bp["odds"],
                    "ev": bp["ev"], "stake_pct": bp["stake_pct"], "status": status,
                    "score": f"{m['fthg']}-{m['ftag']}",
                    "units": unit_return(status, bp["odds"]),
                    "clv": bp["odds"] * pc - 1 if pc else None,
                })
    bets.sort(key=lambda b: b["date"])
    bank, curve = settings["bankroll"], []
    for b in bets:
        stake_amt = b["stake_pct"] * bank
        bank += stake_amt * b["units"]
        curve.append({"t": b["date"], "bankroll": round(bank, 2)})
    clvs = [b["clv"] for b in bets if b["clv"] is not None]
    data = {
        "basis": basis,
        "n_bets": len(bets),
        "hit_rate": sum(1 for b in bets if b["units"] > 0) / len(bets) if bets else None,
        "flat_roi": sum(b["units"] for b in bets) / len(bets) if bets else None,
        "flat_units": sum(b["units"] for b in bets),
        "avg_ev": sum(b["ev"] for b in bets) / len(bets) if bets else None,
        "avg_clv": sum(clvs) / len(clvs) if clvs else None,
        "positive_clv_rate": sum(1 for c in clvs if c > 0) / len(clvs) if clvs else None,
        "final_bankroll": bank, "start_bankroll": settings["bankroll"],
        "calibration": {
            "n_matches": n_cal,
            "brier_model": brier_model / n_cal if n_cal else None,
            "brier_market": brier_mkt / n_cal if n_cal else None,
            "brier_blend": brier_real / n_cal if n_cal else None,
            "bins": [{"p": b[1] / b[0], "freq": b[2] / b[0], "n": b[0]} for b in calib_bins if b[0]],
        },
        "curve": curve,
        "bets": bets[-200:],
    }
    _backtest_cache[key] = {"ts": time.time(), "data": data}
    return data
