"""Tests unitarios del motor cuantitativo Opta QuantBet AI."""
from __future__ import annotations

import math
from backend.model import poisson, value


def test_poisson_matrix_normalized():
    m = poisson.score_matrix(1.65, 1.15)
    total = sum(sum(r) for r in m)
    assert math.isclose(total, 1.0, rel_tol=1e-9)

    probs = poisson.market_probs(m)
    assert math.isclose(sum(probs["1x2"].values()), 1.0, rel_tol=1e-9)
    assert math.isclose(sum(probs["ou25"].values()), 1.0, rel_tol=1e-9)
    assert math.isclose(sum(probs["btts"].values()), 1.0, rel_tol=1e-9)


def test_devig_methods_sum_to_one():
    odds_3way = [1.95, 3.50, 4.00]
    for fn in (value.devig_proportional, value.devig_power, value.devig_shin, value.devig):
        p = fn(odds_3way)
        assert len(p) == 3
        assert math.isclose(sum(p), 1.0, rel_tol=1e-6)
        assert all(0 < x < 1 for x in p)

    odds_2way = [1.90, 1.95]
    p2 = value.devig(odds_2way)
    assert math.isclose(sum(p2), 1.0, rel_tol=1e-6)


def test_ev_and_kelly_cap():
    ev = value.expected_value(0.562, 2.10)
    assert math.isclose(ev, 0.562 * 2.10 - 1.0, rel_tol=1e-9)
    assert ev > 0

    settings = {"bankroll": 20000.0, "kelly_fraction": 0.25, "max_stake_pct": 0.02, "min_bet": 1000.0}
    st = value.stake(ev, 2.10, n_matches=20, settings=settings)
    assert 0 < st["stake_pct"] <= 0.02
    assert st["stake_amount"] <= 400.0  # 2% de $20.000 COP

    # Con muestra pequeña (<6 partidos) se reduce por factor 0.5
    st_small = value.stake(0.05, 2.00, n_matches=4, settings=settings)
    st_full = value.stake(0.05, 2.00, n_matches=18, settings=settings)
    assert math.isclose(st_small["stake_pct"], st_full["stake_pct"] * 0.5, rel_tol=1e-6)


def test_asian_handicap_outcomes():
    m = poisson.score_matrix(1.5, 1.2)
    diff = poisson.goal_diff_distribution(m)
    for line in (-0.5, -0.25, 0.0, 0.25, 0.75):
        out = poisson.ah_outcomes(diff, line, "H")
        assert math.isclose(sum(out.values()), 1.0, rel_tol=1e-6)
