"""Dollar-accounting metrics + equity chart (spec §7.1, §13.1) — M4 S4.2.

EVERY metric is on the FIXED base C0 = initial_capital ($1M), net of fees — never a moving
equity denominator. Daily return is r[t] = ΔE / C0, so Sharpe/Sortino on r[t] equal the
Sharpe of the raw dollar P&L, annualized by √252. Max drawdown uses the deliberately
non-standard "/ INITIAL CAPITAL" convention — dd[t] = (E[t] - peak$[t]) / C0 — which reads
DEEPER than the usual /peak; it is labeled as such (`max_drawdown_over_c0`) so no one is misled.
"""

from __future__ import annotations

import pandas as pd

_ANNUALIZATION = 252


def daily_returns(equity: pd.Series, c0: float) -> pd.Series:
    """Fixed-base daily return r[t] = (E[t] - E[t-1]) / C0 (NOT divided by moving equity)."""
    return equity.diff().dropna() / c0


def total_return(equity: pd.Series, c0: float) -> float:
    """total_return = E[T] / C0 - 1 (net of fees)."""
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1]) / c0 - 1.0


def sharpe(returns: pd.Series, periods: int = _ANNUALIZATION) -> float:
    """Sharpe = mean(r) / std(r) · √periods on the fixed-base r[t] (C0 constant → = Sharpe of $ P&L)."""
    if len(returns) < 2:
        return 0.0
    sd = float(returns.std())
    if sd == 0:
        return 0.0
    return float(returns.mean()) / sd * (periods ** 0.5)


def sortino(returns: pd.Series, periods: int = _ANNUALIZATION) -> float:
    """Sortino = mean(r) / std(r | r<0) · √periods (downside-only deviation)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    dd = float(downside.std())
    if len(downside) < 2 or dd == 0:
        return 0.0
    return float(returns.mean()) / dd * (periods ** 0.5)


def max_drawdown(equity: pd.Series, c0: float) -> float:
    """MDD divided by INITIAL CAPITAL (convention, NOT /peak):
       peak$[t] = max(E[0..t]); dd[t] = (E[t] - peak$[t]) / C0; MDD = min(dd[t]) (<= 0)."""
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((equity - peak) / c0).min())


def hit_rate(returns: pd.Series) -> float:
    """Share of test days with r[t] > 0."""
    if returns.empty:
        return 0.0
    return float((returns > 0).mean())


def turnover(position: pd.Series) -> float:
    """Mean |Δ position| per session (churn). A pre-start flat (0) is prepended so an initial
    open registers; a flip contributes |Δ| = 2 — so this ties out with the fee-on-change count."""
    full = pd.concat([pd.Series([0]), position.reset_index(drop=True)], ignore_index=True)
    return float(full.diff().abs().dropna().mean())


def avg_holding_period(position: pd.Series) -> float:
    """Mean run-length of a non-zero position (consecutive days the book stays on one side).
    A change of side ends a run. Returns 0.0 when the book is never in a position."""
    runs: list[int] = []
    current = 0
    prev = 0
    for p in position:
        if p != 0 and p == prev:
            current += 1
        elif p != 0:
            if current:
                runs.append(current)
            current = 1
        else:  # flat ends any run
            if current:
                runs.append(current)
            current = 0
        prev = p
    if current:
        runs.append(current)
    return float(sum(runs) / len(runs)) if runs else 0.0


def buy_and_hold(price: pd.Series, c0: float) -> pd.Series:
    """Reference line computed directly from the price cache: value[t] = C0 · P[t] / P[0]."""
    return c0 * price / float(price.iloc[0])


def compute_metrics(equity: pd.Series, position: pd.Series, price: pd.Series, c0: float) -> dict:
    """Bundle every metric on the $1M base, net of fees, plus the buy & hold trio."""
    r = daily_returns(equity, c0)
    bh = buy_and_hold(price, c0)
    bh_r = daily_returns(bh, c0)
    return {
        "initial_capital": c0,
        "total_return": total_return(equity, c0),
        "sharpe": sharpe(r),
        "sortino": sortino(r),
        "max_drawdown_over_c0": max_drawdown(equity, c0),  # /C0 convention (reads deeper than /peak)
        "hit_rate": hit_rate(r),
        "turnover": turnover(position),
        "avg_holding_period": avg_holding_period(position),
        "buy_hold": {
            "total_return": total_return(bh, c0),
            "sharpe": sharpe(bh_r),
            "max_drawdown_over_c0": max_drawdown(bh, c0),
        },
    }


def plot_equity(strategy: pd.Series, buy_hold: pd.Series, metrics: dict, out_path: str) -> None:
    """Strategy equity vs buy & hold AAPL (both from $1M) on one axis, with an on-figure stats
    box (total_return / Sharpe / MaxDD per line). Saves a PNG; reusable by the Step-6 notebook."""
    import matplotlib

    matplotlib.use("Agg")  # headless / CI-safe
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(strategy.index, strategy.values, label="Strategy", color="#1f77b4")
    ax.plot(buy_hold.index, buy_hold.values, label="Buy & Hold", color="#888888", linestyle="--")
    ax.set_title("Strategy vs Buy & Hold (from $1M, net of fees)")
    ax.set_ylabel("Equity ($)")
    ax.legend(loc="upper left")

    bh = metrics.get("buy_hold", {})
    box = (
        f"Strategy   ret {metrics.get('total_return', 0):+.1%}  "
        f"Sharpe {metrics.get('sharpe', 0):.2f}  "
        f"MaxDD {metrics.get('max_drawdown_over_c0', 0):.1%}\n"
        f"Buy&Hold   ret {bh.get('total_return', 0):+.1%}  "
        f"Sharpe {bh.get('sharpe', 0):.2f}  "
        f"MaxDD {bh.get('max_drawdown_over_c0', 0):.1%}\n"
        f"(MaxDD divided by initial capital)"
    )
    ax.text(0.99, 0.02, box, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, family="monospace",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
