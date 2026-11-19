"""Pipeline de análisis de un partido: modelo -> mercado -> EV -> stake -> riesgos."""
from __future__ import annotations

from datetime import datetime

from . import poisson, value
from .ratings import Ratings

SEL_NAMES = {
    "1x2": {"H": "Local", "D": "Empate", "A": "Visitante"},
    "ou25": {"O": "Más de 2.5 goles", "U": "Menos de 2.5 goles"},
    "btts": {"Y": "Ambos marcan: Sí", "N": "Ambos marcan: No"},
}
MARKET_NAMES = {"1x2": "Ganador (1X2)", "ou25": "Over/Under 2.5", "btts": "Ambos marcan",
                "ah": "Hándicap asiático"}


def _fmt_line(x: float) -> str:
    return f"{x:+g}" if x else "0"


def _price(block: dict, sel: str, basis: str) -> tuple[float | None, str | None]:
    """Cuota usada para el EV: media del mercado (realista) o mejor cuota."""
    if not block:
        return None, None
    if basis == "best" and block.get("best", {}).get(sel):
        return block["best"][sel], block["best"].get(f"{sel}_book", "Mejor cuota")
    if block.get("avg", {}).get(sel):
        return block["avg"][sel], "Promedio del mercado"
    if block.get("best", {}).get(sel):
        return block["best"][sel], block["best"].get(f"{sel}_book", "Mejor cuota")
    return None, None


def _market_fair(block: dict, sels: list[str]) -> dict[str, float] | None:
    src = block.get("avg") or {}
    odds = [src.get(s) for s in sels]
    if not all(odds):
        src = block.get("best") or {}
        odds = [src.get(s) for s in sels]
    if not all(odds):
        return None
    return dict(zip(sels, value.devig(odds)))


def _selection(market: str, sel: str, name: str, p_model: float, p_fair: float | None,
               odds: float | None, book: str | None, best: float | None, n: int,
               settings: dict, extra: dict | None = None) -> dict:
    w = settings["model_weight"]
    p_real = p_model if p_fair is None else w * p_model + (1 - w) * p_fair
    ev = value.expected_value(p_real, odds) if odds else None
    st = value.stake(ev, odds, n, settings) if ev and ev > 0 else value.stake(0, 2, n, settings)
    out = {
        "key": f"{market}:{sel}", "market": market, "market_name": MARKET_NAMES[market],
        "selection": sel, "name": name,
        "odds": odds, "odds_source": book, "best_odds": best,
        "p_implied_raw": value.implied(odds),
        "p_market": p_fair, "p_model": p_model, "p_real": p_real,
        "fair_odds": 1 / p_real if p_real > 0 else None,
        "ev": ev, "edge": (p_real - p_fair) if p_fair is not None else None,
        "label": value.label(ev, settings["min_ev"]),
        "confidence": value.confidence_label(n, ev or 0),
        **st,
    }
    if extra:
        out.update(extra)
    return out


def opta_props(home: str, away: str, ph: dict, pa: dict, lh: float, la: float) -> dict:
    """Proyecciones Poisson Opta para Córners, Tiros al Arco (SOT), Faltas y Tarjetas."""
    # Córners esperados ajustados por caudal ofensivo (lh / la)
    ch_for = ph.get("corners_for") or (3.6 + 1.15 * lh)
    ca_ag = pa.get("corners_against") or (3.4 + 1.05 * lh)
    ca_for = pa.get("corners_for") or (3.2 + 1.10 * la)
    ch_ag = ph.get("corners_against") or (3.3 + 1.05 * la)
    cor_h = round(0.55 * ch_for + 0.45 * ca_ag, 2)
    cor_a = round(0.55 * ca_for + 0.45 * ch_ag, 2)
    cor_tot = round(cor_h + cor_a, 2)

    # Tiros al Arco (Shots on Target - SOT)
    sh_for = ph.get("sot_for") or (2.4 + 1.55 * lh)
    sa_ag = pa.get("sot_against") or (2.3 + 1.45 * lh)
    sa_for = pa.get("sot_for") or (2.1 + 1.50 * la)
    sh_ag = ph.get("sot_against") or (2.2 + 1.45 * la)
    sot_h = round(0.55 * sh_for + 0.45 * sa_ag, 2)
    sot_a = round(0.55 * sa_for + 0.45 * sh_ag, 2)
    sot_tot = round(sot_h + sot_a, 2)

    # Faltas e Intensidad Defensiva (PPDA / High Turnovers proxy)
    fh = ph.get("fouls_for") or 11.4
    fa = pa.get("fouls_for") or 11.8
    fls_h = round(fh, 1)
    fls_a = round(fa, 1)
    fls_tot = round(fls_h + fls_a, 1)

    # Tarjetas Amarillas
    yh = ph.get("cards_for") or 1.95
    ya = pa.get("cards_for") or 2.10
    cards_tot = round(yh + ya, 2)

    return {
        "corners": {
            "home": cor_h, "away": cor_a, "total": cor_tot,
            "p_over_85": poisson.prob_poisson_over(cor_tot, 8.5),
            "p_over_95": poisson.prob_poisson_over(cor_tot, 9.5),
            "p_over_105": poisson.prob_poisson_over(cor_tot, 10.5),
        },
        "sot": {
            "home": sot_h, "away": sot_a, "total": sot_tot,
            "p_over_75": poisson.prob_poisson_over(sot_tot, 7.5),
            "p_over_85": poisson.prob_poisson_over(sot_tot, 8.5),
            "p_over_95": poisson.prob_poisson_over(sot_tot, 9.5),
            "p_home_over_45": poisson.prob_poisson_over(sot_h, 4.5),
            "p_away_over_35": poisson.prob_poisson_over(sot_a, 3.5),
        },
        "fouls": {
            "home": fls_h, "away": fls_a, "total": fls_tot,
            "p_over_215": poisson.prob_poisson_over(fls_tot, 21.5),
            "p_over_235": poisson.prob_poisson_over(fls_tot, 23.5),
            "p_over_255": poisson.prob_poisson_over(fls_tot, 25.5),
        },
        "cards": {
            "home": round(yh, 2), "away": round(ya, 2), "total": cards_tot,
            "p_over_35": poisson.prob_poisson_over(cards_tot, 3.5),
            "p_over_45": poisson.prob_poisson_over(cards_tot, 4.5),
        },
    }


def analyze(fixture: dict, ratings: Ratings, profiles: dict[str, dict], settings: dict,
            odds_age_hours: float | None = None,
            override_lambdas: tuple[float, float] | None = None) -> dict:
    home, away = fixture["home"], fixture["away"]
    lh, la = override_lambdas if override_lambdas else ratings.lambdas(home, away)
    matrix = poisson.score_matrix(lh, la)
    probs = poisson.market_probs(matrix)
    diff = poisson.goal_diff_distribution(matrix)
    odds = fixture.get("odds") or {}
    basis = settings.get("price_basis", "avg")
    n = min(ratings.n_matches.get(home, 0), ratings.n_matches.get(away, 0))

    selections = []
    # 1X2, Over/Under 2.5
    for mk, sels in (("1x2", ["H", "D", "A"]), ("ou25", ["O", "U"])):
        block = odds.get(mk) or {}
        fair = _market_fair(block, sels) if block else None
        for s in sels:
            o, book = _price(block, s, basis)
            name = SEL_NAMES[mk][s]
            if mk == "1x2" and s != "D":
                name = f"{name} ({home if s == 'H' else away})"
            selections.append(_selection(mk, s, name, probs[mk][s], fair[s] if fair else None,
                                         o, book, (block.get("best") or {}).get(s), n, settings))
    # Ambos marcan (sin feed de cuotas gratuito: se muestra cuota justa del modelo)
    for s in ("Y", "N"):
        bt = (odds.get("btts") or {})
        fair = _market_fair(bt, ["Y", "N"]) if bt else None
        o, book = _price(bt, s, basis)
        selections.append(_selection("btts", s, SEL_NAMES["btts"][s], probs["btts"][s],
                                     fair[s] if fair else None, o, book, None, n, settings))
    # Hándicap asiático
    ah = odds.get("ah") or {}
    ah_line = ah.get("line")
    if ah_line is not None:
        fair = _market_fair(ah, ["H", "A"])
        for s in ("H", "A"):
            outcomes = poisson.ah_outcomes(diff, ah_line, s)
            fo = poisson.ah_fair_odds(outcomes)
            q_model = 1 / fo if fo else 0.0
            line = ah_line if s == "H" else -ah_line
            team = home if s == "H" else away
            o, book = _price(ah, s, basis)
            sel_obj = _selection(
                "ah", s, f"{team} {_fmt_line(line)}", q_model, fair[s] if fair else None,
                o, book, (ah.get("best") or {}).get(s), n, settings,
                extra={"line": line, "outcomes": outcomes})
            if o and o > 1:
                # EV exacto para hándicap asiático (teniendo en cuenta push / reembolso y medias apuestas)
                w = settings["model_weight"]
                ev_model = poisson.ah_ev(outcomes, o)
                ev_mkt = ((fair[s] * o - 1) if fair and fair.get(s) else ev_model)
                ev_exact = w * ev_model + (1 - w) * ev_mkt
                sel_obj["ev"] = ev_exact
                sel_obj["label"] = value.label(ev_exact, settings["min_ev"])
                sel_obj["confidence"] = value.confidence_label(n, ev_exact)
                st = value.stake(ev_exact, o, n, settings) if ev_exact > 0 else value.stake(0, 2, n, settings)
                sel_obj.update(st)
            selections.append(sel_obj)

    priced = [s for s in selections if s["ev"] is not None]
    best_pick = max(priced, key=lambda s: s["ev"]) if priced else None

    ph, pa = profiles.get(home, {}), profiles.get(away, {})
    return {
        "id": match_id(fixture),
        "div": fixture["div"],
        "kickoff": fixture["kickoff"].isoformat(),
        "home": home, "away": away,
        "odds_source": fixture.get("source", "football-data.co.uk"),
        "wplay_url": fixture.get("wplay_url"),
        "lambda_home": lh, "lambda_away": la,
        "rating": {
            "home_att": ratings.att.get(home, 1.0), "home_def": ratings.defn.get(home, 1.0),
            "away_att": ratings.att.get(away, 1.0), "away_def": ratings.defn.get(away, 1.0),
        },
        "uses_xg": ratings.uses_xg,
        "sample": n,
        "probs": {k: probs[k] for k in ("1x2", "ou25", "btts")},
        "top_scores": probs["top_scores"],
        "matrix": [row[:6] for row in matrix[:6]],
        "profiles": {"home": ph, "away": pa},
        "opta_props": opta_props(home, away, ph, pa, lh, la),
        "insights": insights(ph, pa, lh, la),
        "selections": selections,
        "best_pick": best_pick,
        "has_value": any(s["label"] == "VALUE" for s in selections),
        "risks": risks(fixture, ph, pa, best_pick, n, ratings, odds_age_hours,
                       probs["1x2"]["D"]),
    }


def match_id(f: dict) -> str:
    slug = lambda s: "".join(ch for ch in s.lower().replace(" ", "_") if ch.isalnum() or ch == "_")
    return f"{f['div']}-{f['kickoff'].strftime('%Y%m%d')}-{slug(f['home'])}-{slug(f['away'])}"


# --------------------------------------------------------------------------- #
# Texto ejecutivo: desequilibrios y riesgos
# --------------------------------------------------------------------------- #
def insights(ph: dict, pa: dict, lh: float, la: float) -> list[str]:
    out = []
    h, a = ph.get("team", "Local"), pa.get("team", "Visitante")
    out.append(f"Goles esperados proyectados: {h} {lh:.2f} – {la:.2f} {a} "
               f"(total {lh + la:.2f}).")
    if ph.get("xg_for") is not None and pa.get("xg_for") is not None:
        out.append(f"xG generado por partido: {h} {ph['xg_for']:.2f} vs {a} {pa['xg_for']:.2f} "
                   f"({ph['xg_for'] - pa['xg_for']:+.2f}).")
        out.append(f"xG concedido por partido: {h} {ph['xg_against']:.2f} vs {a} "
                   f"{pa['xg_against']:.2f}.")
        for p in (ph, pa):
            if p.get("last5_xg_diff") is not None and abs(p["last5_xg_diff"] - p["xg_diff"]) >= 0.4:
                trend = "mejora" if p["last5_xg_diff"] > p["xg_diff"] else "caída"
                out.append(f"{p['team']}: {trend} reciente (xG diff últimos 5: "
                           f"{p['last5_xg_diff']:+.2f} vs temporada {p['xg_diff']:+.2f}).")
    if ph.get("sot_for") is not None and pa.get("sot_for") is not None:
        out.append(f"Tiros a puerta por partido: {h} {ph['sot_for']:.1f} vs {a} {pa['sot_for']:.1f}.")
    if ph.get("form") and pa.get("form"):
        out.append(f"Forma reciente (últimos 5): {h} [{''.join(ph['form'])}] vs {a} [{''.join(pa['form'])}].")
    if ph.get("record") or pa.get("record"):
        out.append(f"Balance competitivo: {h} ({ph.get('record') or 's/d'}) vs {a} ({pa.get('record') or 's/d'}).")
    return out


def risks(fixture: dict, ph: dict, pa: dict, pick: dict | None, n: int, ratings: Ratings,
          odds_age_hours: float | None, draw_p: float = 0.0) -> list[str]:
    out = []
    if n < 6:
        out.append(f"Muestra corta ({n} partidos en la temporada): ratings poco estables.")
    if not ratings.uses_xg:
        out.append("Sin xG disponible: el modelo usa un proxy basado en tiros.")
    for p in (ph, pa):
        fd = p.get("finishing_delta")
        if fd is not None and abs(fd) >= 0.3:
            word = "por encima" if fd > 0 else "por debajo"
            out.append(f"{p['team']} marca {word} de su xG ({fd:+.2f}/partido): "
                       "posible regresión a la media.")
        dd = p.get("defending_delta")
        if dd is not None and abs(dd) >= 0.3:
            word = "más" if dd > 0 else "menos"
            out.append(f"{p['team']} recibe {word} goles de lo que indica su xG en contra "
                       f"({dd:+.2f}/partido): rendimiento del portero/varianza.")
    if pick and pick.get("p_market") is not None:
        gap = pick["p_model"] - pick["p_market"]
        if abs(gap) >= 0.10:
            out.append(f"Gran discrepancia modelo vs mercado ({gap * 100:+.1f} pp): el mercado "
                       "podría estar descontando lesiones, rotaciones o noticias que el modelo no ve.")
    if pick and pick["market"] == "1x2" and pick["selection"] != "D" and draw_p >= 0.29:
        out.append(f"Probabilidad de empate elevada ({draw_p * 100:.0f}%): considera la "
                   "alternativa de hándicap asiático 0 / +0.25 para reducir varianza.")
    if odds_age_hours is not None and odds_age_hours > 24:
        out.append(f"Las cuotas tienen {odds_age_hours:.0f} h de antigüedad: verifica la cuota "
                   "actual en tu casa antes de apostar.")
    out.append("No incluye alineaciones, lesiones, clima ni partidos de copas europeas entre "
               "semana: verifica las alineaciones ~1 h antes del partido.")
    return out
