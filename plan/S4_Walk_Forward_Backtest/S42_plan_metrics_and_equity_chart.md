# S4.2 — Metrics & Equity Chart

## Objective

A career needs a scorecard. Once the S4.1 `Backtester` has walked the whole 2025–2026 window and
produced a daily equity series `E[t]`, this sub-step turns that series into the headline numbers a
quant reviewer asks for — total return, Sharpe, Sortino, max drawdown, hit rate, turnover, and average
holding period — and into the one picture everyone actually looks at: the equity curve of the strategy
plotted against simply buying and holding AAPL.

The accounting convention matters as much as the formulas. Every metric is computed on the **fixed
\$1,000,000 base** (`C0`), net of fees, never on a moving equity denominator. Daily return is the
day's dollar change divided by `C0` (`r[t] = ΔE / C0`), so Sharpe and Sortino on `r[t]` are just the
Sharpe of the raw dollar P&L, annualized by `√252`. Max drawdown is deliberately the non-standard
"divide by initial capital" version — `dd[t] = (E[t] − peak$[t]) / C0` — which reads *deeper* than the
usual `/peak` (e.g. −24% where `/peak` would say −20%), and we label it as such so no one is misled.
The chart draws both lines from the same \$1M start, with the buy-and-hold reference computed directly
from the price cache as `\$1M·P[t]/P[0]`, and pins a small stats box on the figure so the return,
Sharpe, and MaxDD of each line are readable straight off the image.

## Inputs and Outputs

**Inputs**
- The strategy equity series `E[t]` (and the per-day `position` series for turnover / holding period)
  produced by the S4.1 `Backtester`, as a pandas `Series` / `DataFrame` indexed by date.
- The aligned price series `P[t]` from the cache, for the buy & hold reference (`C0·P[t]/P[0]`).
- `config`: `initial_capital` (= `C0` = 1_000_000) — the fixed base every metric divides by.

**Outputs**
- `results/metrics.json` — the metric dict: `total_return, sharpe, sortino, max_drawdown, hit_rate,
  turnover, avg_holding_period` (all on the \$1M base, net of fees) plus the same trio for buy & hold.
  JSON, under `results/` (gitignored).
- `results/equity_curve.png` — strategy vs buy & hold, both from \$1M, with an on-chart stats box
  showing total return / Sharpe / MaxDD per line. PNG, under `results/`.
- (Consumes `results/equity_curve.csv` from S4.1; produced there, not here.)

## Skeleton Python Code

```python
"""src/backtest/metrics.py — dollar-accounting metrics + equity chart (M4).

All metrics are on the FIXED base C0 = initial_capital ($1M), net of fees.
"""
from __future__ import annotations

import pandas as pd


def daily_returns(equity: pd.Series, c0: float) -> pd.Series:
    """Fixed-base daily return r[t] = (E[t] - E[t-1]) / C0  (NOT divided by moving equity)."""
    ...


def total_return(equity: pd.Series, c0: float) -> float:
    """total_return = E[T] / C0 - 1  (net of fees)."""
    ...


def sharpe(returns: pd.Series, periods: int = 252) -> float:
    """Sharpe = mean(r) / std(r) · √252  on the fixed-base r[t]
    (since C0 is constant this equals Sharpe on raw $ P&L)."""
    ...


def sortino(returns: pd.Series, periods: int = 252) -> float:
    """Sortino = mean(r) / std(r | r<0) · √252  (downside-only deviation)."""
    ...


def max_drawdown(equity: pd.Series, c0: float) -> float:
    """MDD divided by INITIAL CAPITAL (convention, not /peak):
       peak$[t] = max(E[0..t]); dd[t] = (E[t] - peak$[t]) / C0; MDD = min(dd[t]).
       Reads deeper than the standard /peak; label it as such downstream."""
    ...


def hit_rate(returns: pd.Series) -> float:
    """Share of test days with r[t] > 0."""
    ...


def turnover(position: pd.Series) -> float:
    """turnover = mean |Δ position|  (churn measure; ties out with the fee-on-change count)."""
    ...


def avg_holding_period(position: pd.Series) -> float:
    """Mean run-length of a non-zero position (consecutive days the book stays on one side)."""
    ...


def compute_metrics(equity: pd.Series, position: pd.Series, price: pd.Series, c0: float) -> dict:
    """Bundle every metric on the $1M base, net of fees, plus the buy & hold trio
    (computed from C0·P[t]/P[0]); the dict written to results/metrics.json."""
    ...


def buy_and_hold(price: pd.Series, c0: float) -> pd.Series:
    """Reference line computed directly from the price cache: value[t] = C0 · P[t] / P[0]."""
    ...


def plot_equity(strategy: pd.Series, buy_hold: pd.Series, metrics: dict, out_path: str) -> None:
    """Plot strategy equity vs buy & hold AAPL (both starting at $1M) on one time axis;
    add a stats box annotating each line's total_return / Sharpe / MaxDD; save to out_path
    (results/equity_curve.png). Reusable by the Step-6 notebook."""
    ...
```

## How It Connects

After the S4.1 loop has marked every session to market, it hands its daily equity series and position
series to this layer: `daily_returns` converts the dollar curve into fixed-base returns by dividing
each day's change by the unchanging \$1M, and from those returns `sharpe`, `sortino`, and `hit_rate`
fall out, while `max_drawdown` walks the running dollar peak and reports the trough as a fraction of
initial capital, and `turnover` and `avg_holding_period` read the position series to summarize churn
and how long the book sits on one side. `compute_metrics` bundles all of these — together with the
same headline trio for the directly-computed buy-and-hold line (\$1M·P[t]/P[0]) — into the dict that
becomes `results/metrics.json`, and `plot_equity` draws both equity lines from their shared \$1M
origin with a stats box pinned on the figure, saving `results/equity_curve.png`. The result is that
the backtester's raw march through history becomes a single readable scorecard and a single readable
picture — the deliverable a reviewer judges, and the exact figures the Step-6 notebook and web report
re-render without recomputing.

## Key Technology, Design Patterns & Packages

- **pandas** — vectorized return, drawdown (cumulative max), run-length and rolling math over the dated
  equity / position series; the metric functions are thin wrappers over Series operations.
- **matplotlib** — the dual-line equity chart with an on-figure stats box (text annotation); kept
  deliberately plain so the headline numbers, not styling, are the message.
- **vectorbt — optional cross-check only** — its `Portfolio.stats()` can validate the *standard*
  Sharpe/Sortino/MDD on a toy series, but it is NOT the source of record (its `/peak` drawdown and
  full-compounding differ from our `/C0` convention and capped sizing).
- **Design pattern: pure functions over a loop driver** — each metric is a stateless function of the
  equity/position series, so the same scorecard logic is reused unchanged by the backtest, the Step-5
  ablation suite, and the Step-6 notebook.
- **json** — serializing the metric dict to `results/metrics.json` for downstream rendering.
- **Why:** computing everything on the fixed \$1M base (not moving equity) and the labeled `/C0`
  drawdown keep the scorecard internally consistent with the capped-notional account and honest about
  reading deeper than the conventional `/peak`.

## Definition of Done

- [ ] **Acceptance command:** metrics unit test green — `.venv/bin/python -m pytest tests/test_metrics.py -q` (also exercised end-to-end via `--mode backtest`, which writes `results/metrics.json` + `results/equity_curve.png`).
- [ ] **Tests:** offline + deterministic toy-series test with hand-calculated expectations: assert **MaxDD** `= min((E[t] − peak$[t]) / C0)` (drawdown divided by INITIAL CAPITAL, not `/peak`), assert **Sharpe** on fixed-base returns `r[t] = ΔE / C0` (annualized `√252`) matches the hand calc, and cover `total_return`, `sortino`, `hit_rate`, `turnover` (ties out with S4.1 fee-on-change count), `avg_holding_period` (position run-length); optionally cross-check the *standard* Sharpe/Sortino/MDD against vectorbt on the toy series.
- [ ] **Gate:** `make check` (lint + typecheck + test + e2e) green.
- [ ] **features.json:** F12 → `passing` with evidence (metrics test + acceptance command output + `make check` date).
- [ ] **Artifacts:** writes `results/equity_curve.png` — **strategy vs buy & hold** (both from $1M, buy & hold = `C0·P[t]/P[0]`) with an on-chart stats box showing each line's **total return / Sharpe / MaxDD**; consumes `results/equity_curve.csv` from S4.1.
- [ ] **Rules:** every metric on the fixed $1M base (`C0`) net of fees — never a moving equity denominator; MaxDD divided by INITIAL CAPITAL and **labeled** as the `/C0` convention (reads deeper than `/peak`); computed only over the 2025–2026 test window; `initial_capital` sourced from config, not hardcoded; vectorbt used for cross-check only, never as source of record.
- [ ] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` ADR for the `/C0` (initial-capital) drawdown convention.
