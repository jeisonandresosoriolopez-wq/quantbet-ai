"""Fuente en vivo: ESPN Scoreboard API (sin API key).

Proporciona calendario real y cuotas (apertura y línea actual de DraftKings/mercado)
para:
- Amistosos Internacionales FIFA (`fifa.friendly`)
- UEFA Nations League (`uefa.nations`)
- CONCACAF Nations League (`concacaf.nations.league`)
- Las 5 grandes ligas europeas (`eng.1`, `esp.1`, `ita.1`, `ger.1`, `fra.1`)
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .. import config
from ..model import value
from .team_mapping import match_team

log = logging.getLogger("quantbet.espn")

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QuantBet/1.1"


def american_to_decimal(am_str: str | int | float | None) -> float | None:
    if am_str is None or am_str == "":
        return None
    s = str(am_str).strip().upper()
    if s == "EVEN":
        return 2.0
    try:
        v = float(s.replace("+", ""))
    except ValueError:
        return None
    if v == 0:
        return None
    if v > 0:
        return round(1.0 + v / 100.0, 3)
    return round(1.0 + 100.0 / abs(v), 3)


def _extract_price(node: dict | None) -> tuple[float | None, float | None]:
    """Devuelve (cuota_actual, cuota_apertura) en formato decimal desde un nodo ESPN."""
    if not node or not isinstance(node, dict):
        return None, None
    cur = (node.get("current") or {}).get("odds") or (node.get("close") or {}).get("odds")
    opn = (node.get("open") or {}).get("odds")
    dec_cur = american_to_decimal(cur)
    dec_opn = american_to_decimal(opn)
    return dec_cur or dec_opn, dec_opn or dec_cur


def _parse_odds(odds_list: list | None) -> dict:
    """Convierte el bloque `odds` de ESPN al formato interno de QuantBet."""
    valid = [o for o in (odds_list or []) if o and isinstance(o, dict)]
    if not valid:
        return {"1x2": {"best": {}, "avg": {}}, "ou25": {"best": {}, "avg": {}}, "ah": {"best": {}, "avg": {}, "line": None}}
    o = valid[0]
    provider = (o.get("provider") or {}).get("displayName") or "DraftKings / ESPN"

    # 1X2 (Moneyline)
    ml = o.get("moneyline") or {}
    h_cur, h_opn = _extract_price(ml.get("home"))
    a_cur, a_opn = _extract_price(ml.get("away"))
    d_cur, d_opn = _extract_price(ml.get("draw"))
    if d_cur is None and o.get("drawOdds"):
        d_cur = american_to_decimal((o.get("drawOdds") or {}).get("moneyLine"))
        d_opn = d_cur

    best_1x2, avg_1x2 = {}, {}
    for k, cur, opn in (("H", h_cur, h_opn), ("D", d_cur, d_opn), ("A", a_cur, a_opn)):
        if cur and opn:
            best_1x2[k] = max(cur, opn)
            best_1x2[f"{k}_book"] = f"{provider} ({'Actual' if cur >= opn else 'Apertura'})"
            avg_1x2[k] = cur
        elif cur:
            best_1x2[k] = cur
            best_1x2[f"{k}_book"] = provider
            avg_1x2[k] = cur

    # Totales (Over / Under)
    tot = o.get("total") or {}
    ou_line = o.get("overUnder")
    o_cur, o_opn = _extract_price(tot.get("over"))
    u_cur, u_opn = _extract_price(tot.get("under"))
    best_ou, avg_ou = {}, {}
    # Si la línea es 2.5 la usamos directo; si es otra (ej. 3.5), aún guardamos si es 2.5
    if ou_line in (None, 2.5) and o_cur and u_cur:
        best_ou["O"] = max(o_cur, o_opn or o_cur)
        best_ou["O_book"] = provider
        best_ou["U"] = max(u_cur, u_opn or u_cur)
        best_ou["U_book"] = provider
        avg_ou["O"] = o_cur
        avg_ou["U"] = u_cur

    # Spread / Hándicap Asiático: solo usamos líneas estrictas de cuarto/medio cuando la suma sin vig sea válida
    # (ESPN envía hándicap europeo de 3 vías en varios partidos, por lo que no lo mezclamos como hándicap asiático)
    best_ah, avg_ah, ah_line = {}, {}, None

    return {
        "1x2": {"best": best_1x2, "avg": avg_1x2},
        "ou25": {"best": best_ou, "avg": avg_ou, "alt_line": ou_line, "alt_over": o_cur, "alt_under": u_cur},
        "ah": {"best": best_ah, "avg": avg_ah, "line": ah_line},
    }


def _fetch_day(espn_slug: str, day_yyyymmdd: str, ttl_hours: float = 24.0) -> list[dict]:
    cache = config.CACHE_DIR / f"espn_{espn_slug}_{day_yyyymmdd}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except ValueError:
            pass
    url = f"{BASE}/{espn_slug}/scoreboard?dates={day_yyyymmdd}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            events = data.get("events", [])
        cache.write_text(json.dumps(events), encoding="utf-8")
        return events
    except Exception as exc:
        log.warning("ESPN falló para %s %s: %s", espn_slug, day_yyyymmdd, exc)
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        return []


def _form_score(form_str: str | None) -> float:
    """Convierte racha tipo 'WWLDW' en puntaje entre -1 y +1."""
    if not form_str:
        return 0.0
    weights = [0.12, 0.16, 0.20, 0.24, 0.28]
    chars = list(form_str.strip().upper()[-5:])
    if not chars:
        return 0.0
    ws = weights[-len(chars):]
    total_w = sum(ws)
    pts = sum(w * (1.0 if c == "W" else 0.0 if c == "D" else -1.0) for w, c in zip(ws, chars))
    return pts / total_w


def estimate_intl_lambdas(odds_block: dict, home_form: str | None, away_form: str | None) -> tuple[float, float]:
    """Deriva (lambda_home, lambda_away) para selecciones combinando mercado sin vig + impulso de forma."""
    # Total esperado de goles base
    ou = odds_block.get("ou25") or {}
    total_g = 2.62
    if ou.get("avg", {}).get("O") and ou.get("avg", {}).get("U"):
        p_over, _ = value.devig([ou["avg"]["O"], ou["avg"]["U"]])
        # Ajuste suave alrededor de 2.5 goles según P(Over 2.5)
        total_g = max(1.65, min(3.85, 2.55 + (p_over - 0.48) * 2.4))
    elif ou.get("alt_line"):
        total_g = float(ou["alt_line"])

    # Fuerza relativa desde 1X2 sin vig
    one_x_two = (odds_block.get("1x2") or {}).get("avg") or {}
    if all(one_x_two.get(k) for k in ("H", "D", "A")):
        ph, pd, pa = value.devig([one_x_two["H"], one_x_two["D"], one_x_two["A"]])
        share_h = (ph + 0.5 * pd)
    else:
        share_h = 0.53  # ligera ventaja local por defecto

    # Ajuste cuantitativo por racha reciente de últimos 5 partidos (Opta/ESPN Form Factor)
    fh, fa = _form_score(home_form), _form_score(away_form)
    form_diff = fh - fa  # entre -2 y +2

    lh = total_g * share_h * math.exp(0.11 * form_diff)
    la = total_g * (1.0 - share_h) * math.exp(-0.11 * form_diff)
    return max(0.20, round(lh, 3)), max(0.20, round(la, 3))


def fetch_upcoming_events(div: str, known_club_teams: list[str] | None = None,
                          days_ahead: int = 4, force: bool = False) -> list[dict]:
    """Descarga los partidos próximos de `div` desde hoy hasta `days_ahead` días."""
    meta = config.LEAGUES.get(div)
    if not meta or not meta.get("espn"):
        return []
    slug = meta["espn"]
    kind = meta["kind"]
    today_co = (datetime.now(timezone.utc) - timedelta(hours=5)).date()
    ttl = 0.0 if force else 2.0

    out = []
    seen = set()
    for d_off in range(0, days_ahead + 1):
        d_str = (today_co + timedelta(days=d_off)).strftime("%Y%m%d")
        for ev in _fetch_day(slug, d_str, ttl_hours=ttl):
            comp = (ev.get("competitions") or [None])[0]
            if not comp:
                continue
            status_name = (((comp.get("status") or {}).get("type") or {}).get("state") or "").lower()
            # Incluimos pre-partido y en juego del día
            h_c = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), None)
            a_c = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), None)
            if not h_c or not a_c:
                continue
            h_raw = (h_c.get("team") or {}).get("displayName", "").strip()
            a_raw = (a_c.get("team") or {}).get("displayName", "").strip()
            if not h_raw or not a_raw:
                continue

            if kind == "club" and known_club_teams:
                home = match_team(h_raw, known_club_teams) or h_raw
                away = match_team(a_raw, known_club_teams) or a_raw
            else:
                home, away = h_raw, a_raw

            ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            key = (div, home, away, ko.strftime("%Y-%m-%d"))
            if key in seen:
                continue
            seen.add(key)

            odds_blk = _parse_odds(comp.get("odds"))
            h_form = h_c.get("form") or ""
            a_form = a_c.get("form") or ""
            h_rec = ((h_c.get("records") or [{}])[0]).get("summary")
            a_rec = ((a_c.get("records") or [{}])[0]).get("summary")

            item = {
                "div": div,
                "kickoff": ko,
                "home": home,
                "away": away,
                "odds": odds_blk,
                "source": "ESPN / DraftKings Live",
                "home_form": list(h_form[-5:]),
                "away_form": list(a_form[-5:]),
                "home_record": h_rec,
                "away_record": a_rec,
                "state": status_name,
            }
            if status_name == "post":
                try:
                    item["fthg"] = int(h_c.get("score", 0))
                    item["ftag"] = int(a_c.get("score", 0))
                except ValueError:
                    pass
            out.append(item)
    return out
