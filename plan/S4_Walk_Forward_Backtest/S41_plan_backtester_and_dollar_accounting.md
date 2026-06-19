# S4.1 — Backtester & Dollar Accounting

## Objective

Up to now the system can think for a single day: hand it a date and it returns a `TradeDecision`.
This sub-step turns that one-day brain into a *career*. We build a `Backtester` that opens a
\$1,000,000 brokerage account on the first day of the 2025–2026 test window and then walks forward,
one trading session at a time, carrying its `PortfolioState` (current position, thesis, days held)
the way a real trader carries a book across days. On each day `t` it asks the graph what it wants the
position to be, and — crucially — only *acts* on that wish at the **next** session's price (`t+1`),
so no decision is ever made with knowledge of the bar it trades on.

The money is tracked honestly, not as an abstract return series. Sizing is **capped notional**: the
moment we open a position we deploy `notional = min($1M, equity)` — a flat \$1M with the rest parked in
cash when we are above water, but all-in when we are underwater — convert that into a fixed number of
shares at the entry price, and then simply *hold* those shares, marking them to market every day. A
fee (`fee_bps`) is charged only when the position actually changes, and a flip (long↔short) crosses
zero so it turns over double the notional and pays double the fee. As the loop runs it writes out the
day-by-day equity curve and a rich `trace.json` that remembers *why* every decision was made — the
news read, each agent's rationale, the debate, the conviction, and the final call — which is the raw
material the Step-6 explainable report feeds on.

## Inputs and Outputs

**Inputs**
- `config` (`config.py`): `test_start` / `test_end` (window), `initial_capital` (= 1_000_000),
  `position_sizing` (= `"capped_notional"`; `"full_compounding"` is a Step-5 ablation), `fee_bps`
  (cost per position change), `allow_short`, `offline`.
- Step 3 artifacts: the compiled LangGraph `app` from `build_graph(config, store)`, `run_one_day(...)`,
  and the `MemoryStore` (for `stage` / `flush_due`).
- Step 1 prices: the price cache (`config.price_cache_path()`) read through the data layer, giving the
  point-in-time adjusted close `P[t]` used for mark-to-market and the `t+1` execution price.

**Outputs**
- `results/equity_curve.csv` — one row per test session: `date, position, action, P, shares, pnl,
  fee, equity, cum_pnl_strategy, cum_pnl_buyhold`. CSV, under `results/` (gitignored).
- `results/trace.json` — list of per-day records (see skeleton), each with `cum_pnl_strategy`,
  `cum_pnl_buyhold`, `position`, `action`, `conviction` (+ breakdown), `news`, per-agent
  `{signal/regime, rationale}`, debate `{bull_case, bear_case, thesis_still_valid}`, and final
  `{new_position, reason}`. JSON array, under `results/`.
- `results/decisions_log.csv` — flat per-day signals + rationale + position (notebook-friendly view).
- `results/metrics.json` — written by the S4.2 metrics layer, which the `Backtester` calls before
  returning (see S4.2). Returned in-memory as part of the `run_backtest(config)` dict.

## Skeleton Python Code

```python
"""src/backtest/run_backtest.py — walk-forward backtester + dollar accounting (M4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from config import Config


@dataclass
class DayRecord:
    """One test-session row: the execution and the full reasoning trace for trace.json."""
    t: date
    position: int                 # position held over session t (-1/0/+1), set at t-1, acted t
    action: str                   # hold | open | close | flip (from TradeDecision)
    price: float                  # adjusted close P[t] used for mark-to-market
    shares: float                 # signed share count currently held
    pnl: float                    # shares · (P[t] - P[t-1])
    fee: float                    # (fee_bps/1e4) · |Δ notional traded|; 0 on no change
    equity: float                 # E[t] = E[t-1] + pnl - fee ; E[0] = C0
    cum_pnl_strategy: float       # E[t] - C0
    cum_pnl_buyhold: float        # C0·P[t]/P[0] - C0
    conviction: float
    trace: dict = field(default_factory=dict)  # news, per-agent rationales, debate, final decision


class Backtester:
    """Owns the walk-forward loop over the test window (Template Method / loop driver).

    Carries PortfolioState day-to-day, executes each day's target position at t+1, and keeps a
    dollar account starting at C0 = initial_capital under CAPPED-NOTIONAL sizing.
    """

    def __init__(self, config: Config) -> None:
        """Hold config, build the graph + MemoryStore, load test-window prices, init E[0]=C0."""
        ...

    def _entry_notional(self, equity: float) -> float:
        """Capped-notional sizing, set ONCE at entry: notional = min(C0, equity).
        Fixed $1M above water (rest in cash); all-in when underwater. Not re-sized while held."""
        ...

    def _shares_for(self, target_position: int, notional: float, p_exec: float) -> float:
        """shares = ±notional / P_exec  (sign = target direction). P_exec is the t+1 price."""
        ...

    def _fee(self, shares_before: float, shares_after: float, p_exec: float) -> float:
        """Fee only on a position CHANGE: (fee_bps/1e4) · |Δ notional traded|.
        A flip crosses zero, so |shares_after - shares_before| covers double notional -> double fee."""
        ...

    def step(self, t: date, t_next: date, portfolio, store) -> DayRecord:
        """One walk-forward iteration:
          1. decision = run_one_day(app, t, portfolio, store)  # uses data <= t only
          2. execute decision.new_position at t_next's price (t+1 execution, no lookahead):
             on a change -> notional = _entry_notional(equity); shares = _shares_for(...); pay _fee(...)
          3. mark-to-market: pnl = shares·(P[t]-P[t-1]); E[t] = E[t-1] + pnl - fee
          4. store.stage(obs, action); store.flush_due(t, prices)   # delayed-write memory
          5. capture the day's trace (news, agent rationales, debate, final decision)."""
        ...

    def run(self) -> dict:
        """Walk every session in [test_start, test_end], skipping NaN-warmup dates cleanly.
        Build the equity DataFrame, compute buy & hold (C0·P[t]/P[0]), call the S4.2 metrics +
        plot helpers, persist equity_curve.csv / trace.json / decisions_log.csv / metrics.json,
        and return {'equity': df, 'metrics': {...}, 'trace': [...]}."""
        ...

    def _write_artifacts(self, records: list[DayRecord], metrics: dict) -> None:
        """Persist results/equity_curve.csv, results/trace.json, results/decisions_log.csv."""
        ...


def run_backtest(config: Config) -> dict:
    """Public entrypoint (called by `python -m src.main --mode backtest`).
    Construct a Backtester and run the walk-forward loop; return metrics + equity curve + trace."""
    ...
```

## How It Connects

The story is a single forward march through time: the `Backtester` opens its \$1M account, then for
each session `t` it asks the Step-3 graph (via `run_one_day`) what position it wants — a question that
can only see data up to `t` — and records the wish without acting on it yet; on the following session
`t+1` it converts that wish into shares at the next bar's price using capped-notional sizing, pays a
fee only if the position actually changed (double on a flip), and from then on simply holds the shares
and marks them to market each day so the equity `E[t]` grows or shrinks with `shares·(P[t]−P[t−1])`.
After settling the day it stages today's episode into memory and flushes any whose outcome window has
closed, then advances. As the loop turns, every day appends a row to the growing equity curve and a
fully-reasoned record — news, each agent's rationale, the bull/bear debate, the conviction, and the
final decision — to the trace; when the march reaches `test_end` the backtester hands the equity
series and the directly-computed buy-and-hold line (\$1M·P[t]/P[0]) to the S4.2 metrics and chart
helpers, writes out `equity_curve.csv`, `trace.json`, `decisions_log.csv`, and `metrics.json`, and
returns the headline numbers — the honest, fee-net record of the system's simulated career.

## Key Technology, Design Patterns & Packages

- **pandas** — the price frame, the per-day equity DataFrame, run-length holding-period math, and CSV
  serialization; the natural container for a dated, columnar walk-forward log.
- **Custom dollar P&L loop (not vectorbt's default)** — vectorbt compounds on *full* equity, which
  would silently break the capped-notional rule (`min($1M, equity)` set at entry); we must own the loop
  so the cap, the t+1 execution offset, and the fee-on-change accounting are exactly honored.
- **vectorbt — optional cross-check only** — may be used to sanity-check the *standard* metrics on a
  toy series; it is never the compounding engine of record.
- **Design pattern: Template Method / loop driver** — `Backtester.run` fixes the day's skeleton
  (decide → execute at t+1 → mark-to-market → memory flush → record) while `run_one_day` supplies the
  varying per-day reasoning; this keeps the anti-lookahead ordering in one auditable place.
- **json** — emitting the structured `trace.json` that powers the Step-6 explainable web report.
- **Why:** owning the loop is what makes the PnL *honest and reproducible* — the sizing cap, the
  one-session execution lag, and the fee model are the difference between a trading-realistic result
  and an inflated one.

## Definition of Done

- [x] **Acceptance command:** `--mode backtest --offline` runs the walk-forward loop end-to-end (45 sessions over the offline 2025 window) and exits 0. ✅ 2026-06-19
- [x] **Tests:** offline + deterministic; **t+1 execution** asserted (a day-t target applies to t+1's return — the day-0 long earns nothing day0→day1, only day1→day2); **fee only on a position change** with **flip = double** (`_fee(+N,-N) == 2·_fee(0,N)`); **turnover ties out** (fee days == open/flip/close count); **capped-notional** `min($1M, equity)` (cap above water, all-in underwater). The dollar primitives are tested directly with injected targets (the offline graph is hold-flat, so it never trades).
- [x] **Gate:** `make check` green (ruff + mypy 23 files + 70 unit + e2e).
- [x] **features.json:** F12 → `passing` with evidence.
- [x] **Artifacts:** writes `results/{equity_curve.csv, metrics.json, decisions_log.csv, trace.json}` (Step-6 report source) under gitignored `results/`.
- [x] **Rules:** dollar accounting on the fixed $1M base net of fees; only the test window is looped (no warm-up PnL); a **custom dollar loop, NOT vectorbt** (vectorbt not used); `fee_bps`/`initial_capital`/`position_sizing`/`results_dir` in config.
- [x] **Tracking:** PROGRESS.md updated; ADR-012 (capped-notional + offline 2025 fixture slice + think/account split); `initial_capital`/`position_sizing`/`results_dir` added to config. NOTE: risk metrics (Sharpe/MaxDD/turnover/avg-holding) are a minimal stub here — the full metrics module + equity chart are S4.2.
