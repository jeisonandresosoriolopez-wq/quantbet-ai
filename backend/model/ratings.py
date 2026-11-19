"""Ratings ofensivos/defensivos por equipo a partir de xG (o proxy de tiros).

Modelo multiplicativo:  λ_local = μ_local · ATT_local · DEF_visitante
                        λ_visit = μ_visit · ATT_visit · DEF_local

Se estima con ajuste proporcional iterativo, ponderando cada partido por recencia
(semivida configurable) y aplicando *shrinkage* hacia la media de la liga mediante
pseudo-partidos, de modo que equipos con poca muestra no tengan ratings extremos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

HALF_LIFE_DAYS = 90
PREV_SEASON_WEIGHT = 0.5
SHRINK_MATCHES = 1.5
XG_WEIGHT = 0.7  # señal = 0.7·xG + 0.3·goles (los goles aportan algo de info de finalización)


@dataclass
class Ratings:
    mu_home: float
    mu_away: float
    att: dict[str, float]
    defn: dict[str, float]
    teams: list[str]
    uses_xg: bool
    n_matches: dict[str, int] = field(default_factory=dict)

    def lambdas(self, home: str, away: str) -> tuple[float, float]:
        lh = self.mu_home * self.att.get(home, 1.0) * self.defn.get(away, 1.0)
        la = self.mu_away * self.att.get(away, 1.0) * self.defn.get(home, 1.0)
        return max(lh, 0.05), max(la, 0.05)


def _shot_proxy(shots: int | None, sot: int | None) -> float | None:
    if shots is None or sot is None:
        return None
    return 0.22 * sot + 0.045 * max(shots - sot, 0)


def signals(m: dict) -> tuple[float, float, bool]:
    """Señal de 'goles esperados' de cada lado para un partido."""
    gh, ga = m["fthg"], m["ftag"]
    if m.get("hxg") is not None and m.get("axg") is not None:
        return (XG_WEIGHT * m["hxg"] + (1 - XG_WEIGHT) * gh,
                XG_WEIGHT * m["axg"] + (1 - XG_WEIGHT) * ga, True)
    ph, pa = _shot_proxy(m.get("hs"), m.get("hst")), _shot_proxy(m.get("as"), m.get("ast"))
    if ph is not None and pa is not None:
        return 0.6 * ph + 0.4 * gh, 0.6 * pa + 0.4 * ga, False
    return float(gh), float(ga), False


def fit(current: list[dict], previous: list[dict], as_of: datetime,
        iterations: int = 40) -> Ratings | None:
    """Ajusta los ratings usando sólo partidos anteriores a ``as_of``."""
    rows = []
    teams_now: set[str] = set()
    n_matches: dict[str, int] = {}
    any_xg = False
    for season_rows, season_w in ((current, 1.0), (previous, PREV_SEASON_WEIGHT)):
        for m in season_rows:
            if m["kickoff"] >= as_of:
                continue
            days = (as_of - m["kickoff"]).total_seconds() / 86400
            w = season_w * math.exp(-math.log(2) * days / HALF_LIFE_DAYS)
            sh, sa, xg = signals(m)
            any_xg |= xg and season_w == 1.0
            rows.append((m["home"], m["away"], sh, sa, w))
            if season_w == 1.0:
                teams_now.update((m["home"], m["away"]))
                n_matches[m["home"]] = n_matches.get(m["home"], 0) + 1
                n_matches[m["away"]] = n_matches.get(m["away"], 0) + 1
    if len(rows) < 20:
        return None

    tw = sum(r[4] for r in rows)
    mu_h = sum(r[2] * r[4] for r in rows) / tw
    mu_a = sum(r[3] * r[4] for r in rows) / tw
    mu = (mu_h + mu_a) / 2
    teams = sorted({t for r in rows for t in r[:2]})
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}

    for _ in range(iterations):
        s_for = {t: SHRINK_MATCHES * mu for t in teams}
        e_for = {t: SHRINK_MATCHES * mu for t in teams}
        s_ag = {t: SHRINK_MATCHES * mu for t in teams}
        e_ag = {t: SHRINK_MATCHES * mu for t in teams}
        for h, a, sh, sa, w in rows:
            s_for[h] += w * sh
            e_for[h] += w * mu_h * dfn[a]
            s_for[a] += w * sa
            e_for[a] += w * mu_a * dfn[h]
            s_ag[h] += w * sa
            e_ag[h] += w * mu_a * att[a]
            s_ag[a] += w * sh
            e_ag[a] += w * mu_h * att[h]
        att = {t: s_for[t] / e_for[t] for t in teams}
        dfn = {t: s_ag[t] / e_ag[t] for t in teams}
        # Normaliza para que el equipo medio tenga rating 1
        ma = sum(att.values()) / len(att)
        md = sum(dfn.values()) / len(dfn)
        att = {t: v / ma for t, v in att.items()}
        dfn = {t: v / md for t, v in dfn.items()}

    return Ratings(mu_h, mu_a, att, dfn, sorted(teams_now or teams), any_xg, n_matches)


# --------------------------------------------------------------------------- #
# Estadísticas descriptivas por equipo (para el panel de métricas)
# --------------------------------------------------------------------------- #
def team_profile(team: str, matches: list[dict], as_of: datetime) -> dict:
    played = sorted((m for m in matches if m["kickoff"] < as_of and team in (m["home"], m["away"])),
                    key=lambda m: m["kickoff"])
    n = len(played)
    if n == 0:
        return {"team": team, "played": 0}
    acc = {"xg_for": 0.0, "xg_ag": 0.0, "g_for": 0, "g_ag": 0, "sh_for": 0, "sh_ag": 0,
           "sot_for": 0, "sot_ag": 0, "cor_for": 0, "cor_ag": 0, "fls_for": 0, "fls_ag": 0,
           "yel_for": 0, "yel_ag": 0}
    xg_n = 0
    cor_n = 0
    fls_n = 0
    form = []
    for m in played:
        home = m["home"] == team
        gf, ga = (m["fthg"], m["ftag"]) if home else (m["ftag"], m["fthg"])
        acc["g_for"] += gf
        acc["g_ag"] += ga
        if m.get("hxg") is not None:
            xf, xa = (m["hxg"], m["axg"]) if home else (m["axg"], m["hxg"])
            acc["xg_for"] += xf
            acc["xg_ag"] += xa
            xg_n += 1
        if m.get("hs") is not None:
            acc["sh_for"] += m["hs"] if home else m["as"]
            acc["sh_ag"] += m["as"] if home else m["hs"]
            acc["sot_for"] += m["hst"] if home else m["ast"]
            acc["sot_ag"] += m["ast"] if home else m["hst"]
        if m.get("hc") is not None and m.get("ac") is not None:
            acc["cor_for"] += m["hc"] if home else m["ac"]
            acc["cor_ag"] += m["ac"] if home else m["hc"]
            cor_n += 1
        if m.get("hf") is not None and m.get("af") is not None:
            acc["fls_for"] += m["hf"] if home else m["af"]
            acc["fls_ag"] += m["af"] if home else m["hf"]
            acc["yel_for"] += (m.get("hy") or 0) if home else (m.get("ay") or 0)
            acc["yel_ag"] += (m.get("ay") or 0) if home else (m.get("hy") or 0)
            fls_n += 1
        form.append("W" if gf > ga else "D" if gf == ga else "L")
    last5 = played[-5:]
    l5_xgd = None
    if all(m.get("hxg") is not None for m in last5):
        l5_xgd = sum((m["hxg"] - m["axg"]) if m["home"] == team else (m["axg"] - m["hxg"])
                     for m in last5) / len(last5)
    prof = {
        "team": team, "played": n,
        "goals_for": round(acc["g_for"] / n, 2), "goals_against": round(acc["g_ag"] / n, 2),
        "shots_for": round(acc["sh_for"] / n, 1), "shots_against": round(acc["sh_ag"] / n, 1),
        "sot_for": round(acc["sot_for"] / n, 1), "sot_against": round(acc["sot_ag"] / n, 1),
        "corners_for": round(acc["cor_for"] / cor_n, 2) if cor_n else 5.1,
        "corners_against": round(acc["cor_ag"] / cor_n, 2) if cor_n else 4.9,
        "fouls_for": round(acc["fls_for"] / fls_n, 1) if fls_n else 11.4,
        "fouls_against": round(acc["fls_ag"] / fls_n, 1) if fls_n else 11.4,
        "cards_for": round(acc["yel_for"] / fls_n, 2) if fls_n else 1.9,
        "cards_against": round(acc["yel_ag"] / fls_n, 2) if fls_n else 1.9,
        "form": form[-5:],
        "last_match": played[-1]["kickoff"].isoformat(),
    }
    if xg_n:
        prof.update({
            "xg_for": round(acc["xg_for"] / xg_n, 2),
            "xg_against": round(acc["xg_ag"] / xg_n, 2),
            "xg_diff": round((acc["xg_for"] - acc["xg_ag"]) / xg_n, 2),
            "finishing_delta": round((acc["g_for"] - acc["xg_for"]) / xg_n, 2),
            "defending_delta": round((acc["g_ag"] - acc["xg_ag"]) / xg_n, 2),
            "last5_xg_diff": round(l5_xgd, 2) if l5_xgd is not None else None,
        })
    return prof
