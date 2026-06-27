"""S5.2 — baselines (the yardsticks the system must beat).

Three decision rules pushed through the SAME Step-4 dollar-accounting loop
(`Backtester._run_accounting`: capped notional, t+1 execution, fee on change, $1M base) so the
comparison is fair to the decimal — only the per-day target sequence differs:

  - buy & hold AAPL (always long)         — no LLM
  - pure AV-sentiment (sign of AV score)  — no LLM; THE baseline to beat
  - single-agent (NewsAgent signal only)  — one cached LLM call/day; the protocol's value-add test

AV `ticker_sentiment_score` (`av_sentiment`) is the baseline-TO-BEAT, NEVER the system's own signal —
using it as the signal would launder AV's alpha as ours (CLAUDE.md / security-rules). The relevance
filter applies to the AAPL channel only (it already does, inside `get_observation`).
"""

from __future__ import annotations

from datetime import date

from config import Config

_DIR = {"long": 1, "flat": 0, "short": -1}


def _test_dates_prices(config: Config) -> tuple[list[date], list[float]]:
    """The test-window sessions + close prices — the same slice the Backtester loops over."""
    import pandas as pd

    from src.data.loaders import load_prices

    frame = load_prices(config.ticker, date.fromisoformat(config.test_end))
    window = frame.loc[pd.Timestamp(config.test_start):]
    dates = [ts.date() for ts in window.index]
    prices = [float(c) for c in window["close"]]
    return dates, prices


def _run_targets(config: Config, dates: list[date], prices: list[float], targets: list[int]) -> dict:
    """Push a per-day target sequence through the shared Step-4 dollar loop + metric set and
    assemble the equity curve. THE one accounting path for every baseline AND the strategy, so any
    gap between them is attributable to the decision rule, not the accounting."""
    import pandas as pd

    from src.backtest.metrics import compute_metrics
    from src.backtest.run_backtest import Backtester

    records = Backtester(config)._run_accounting(dates, prices, targets)
    if not records:
        empty = pd.DataFrame(columns=["date", "equity", "position"])
        return {"curve": empty, "metrics": {"sessions": 0}}

    idx = [r.t for r in records]
    equity = pd.Series([r.equity for r in records], index=idx, dtype=float)
    position = pd.Series([r.position for r in records], index=idx, dtype=float)
    price = pd.Series([r.price for r in records], index=idx, dtype=float)
    metrics = compute_metrics(equity, position, price, config.initial_capital)
    metrics.update({
        "sessions": len(records),
        "final_equity": records[-1].equity,
        "n_trades": sum(1 for r in records if r.fee > 0),
        "total_fees": sum(r.fee for r in records),
    })
    curve = pd.DataFrame({
        "date": [r.t.isoformat() for r in records],
        "equity": [r.equity for r in records],
        "position": [r.position for r in records],
    })
    return {"curve": curve, "metrics": metrics}


def _position_from_sentiment(score: float, config: Config) -> int:
    """Map a sentiment score to a target: +1 if score>0, -1 if score<0 (and allow_short) else 0."""
    if score > 0:
        return 1
    if score < 0:
        return -1 if config.allow_short else 0
    return 0


def _daily_av_score(obs) -> float:
    """Mean AV ticker_sentiment_score over today's relevance-filtered AAPL news (the gate's output;
    point-in-time ≤ t); 0.0 when there is no news."""
    scores = [float(it["av_sentiment"]) for it in obs.aapl_news if it.get("av_sentiment") is not None]
    return sum(scores) / len(scores) if scores else 0.0


def baseline_buy_and_hold(config: Config) -> dict:
    """Buy & hold AAPL: always long — deploy initial_capital at the (t+1) open and hold to the end,
    marked to market through the shared loop. Returns {'curve', 'metrics'}."""
    dates, prices = _test_dates_prices(config)
    return _run_targets(config, dates, prices, [1] * len(dates))


def baseline_av_sentiment(config: Config) -> dict:
    """THE baseline to beat. Per-day AV ticker_sentiment_score -> sign -> target position, run
    through the shared dollar loop. No LLM. Returns {'curve', 'metrics', '_av_scores'}."""
    from src.data.loaders import get_observation

    dates, prices = _test_dates_prices(config)
    scores = [_daily_av_score(get_observation(config.ticker, t)) for t in dates]
    targets = [_position_from_sentiment(s, config) for s in scores]
    out = _run_targets(config, dates, prices, targets)
    out["_av_scores"] = scores
    return out


def baseline_single_agent(config: Config) -> dict:
    """NewsAgent-only: trade the news signal each day (one cached LLM call/day; macro/technical/
    memory/debate are simply not consulted — a lone headline reader). Stateless daily classifier.
    Returns {'curve', 'metrics', '_llm_sentiments'}."""
    from src.agents.news import NewsAgent
    from src.data.loaders import get_observation
    from src.schemas import PortfolioState

    dates, prices = _test_dates_prices(config)
    agent = NewsAgent(config)
    flat = PortfolioState()
    targets: list[int] = []
    sentiments: list[float] = []
    for t in dates:
        obs = get_observation(config.ticker, t)
        sig = agent.run(obs, flat)
        d = _DIR[sig.signal]
        targets.append(0 if (d == -1 and not config.allow_short) else d)
        sentiments.append(float(sig.sentiment))
    out = _run_targets(config, dates, prices, targets)
    out["_llm_sentiments"] = sentiments
    return out


def _corr(a: list[float], b: list[float]) -> float:
    """Pearson correlation; 0.0 when undefined (a constant series or < 2 points)."""
    import numpy as np

    if len(a) < 2 or len(b) < 2 or len(a) != len(b):
        return 0.0
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def run_baselines(config: Config) -> dict:
    """Compute all three baselines from caches (no LLM for buyhold/av-sentiment; single-agent reuses
    the LLM cache), persist each equity curve to results/curves/, emit the corr(LLM_sentiment,
    AV_score) diagnostic (evidence the NewsAgent is not just echoing AV), and return
    {name: {'curve','metrics'}} — the metric rows are folded into the S5.3 comparison table."""
    import os

    bh = baseline_buy_and_hold(config)
    av = baseline_av_sentiment(config)
    sa = baseline_single_agent(config)

    curves_dir = os.path.join(config.results_dir, "curves")
    os.makedirs(curves_dir, exist_ok=True)
    bh["curve"].to_csv(os.path.join(curves_dir, "baseline_buyhold.csv"), index=False)
    av["curve"].to_csv(os.path.join(curves_dir, "baseline_avsentiment.csv"), index=False)
    sa["curve"].to_csv(os.path.join(curves_dir, "baseline_newsonly.csv"), index=False)

    return {
        "buy_hold": {"curve": bh["curve"], "metrics": bh["metrics"]},
        "av_sentiment": {"curve": av["curve"], "metrics": av["metrics"]},
        "single_agent": {"curve": sa["curve"], "metrics": sa["metrics"]},
        "corr_llm_sentiment_vs_av": _corr(sa.get("_llm_sentiments", []), av.get("_av_scores", [])),
    }
