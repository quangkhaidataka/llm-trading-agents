"""S41 tests — walk-forward backtester + dollar accounting.

The dollar primitives + the t+1 / fee / sizing invariants are tested directly with
injected targets (offline the graph returns hold-flat, so it never trades). One full
offline run over the fixture 2025 window proves the loop + artifacts end-to-end.
All offline + deterministic (Config(offline=True), MockLLM, fixtures; no network).
"""

from __future__ import annotations

from datetime import date

import pytest

import src.data.loaders as loaders
from config import Config
from src.backtest.run_backtest import Backtester, run_backtest


def _bt(**kw) -> Backtester:
    return Backtester(Config(offline=True, **kw))


# ── capped-notional sizing (set once at entry) ───────────────────────────────
def test_capped_notional_caps_above_water_all_in_underwater() -> None:
    bt = _bt()  # C0 = 1_000_000
    assert bt._entry_notional(1_200_000) == 1_000_000   # above water → deploy $1M, rest cash
    assert bt._entry_notional(700_000) == 700_000       # underwater → all-in


def test_shares_for_signs_and_sizes() -> None:
    bt = _bt()
    assert bt._shares_for(1, 1_000_000, 100.0) == pytest.approx(10_000)
    assert bt._shares_for(-1, 1_000_000, 100.0) == pytest.approx(-10_000)
    assert bt._shares_for(0, 1_000_000, 100.0) == 0


# ── fee on change; a flip turns over double the notional → double fee ─────────
def test_flip_costs_double_an_open() -> None:
    bt = _bt()
    open_fee = bt._fee(0.0, 100.0, 50.0)        # 0 -> +100 shares
    flip_fee = bt._fee(100.0, -100.0, 50.0)     # +100 -> -100 shares (crosses zero)
    assert flip_fee == pytest.approx(2 * open_fee)


# ── t+1 execution: a day-t decision earns only from t+1 onward (no lookahead) ──
def test_execution_is_t_plus_one() -> None:
    bt = _bt()
    dates = [date(2025, 1, d) for d in (2, 3, 6, 7)]
    prices = [100.0, 110.0, 121.0, 133.1]   # strictly rising
    targets = [1, 1, 1, 1]                   # decide "long" every day

    recs = bt._run_accounting(dates, prices, targets)

    # day 0: nothing decided before today → flat, no P&L
    assert recs[0].shares == 0 and recs[0].pnl == 0.0
    # day 1: the day-0 long is EXECUTED here (t+1); it did NOT capture the day0->day1 move
    assert recs[1].action == "open" and recs[1].shares > 0
    assert recs[1].pnl == 0.0   # off-by-one guard: same-day execution would make this > 0
    # day 2: now the long earns the day1->day2 return
    assert recs[2].pnl > 0


# ── turnover ties out with the fee-on-change count ───────────────────────────
def test_fee_charged_only_on_change_and_turnover_ties_out() -> None:
    bt = _bt()
    dates = [date(2025, 1, d) for d in (2, 3, 6, 7, 8)]
    prices = [100.0] * 5                      # flat → isolate fees from P&L
    targets = [1, 1, -1, 0, 0]               # open, (hold), flip, close, (flat)

    recs = bt._run_accounting(dates, prices, targets)
    actions = [r.action for r in recs]
    fee_days = [i for i, r in enumerate(recs) if r.fee > 0]

    # executions land one day after the decision: open@1, hold@2, flip@3, close@4
    assert actions == ["hold", "open", "hold", "flip", "close"]
    assert fee_days == [1, 3, 4]                       # exactly the position changes
    assert len(fee_days) == sum(1 for a in actions if a in ("open", "flip", "close"))
    assert recs[3].fee > recs[1].fee                   # flip turns over more than an open


# ── full offline run end-to-end → artifacts written ──────────────────────────
def test_backtest_runs_offline_and_writes_artifacts(tmp_path, monkeypatch) -> None:
    cfg = Config(
        offline=True, test_start="2025-01-02", test_end="2025-12-31",
        log_dir=str(tmp_path / "logs"), results_dir=str(tmp_path / "results"),
    )
    monkeypatch.setattr(loaders, "config", cfg)

    result = run_backtest(cfg)

    assert result["metrics"]["sessions"] > 0
    assert result["metrics"]["initial_capital"] == 1_000_000.0
    assert "max_drawdown_over_c0" in result["metrics"]  # S42 risk metrics present
    for name in ("equity_curve.csv", "trace.json", "metrics.json", "decisions_log.csv",
                 "equity_curve.png"):
        assert (tmp_path / "results" / name).exists(), name
