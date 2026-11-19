"""Eliminación del margen (vig), valor esperado y gestión de stake (Kelly fraccional)."""
from __future__ import annotations

import math


def implied(odds: float | None) -> float | None:
    return 1 / odds if odds and odds > 1 else None


def overround(odds: list[float]) -> float:
    return sum(1 / o for o in odds) - 1


def devig_proportional(odds: list[float]) -> list[float]:
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def devig_power(odds: list[float]) -> list[float]:
    """Método de potencia: p_i = (1/o_i)^k con k tal que Σ p_i = 1."""
    inv = [1 / o for o in odds]
    lo, hi = 0.5, 3.0
    for _ in range(80):
        k = (lo + hi) / 2
        if sum(x ** k for x in inv) > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    p = [x ** k for x in inv]
    s = sum(p)
    return [x / s for x in p]


def devig_shin(odds: list[float]) -> list[float]:
    """Método de Shin (corrige el sesgo favorito-sorpresa en mercados de 3 vías)."""
    inv = [1 / o for o in odds]
    b = sum(inv)
    if b <= 1:
        return devig_proportional(odds)

    def probs(z: float) -> list[float]:
        return [(math.sqrt(z * z + 4 * (1 - z) * x * x / b) - z) / (2 * (1 - z)) for x in inv]

    lo, hi = 0.0, 0.5
    for _ in range(100):
        z = (lo + hi) / 2
        if sum(probs(z)) > 1:
            lo = z
        else:
            hi = z
    p = probs((lo + hi) / 2)
    s = sum(p)
    return [x / s for x in p]


def devig(odds: list[float]) -> list[float]:
    if len(odds) >= 3:
        return devig_shin(odds)
    return devig_power(odds)


def expected_value(p: float, odds: float) -> float:
    return p * odds - 1


def kelly_full(ev: float, odds: float) -> float:
    """Kelly completo para apuesta binaria: f* = (b·p − q)/b = EV / b."""
    if ev <= 0 or odds <= 1:
        return 0.0
    return ev / (odds - 1)


def confidence_factor(n_matches: int) -> float:
    """Ponderación por estabilidad de la muestra (partidos de la temporada actual)."""
    if n_matches < 6:
        return 0.5
    if n_matches <= 15:
        return 0.75
    return 1.0


def confidence_label(n_matches: int, ev: float) -> str:
    cf = confidence_factor(n_matches)
    if cf == 1.0 and ev >= 0.06:
        return "Alta"
    if cf >= 0.75 and ev >= 0.03:
        return "Media"
    return "Baja"


def stake(ev: float, odds: float, n_matches: int, settings: dict) -> dict:
    full = kelly_full(ev, odds)
    cf = confidence_factor(n_matches)
    pct = min(full * settings["kelly_fraction"] * cf, settings["max_stake_pct"])
    amount = pct * settings["bankroll"]
    return {
        "kelly_full": full,
        "confidence_factor": cf,
        "stake_pct": pct,
        "stake_amount": amount,
        "below_min_bet": 0 < amount < settings.get("min_bet", 0),
    }


def label(ev: float | None, min_ev: float) -> str:
    if ev is None:
        return "SIN CUOTA"
    if ev >= min_ev:
        return "VALUE"
    if ev > 0:
        return "MARGINAL"
    return "NO BET"
