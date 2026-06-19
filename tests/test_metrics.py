"""S42 tests — dollar-accounting metrics + equity chart.

Hand-calculated toy series; every metric on the FIXED base C0, net of fees. The headline
check is MaxDD = min((E[t]-peak$[t])/C0) — divided by INITIAL CAPITAL (reads deeper than
the conventional /peak). Sharpe/Sortino cross-checked against the stdlib `statistics`.
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
import pytest

from src.backtest.metrics import (
    avg_holding_period,
    buy_and_hold,
    compute_metrics,
    daily_returns,
    hit_rate,
    max_drawdown,
    plot_equity,
    sharpe,
    sortino,
    total_return,
    turnover,
)

C0 = 1000.0


def test_daily_returns_are_fixed_base() -> None:
    eq = pd.Series([1000.0, 1010.0, 1005.0, 1020.0])
    r = daily_returns(eq, C0)
    assert list(r) == pytest.approx([0.010, -0.005, 0.015])  # ΔE / C0, not /moving equity


def test_total_return_on_c0() -> None:
    eq = pd.Series([1000.0, 1010.0, 1040.0])
    assert total_return(eq, C0) == pytest.approx(0.04)


def test_max_drawdown_divided_by_initial_capital() -> None:
    eq = pd.Series([1000.0, 1100.0, 900.0, 950.0])
    # peak$ = [1000,1100,1100,1100]; dd = [0, 0, -0.20, -0.15]; min = -0.20.
    assert max_drawdown(eq, C0) == pytest.approx(-0.20)
    # /peak would read only (900-1100)/1100 = -0.1818 — our /C0 convention reads deeper.
    assert max_drawdown(eq, C0) < (900.0 - 1100.0) / 1100.0


def test_sharpe_matches_handcalc() -> None:
    r = pd.Series([0.01, 0.03])
    expected = statistics.mean(r) / statistics.stdev(r) * math.sqrt(252)
    assert sharpe(r) == pytest.approx(expected)


def test_sharpe_zero_variance_guard() -> None:
    assert sharpe(pd.Series([0.01, 0.01, 0.01])) == 0.0


def test_sortino_uses_downside_only() -> None:
    r = pd.Series([0.01, -0.02, 0.03, -0.01])
    downside = [-0.02, -0.01]
    expected = statistics.mean(r) / statistics.stdev(downside) * math.sqrt(252)
    assert sortino(r) == pytest.approx(expected)


def test_hit_rate() -> None:
    assert hit_rate(pd.Series([0.01, -0.02, 0.03, -0.01])) == pytest.approx(0.5)


def test_turnover_counts_changes_with_flip_double() -> None:
    # prepend flat 0 → open(0→1), hold, flip(1→-1, |Δ|=2), close(-1→0): |Δ| = [0,1,0,2,1], mean 0.8
    assert turnover(pd.Series([0, 1, 1, -1, 0])) == pytest.approx(0.8)


def test_avg_holding_period_run_length() -> None:
    # runs of one-sided exposure: [+1,+1]=2, [-1]=1, [+1]=1 → mean 4/3
    assert avg_holding_period(pd.Series([0, 1, 1, -1, 0, 1])) == pytest.approx(4 / 3)


def test_buy_and_hold_from_price() -> None:
    bh = buy_and_hold(pd.Series([100.0, 110.0, 120.0]), C0)
    assert list(bh) == pytest.approx([1000.0, 1100.0, 1200.0])


def test_compute_metrics_bundle_has_keys() -> None:
    eq = pd.Series([1000.0, 1010.0, 1005.0, 1020.0])
    pos = pd.Series([0, 1, 1, 1])
    price = pd.Series([100.0, 101.0, 100.5, 102.0])
    m = compute_metrics(eq, pos, price, C0)
    for key in ("total_return", "sharpe", "sortino", "max_drawdown_over_c0",
                "hit_rate", "turnover", "avg_holding_period", "buy_hold"):
        assert key in m
    assert set(m["buy_hold"]) == {"total_return", "sharpe", "max_drawdown_over_c0"}


def test_plot_equity_writes_png(tmp_path) -> None:
    eq = pd.Series([1000.0, 1010.0, 1020.0])
    bh = pd.Series([1000.0, 1005.0, 1015.0])
    out = str(tmp_path / "equity_curve.png")
    plot_equity(eq, bh, {"total_return": 0.02, "sharpe": 1.0, "max_drawdown_over_c0": -0.01,
                         "buy_hold": {"total_return": 0.015, "sharpe": 0.8,
                                      "max_drawdown_over_c0": -0.02}}, out)
    assert (tmp_path / "equity_curve.png").stat().st_size > 0
