"""Walk-forward backtester + dollar accounting (spec §6, §13.1) — M4.

Opens a $C0 = initial_capital account on the first 2025-2026 session and walks forward
one session at a time, carrying PortfolioState. Each day t the graph decides a target
position from data <= t; that wish is EXECUTED at the NEXT session's price (t+1) — never
on the bar it traded on. Money is tracked honestly in dollars:

  * CAPPED-NOTIONAL sizing, set ONCE at entry: notional = min(C0, equity)
    (flat $1M above water with the rest in cash; all-in when underwater).
  * shares = ±notional / P_exec ; held and marked to market: pnl = shares·(P[t]-P[t-1]).
  * fee = (fee_bps/1e4)·|Δ notional| charged ONLY on a position change; a flip crosses
    zero so it turns over double the notional → double the fee.
  * E[t] = E[t-1] + pnl - fee ; report ONLY the test window, PnL net of fees.

We own the loop (NOT vectorbt's full-compounding default) so the cap, the t+1 offset,
and the fee-on-change accounting are exactly honored. Rich per-day traces are persisted
for the Step-6 explainable report. Risk metrics + the equity chart are added in S4.2.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from config import Config


@dataclass
class DayRecord:
    """One test-session row: the execution and the full reasoning trace for trace.json."""

    t: date
    position: int                 # position held over session t (-1/0/+1), set at t-1, acted t
    action: str                   # hold | open | close | flip (the executed transition)
    price: float                  # adjusted close P[t] used for mark-to-market
    shares: float                 # signed share count currently held
    pnl: float                    # shares · (P[t] - P[t-1])
    fee: float                    # (fee_bps/1e4) · |Δ notional traded|; 0 on no change
    equity: float                 # E[t] = E[t-1] + pnl - fee ; E[0] = C0
    cum_pnl_strategy: float       # E[t] - C0
    cum_pnl_buyhold: float        # C0·P[t]/P[0] - C0
    conviction: float             # today's calibrated conviction (drives t+1)
    trace: dict = field(default_factory=dict)  # news, per-agent rationales, debate, final decision


class Backtester:
    """Walk-forward loop driver over the test window with capped-notional dollar accounting."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.C0 = config.initial_capital

    # ── dollar-accounting primitives (pure, unit-tested directly) ────────────────
    def _entry_notional(self, equity: float) -> float:
        """Capped-notional sizing, set ONCE at entry: min(C0, equity). Fixed $1M above
        water (rest in cash); all-in when underwater. Not re-sized while held."""
        return min(self.C0, equity)

    def _shares_for(self, target_position: int, notional: float, p_exec: float) -> float:
        """shares = ±notional / P_exec  (sign = target direction; 0 when flat)."""
        return target_position * notional / p_exec

    def _fee(self, shares_before: float, shares_after: float, p_exec: float) -> float:
        """Fee only on a position CHANGE: (fee_bps/1e4)·|Δ notional|. A flip crosses zero,
        so |shares_after - shares_before| spans double notional → double fee."""
        return (self.config.fee_bps / 1e4) * abs(shares_after - shares_before) * p_exec

    @staticmethod
    def _action(cur_pos: int, target: int) -> str:
        if target == cur_pos:
            return "hold"
        if cur_pos == 0:
            return "open"
        if target == 0:
            return "close"
        return "flip"

    # ── the walk-forward dollar loop (pure given prices + per-day targets) ───────
    def _run_accounting(
        self,
        dates: list[date],
        prices: list[float],
        targets: list[int],
        traces: list[dict] | None = None,
        convictions: list[float] | None = None,
    ) -> list[DayRecord]:
        """Execute each day's target at the NEXT session (t+1): on session k we act on the
        target decided at k-1, mark existing shares to market over [k-1, k], and pay a fee
        only on a change. targets[k] is the wish decided at session k (executed at k+1)."""
        C0, P0 = self.C0, prices[0]
        equity, shares, cur_pos, prev_price = C0, 0.0, 0, None
        records: list[DayRecord] = []

        for k, t in enumerate(dates):
            P = prices[k]
            pnl = shares * (P - prev_price) if prev_price is not None else 0.0

            target = targets[k - 1] if k > 0 else 0  # decided yesterday → execute today (t+1)
            action = self._action(cur_pos, target)
            fee = 0.0
            if target != cur_pos:  # position CHANGE
                notional = self._entry_notional(equity + pnl)
                new_shares = self._shares_for(target, notional, P)
                fee = self._fee(shares, new_shares, P)
                shares, cur_pos = new_shares, target

            equity += pnl - fee
            records.append(
                DayRecord(
                    t=t, position=cur_pos, action=action, price=P, shares=shares,
                    pnl=pnl, fee=fee, equity=equity,
                    cum_pnl_strategy=equity - C0, cum_pnl_buyhold=C0 * P / P0 - C0,
                    conviction=(convictions[k] if convictions else 0.0),
                    trace=(traces[k] if traces else {}),
                )
            )
            prev_price = P
        return records

    # ── full run: think forward (point-in-time), then account, then persist ─────
    def run(self) -> dict:
        import pandas as pd

        from src.data.loaders import load_prices
        from src.graph.build_graph import build_graph, run_one_day
        from src.memory.store import MemoryStore
        from src.schemas import PortfolioState

        cfg = self.config
        store = MemoryStore(cfg)
        app = build_graph(cfg, store)

        # Test-window sessions = price index in [test_start, test_end]. We only ever loop the
        # test window, so warm-up (2022-2024) PnL is never reported.
        frame = load_prices(cfg.ticker, date.fromisoformat(cfg.test_end))
        window = frame.loc[pd.Timestamp(cfg.test_start) :]
        dates = [ts.date() for ts in window.index]
        prices = [float(c) for c in window["close"]]

        # 1) THINK forward, one session at a time (data <= t), staging/flushing memory.
        portfolio = PortfolioState()
        targets: list[int] = []
        traces: list[dict] = []
        convictions: list[float] = []
        for t in dates:
            decision = run_one_day(app, t, portfolio, store)
            targets.append(decision.new_position)
            trace = self._load_trace(t)
            traces.append(trace)
            convictions.append(float(trace.get("conviction", 0.0)))

        # 2) ACCOUNT in dollars (t+1 execution, capped notional, fee on change).
        records = self._run_accounting(dates, prices, targets, traces, convictions)

        # 3) METRICS + equity chart (S4.2), on the fixed $1M base, net of fees.
        idx = [r.t for r in records]
        equity = pd.Series([r.equity for r in records], index=idx, dtype=float)
        position = pd.Series([r.position for r in records], index=idx, dtype=float)
        price = pd.Series([r.price for r in records], index=idx, dtype=float)
        metrics = self._metrics(records, equity, position, price)
        self._write_artifacts(records, metrics, equity, price)

        equity_rows = [{"date": r.t.isoformat(), "equity": r.equity,
                        "cum_pnl_strategy": r.cum_pnl_strategy,
                        "cum_pnl_buyhold": r.cum_pnl_buyhold} for r in records]
        return {"equity": equity_rows, "metrics": metrics,
                "trace": [self._trace_row(r) for r in records]}

    # ── metrics: dollar-accounting scorecard on the fixed $1M base ──────────────
    def _metrics(self, records, equity, position, price) -> dict:
        if not records:
            return {"sessions": 0, "note": "no sessions in test window"}
        from src.backtest.metrics import compute_metrics

        metrics = compute_metrics(equity, position, price, self.C0)
        metrics.update({
            "sessions": len(records),
            "final_equity": records[-1].equity,
            "cum_pnl_strategy": records[-1].cum_pnl_strategy,
            "cum_pnl_buyhold": records[-1].cum_pnl_buyhold,
            "n_trades": sum(1 for r in records if r.fee > 0),
            "total_fees": sum(r.fee for r in records),
        })
        return metrics

    # ── persistence ─────────────────────────────────────────────────────────────
    def _write_artifacts(self, records: list[DayRecord], metrics: dict, equity, price) -> None:
        import csv

        out = self.config.results_dir
        os.makedirs(out, exist_ok=True)

        with open(os.path.join(out, "equity_curve.csv"), "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date", "position", "action", "P", "shares", "pnl", "fee",
                             "equity", "cum_pnl_strategy", "cum_pnl_buyhold"])
            for r in records:
                writer.writerow([r.t.isoformat(), r.position, r.action, r.price, r.shares,
                                 r.pnl, r.fee, r.equity, r.cum_pnl_strategy, r.cum_pnl_buyhold])

        with open(os.path.join(out, "trace.json"), "w") as fh:
            json.dump([self._trace_row(r) for r in records], fh, indent=2)

        with open(os.path.join(out, "decisions_log.csv"), "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["date", "position", "action", "conviction", "reason"])
            for r in records:
                reason = r.trace.get("decision", {}).get("reason", "")
                writer.writerow([r.t.isoformat(), r.position, r.action, r.conviction, reason])

        with open(os.path.join(out, "metrics.json"), "w") as fh:
            json.dump(metrics, fh, indent=2)

        if records:  # equity_curve.png — strategy vs buy & hold, both from $1M
            from src.backtest.metrics import buy_and_hold, plot_equity

            plot_equity(equity, buy_and_hold(price, self.C0), metrics,
                        os.path.join(out, "equity_curve.png"))

    def _trace_row(self, r: DayRecord) -> dict:
        row = dict(r.trace)
        row.update({
            "date": r.t.isoformat(), "position": r.position, "action": r.action,
            "conviction": r.conviction, "cum_pnl_strategy": r.cum_pnl_strategy,
            "cum_pnl_buyhold": r.cum_pnl_buyhold,
        })
        return row

    def _load_trace(self, t: date) -> dict:
        """Read the per-day trace the commit node wrote (config.log_dir/{ticker}_{t}.json)."""
        path = os.path.join(self.config.log_dir, f"{self.config.ticker}_{t.isoformat()}.json")
        if os.path.exists(path):
            with open(path) as fh:
                return json.load(fh)
        return {}


def run_backtest(config: Config) -> dict:
    """Public entrypoint (called by `python -m src.main --mode backtest`)."""
    result = Backtester(config).run()
    m = result["metrics"]
    print(f"[backtest] sessions={m.get('sessions')}  "
          f"final_equity={m.get('final_equity')}  trades={m.get('n_trades')}")
    print(f"[backtest] cum_pnl strategy={m.get('cum_pnl_strategy')}  "
          f"buy&hold={m.get('cum_pnl_buyhold')}  (net of {m.get('total_fees')} fees)")
    return result
