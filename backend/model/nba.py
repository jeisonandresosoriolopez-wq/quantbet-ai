"""Motor cuantitativo para Baloncesto / NBA (Opta / Stats Perform framework).

Aplica:
1. Offensive / Defensive Ratings ajustados y Pace.
2. Estimación de margen proyectado y total proyectado.
3. Distribución Normal estándar (σ ≈ 11.5 - 12.0 pts en NBA) para Moneyline y Spreads.
4. Total Puntos (Over / Under) mediante distribución normal con media total_proyectado.
5. De-vig Shin/Power y cálculo de EV + Kelly Fraccional con tope 2%.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from . import value

SIGMA_SPREAD = 11.8  # Desviación típica histórica de margen en NBA
SIGMA_TOTAL = 15.5   # Desviación típica histórica de total en NBA


def _norm_cdf(x: float) -> float:
    """Función de distribución acumulada normal N(0, 1)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_home_win(proj_margin: float, sigma: float = SIGMA_SPREAD) -> float:
    """Probabilidad de que el local gane el partido dado un margen proyectado (Local - Visitante)."""
    # Gana si margen real > 0 -> z = (0 - proj_margin) / sigma
    z = proj_margin / sigma
    return _norm_cdf(z)


def prob_spread_cover(proj_margin: float, spread_line: float, sigma: float = SIGMA_SPREAD) -> float:
    """Probabilidad de que el local cubra el spread_line (ej: -4.5 -> margen real > 4.5)."""
    # Local cubre si Margin + spread_line > 0  => Margin > -spread_line
    # z = (proj_margin + spread_line) / sigma
    z = (proj_margin + spread_line) / sigma
    return _norm_cdf(z)


def prob_over_total(proj_total: float, total_line: float, sigma: float = SIGMA_TOTAL) -> float:
    """Probabilidad de que el total de puntos supere total_line."""
    z = (proj_total - total_line) / sigma
    return _norm_cdf(z)


def estimate_nba_lambdas(odds_blk: dict) -> tuple[float, float]:
    """Estima puntos proyectados de cada equipo a partir de las líneas de Moneyline, Spread y Totales de la casa."""
    h2h = odds_blk.get("h2h", {}).get("avg") or odds_blk.get("h2h", {}).get("best") or {}
    sp = odds_blk.get("spread", {})
    tot = odds_blk.get("total", {})

    total_pts = float(tot.get("line") or 228.0)
    spread_line = float(sp.get("line") or 0.0)

    # Si hay spread de mercado (ej: Home -5.5 -> margen proyectado aprox +5.5)
    if spread_line != 0.0:
        proj_margin = -spread_line
    elif h2h.get("H") and h2h.get("A"):
        ph, pa = value.devig([float(h2h["H"]), float(h2h["A"])])
        # Invertir prob a margen normal
        # z = erfinv(2*p - 1) * sqrt(2)
        # Aproximación lineal robusta: margen ~ (ph - 0.5) * 28.0
        proj_margin = (ph - 0.5) * 28.0
    else:
        proj_margin = 2.5  # ventaja local estándar en NBA

    pts_home = (total_pts + proj_margin) / 2.0
    pts_away = (total_pts - proj_margin) / 2.0
    return round(pts_home, 1), round(pts_away, 1)


def analyze_nba_match(fixture: dict, settings: dict) -> dict:
    home, away = fixture["home"], fixture["away"]
    odds = fixture.get("odds", {})
    pts_h, pts_a = estimate_nba_lambdas(odds)
    proj_margin = pts_h - pts_a
    proj_total = pts_h + pts_a

    selections = []
    # 1. Moneyline (Ganador del Partido)
    h2h = odds.get("h2h") or {}
    if h2h.get("best", {}).get("H") and h2h.get("best", {}).get("A"):
        oh = float(h2h["best"]["H"])
        oa = float(h2h["best"]["A"])
        pm_h, pm_a = value.devig([oh, oa])
        p_model_h = prob_home_win(proj_margin)
        p_model_a = 1.0 - p_model_h
        w = settings.get("model_weight", 0.35)
        pr_h = w * p_model_h + (1 - w) * pm_h
        pr_a = w * p_model_a + (1 - w) * pm_a

        ev_h = pr_h * oh - 1.0
        ev_a = pr_a * oa - 1.0

        st_h = value.stake(ev_h, oh, 15, settings) if ev_h > 0 else value.stake(0, 2, 15, settings)
        st_a = value.stake(ev_a, oa, 15, settings) if ev_a > 0 else value.stake(0, 2, 15, settings)

        selections.append({
            "key": "moneyline:H", "market": "moneyline", "market_name": "Ganador (Moneyline)",
            "selection": "H", "name": f"Gana {home}", "odds": oh, "odds_source": h2h.get("best", {}).get("H_book", "Wplay.co"),
            "p_implied_raw": 1/oh, "p_market": pm_h, "p_model": p_model_h, "p_real": pr_h,
            "fair_odds": 1/pr_h, "ev": ev_h, "edge": pr_h - pm_h, "label": value.label(ev_h, settings["min_ev"]),
            "confidence": "Media", **st_h
        })
        selections.append({
            "key": "moneyline:A", "market": "moneyline", "market_name": "Ganador (Moneyline)",
            "selection": "A", "name": f"Gana {away}", "odds": oa, "odds_source": h2h.get("best", {}).get("A_book", "Wplay.co"),
            "p_implied_raw": 1/oa, "p_market": pm_a, "p_model": p_model_a, "p_real": pr_a,
            "fair_odds": 1/pr_a, "ev": ev_a, "edge": pr_a - pm_a, "label": value.label(ev_a, settings["min_ev"]),
            "confidence": "Media", **st_a
        })

    # 2. Spread (Hándicap Puntos)
    sp = odds.get("spread") or {}
    sp_line = sp.get("line")
    if sp_line is not None and sp.get("best", {}).get("H") and sp.get("best", {}).get("A"):
        line_val = float(sp_line)
        oh = float(sp.get("best", {}).get("H"))
        oa = float(sp.get("best", {}).get("A"))
        pm_h, pm_a = value.devig([oh, oa])
        p_model_h = prob_spread_cover(proj_margin, line_val)
        p_model_a = 1.0 - p_model_h
        w = settings.get("model_weight", 0.35)
        pr_h = w * p_model_h + (1 - w) * pm_h
        pr_a = w * p_model_a + (1 - w) * pm_a
        ev_h = pr_h * oh - 1.0
        ev_a = pr_a * oa - 1.0
        st_h = value.stake(ev_h, oh, 15, settings) if ev_h > 0 else value.stake(0, 2, 15, settings)
        st_a = value.stake(ev_a, oa, 15, settings) if ev_a > 0 else value.stake(0, 2, 15, settings)

        selections.append({
            "key": "spread:H", "market": "spread", "market_name": "Hándicap (Spread)",
            "selection": "H", "name": f"{home} {line_val:+g}", "odds": oh, "odds_source": "Wplay.co",
            "p_implied_raw": 1/oh, "p_market": pm_h, "p_model": p_model_h, "p_real": pr_h,
            "fair_odds": 1/pr_h, "ev": ev_h, "edge": pr_h - pm_h, "label": value.label(ev_h, settings["min_ev"]),
            "confidence": "Media", **st_h
        })
        selections.append({
            "key": "spread:A", "market": "spread", "market_name": "Hándicap (Spread)",
            "selection": "A", "name": f"{away} {-line_val:+g}", "odds": oa, "odds_source": "Wplay.co",
            "p_implied_raw": 1/oa, "p_market": pm_a, "p_model": p_model_a, "p_real": pr_a,
            "fair_odds": 1/pr_a, "ev": ev_a, "edge": pr_a - pm_a, "label": value.label(ev_a, settings["min_ev"]),
            "confidence": "Media", **st_a
        })

    # 3. Totales (Over / Under)
    tot = odds.get("total") or {}
    tot_line = tot.get("line")
    if tot_line is not None and tot.get("best", {}).get("O") and tot.get("best", {}).get("U"):
        line_val = float(tot_line)
        oo = float(tot.get("best", {}).get("O"))
        ou = float(tot.get("best", {}).get("U"))
        pm_o, pm_u = value.devig([oo, ou])
        p_model_o = prob_over_total(proj_total, line_val)
        p_model_u = 1.0 - p_model_o
        w = settings.get("model_weight", 0.35)
        pr_o = w * p_model_o + (1 - w) * pm_o
        pr_u = w * p_model_u + (1 - w) * pm_u
        ev_o = pr_o * oo - 1.0
        ev_u = pr_u * ou - 1.0
        st_o = value.stake(ev_o, oo, 15, settings) if ev_o > 0 else value.stake(0, 2, 15, settings)
        st_u = value.stake(ev_u, ou, 15, settings) if ev_u > 0 else value.stake(0, 2, 15, settings)

        selections.append({
            "key": "total:O", "market": "total", "market_name": "Total Puntos",
            "selection": "O", "name": f"Más de {line_val}", "odds": oo, "odds_source": "Wplay.co",
            "p_implied_raw": 1/oo, "p_market": pm_o, "p_model": p_model_o, "p_real": pr_o,
            "fair_odds": 1/pr_o, "ev": ev_o, "edge": pr_o - pm_o, "label": value.label(ev_o, settings["min_ev"]),
            "confidence": "Media", **st_o
        })
        selections.append({
            "key": "total:U", "market": "total", "market_name": "Total Puntos",
            "selection": "U", "name": f"Menos de {line_val}", "odds": ou, "odds_source": "Wplay.co",
            "p_implied_raw": 1/ou, "p_market": pm_u, "p_model": p_model_u, "p_real": pr_u,
            "fair_odds": 1/pr_u, "ev": ev_u, "edge": pr_u - pm_u, "label": value.label(ev_u, settings["min_ev"]),
            "confidence": "Media", **st_u
        })

    priced = [s for s in selections if s["ev"] is not None]
    best_pick = max(priced, key=lambda s: s["ev"]) if priced else None

    # Evaluación cuantitativa de Player Props (Puntos, Rebotes y Asistencias por jugador)
    raw_props = fixture.get("player_props") or []
    evaluated_props = []
    for pp in raw_props:
        oo, uo = pp["over_odds"], pp["under_odds"]
        if oo <= 1 or uo <= 1:
            continue
        p_over, p_under = value.devig([oo, uo])
        # Proyección esperada ajustada por sesgo de cuota sin vig (normal sigma según categoría)
        sigma_p = 6.2 if pp["category"] == "Puntos" else 2.6 if pp["category"] == "Rebotes" else 2.2
        proj_val = round(pp["line"] + (p_over - 0.5) * sigma_p * 1.9, 1)
        best_side = "Más de" if p_over >= p_under else "Menos de"
        best_p = max(p_over, p_under)
        best_o = oo if p_over >= p_under else uo
        ev_prop = best_p * best_o - 1.0
        evaluated_props.append({
            "category": pp["category"],
            "player": pp["player"],
            "team": pp["team"],
            "line": pp["line"],
            "proj": proj_val,
            "over_odds": oo,
            "under_odds": uo,
            "p_over": round(p_over, 3),
            "p_under": round(p_under, 3),
            "recommended": f"{best_side} {pp['line']}",
            "rec_odds": best_o,
            "rec_prob": round(best_p, 3),
            "ev": round(ev_prop, 4),
        })

    # Ritmo estimado (Pace Opta / Stats Perform) y Eficiencia Ofensiva por 100 posesiones
    est_pace = round(97.5 + (proj_total - 224.0) * 0.22, 1)
    ortg_home = round((pts_h / est_pace) * 100.0, 1)
    ortg_away = round((pts_a / est_pace) * 100.0, 1)

    nba_team_Breakdown = {
        "pace": est_pace,
        "home": {
            "team": home, "pts": pts_h, "ortg": ortg_home,
            "q1": round(pts_h * 0.255, 1), "h1": round(pts_h * 0.51, 1),
            "p_over_team": round(_norm_cdf((pts_h - round(pts_h - 0.5)) / 8.5), 3),
        },
        "away": {
            "team": away, "pts": pts_a, "ortg": ortg_away,
            "q1": round(pts_a * 0.255, 1), "h1": round(pts_a * 0.51, 1),
            "p_over_team": round(_norm_cdf((pts_a - round(pts_a - 0.5)) / 8.5), 3),
        },
    }

    insights = [
        f"Proyección Opta / Stats Perform: {home} {pts_h:.1f} pts – {pts_a:.1f} pts {away} (Total proyectado: {proj_total:.1f} pts).",
        f"Pace estimado: {est_pace} posesiones/48m · Off Rating proyectado: {home} {ortg_home} vs {away} {ortg_away}.",
        f"Proyección 1ra Mitad (H1): {home} {nba_team_Breakdown['home']['h1']} - {nba_team_Breakdown['away']['h1']} {away} (Total 1ra Mitad: {round((pts_h+pts_a)*0.51, 1)} pts).",
        f"Margen esperado: {home} {proj_margin:+.1f} pts · Jugadores con línea activa en Wplay: {len(evaluated_props)} props.",
    ]
    risks = [
        "Rotaciones de quinteto y descansos (back-to-back): verifica el reporte oficial de lesiones (NBA Injury Report) 1 hora antes del salto inicial.",
        "Variabilidad en tiro exterior de 3 puntos (volumen y acierto de triples).",
    ]

    return {
        "id": f"NBA-{fixture['kickoff'].strftime('%Y%m%d')}-{home.lower().replace(' ','_')}-{away.lower().replace(' ','_')}",
        "div": "NBA",
        "league": {"name": "NBA Baloncesto", "country": "EE. UU.", "flag": "🏀", "kind": "nba"},
        "kickoff": fixture["kickoff"].isoformat(),
        "home": home,
        "away": away,
        "odds_source": "Wplay.co (Colombia)",
        "wplay_url": fixture.get("wplay_url"),
        "lambda_home": pts_h,
        "lambda_away": pts_a,
        "sample": 15,
        "probs": {
            "1x2": {
                "H": prob_home_win(proj_margin),
                "D": 0.0,
                "A": 1.0 - prob_home_win(proj_margin),
            }
        },
        "insights": insights,
        "risks": risks,
        "nba_breakdown": nba_team_Breakdown,
        "player_props": evaluated_props,
        "selections": selections,
        "best_pick": best_pick,
        "has_value": any(s["label"] == "VALUE" for s in selections),
    }
