"""Modelo de goles: Poisson bivariado independiente con corrección Dixon-Coles."""
from __future__ import annotations

import math

DEFAULT_RHO = -0.08   # valor típico estimado en ligas top (más empates 0-0 / 1-1)
MAX_GOALS = 10


def _pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def prob_poisson_over(lam: float, line: float) -> float:
    """Probabilidad Poisson de superar `line` (ej. 8.5 tiros a puerta o 9.5 córners)."""
    if lam <= 0:
        return 0.0
    k_max = int(math.floor(line))
    cdf = 0.0
    term = math.exp(-lam)
    for k in range(0, k_max + 1):
        if k > 0:
            term *= lam / k
        cdf += term
    return max(0.0, min(1.0, 1.0 - cdf))


def score_matrix(lh: float, la: float, rho: float = DEFAULT_RHO,
                 max_goals: int = MAX_GOALS) -> list[list[float]]:
    """Matriz P(goles_local = i, goles_visitante = j) normalizada a 1."""
    ph = [_pmf(lh, i) for i in range(max_goals + 1)]
    pa = [_pmf(la, j) for j in range(max_goals + 1)]
    m = [[ph[i] * pa[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    # Corrección Dixon-Coles para marcadores bajos
    m[0][0] *= max(1 - lh * la * rho, 0)
    m[0][1] *= max(1 + lh * rho, 0)
    m[1][0] *= max(1 + la * rho, 0)
    m[1][1] *= max(1 - rho, 0)
    total = sum(map(sum, m))
    return [[v / total for v in row] for row in m]


def goal_diff_distribution(m: list[list[float]]) -> dict[int, float]:
    dist: dict[int, float] = {}
    for i, row in enumerate(m):
        for j, p in enumerate(row):
            dist[i - j] = dist.get(i - j, 0.0) + p
    return dist


def market_probs(m: list[list[float]]) -> dict:
    """Probabilidades de los mercados principales a partir de la matriz."""
    h = d = a = over = btts = 0.0
    for i, row in enumerate(m):
        for j, p in enumerate(row):
            if i > j:
                h += p
            elif i == j:
                d += p
            else:
                a += p
            if i + j > 2.5:
                over += p
            if i > 0 and j > 0:
                btts += p
    scores = sorted(((p, i, j) for i, row in enumerate(m) for j, p in enumerate(row)),
                    reverse=True)[:6]
    return {
        "1x2": {"H": h, "D": d, "A": a},
        "ou25": {"O": over, "U": 1 - over},
        "btts": {"Y": btts, "N": 1 - btts},
        "top_scores": [{"score": f"{i}-{j}", "p": p} for p, i, j in scores],
    }


def _split_line(line: float) -> list[float]:
    """Las líneas de cuarto (±0.25, ±0.75...) se dividen en dos medias apuestas."""
    if abs(line * 4) % 2 == 1:
        return [line - 0.25, line + 0.25]
    return [line]


def ah_outcomes(diff: dict[int, float], line: float, side: str) -> dict:
    """Distribución de resultados de un hándicap asiático.

    ``line`` es el hándicap del LOCAL (formato football-data / The Odds API).
    ``side`` = 'H' (apostar al local con ``line``) o 'A' (visitante con ``-line``).
    Devuelve probabilidades de ganar / medio ganar / push / medio perder / perder.
    """
    out = {"win": 0.0, "half_win": 0.0, "push": 0.0, "half_loss": 0.0, "loss": 0.0}
    parts = _split_line(line)
    for d, p in diff.items():
        results = []
        for ln in parts:
            r = (d + ln) if side == "H" else (-d - ln)
            results.append(1 if r > 1e-9 else (-1 if r < -1e-9 else 0))
        if len(results) == 1:
            key = {1: "win", 0: "push", -1: "loss"}[results[0]]
        else:
            s = sum(results)
            key = {2: "win", 1: "half_win", 0: "push", -1: "half_loss", -2: "loss"}[s]
        out[key] += p
    return out


def ah_ev(o: dict, odds: float) -> float:
    """Valor esperado por unidad apostada en un hándicap asiático."""
    b = odds - 1
    return o["win"] * b + o["half_win"] * b / 2 - o["half_loss"] / 2 - o["loss"]


def ah_fair_odds(o: dict) -> float | None:
    """Cuota a la que el EV del hándicap es exactamente 0."""
    num = o["loss"] + o["half_loss"] / 2
    den = o["win"] + o["half_win"] / 2
    if den <= 0:
        return None
    return 1 + num / den
