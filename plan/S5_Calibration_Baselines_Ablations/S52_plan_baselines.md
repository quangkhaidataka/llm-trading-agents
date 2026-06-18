# S5.2 — Baselines

## Objective
A PnL curve in isolation says nothing — a number only becomes a result once you can say *what it beat*. So before we celebrate the multi-agent system we build the yardsticks it must clear, and we build them honestly: straight from the data caches, with **no LLM in the loop**, so they are cheap, deterministic, and obviously free of look-ahead. There are three. **Buy & hold AAPL** is the "did all this machinery beat just owning the stock?" line — a single \$1M purchase at the test-window open, marked to market to the end (the same reference line already drawn in the Step-4 equity chart). **Single-agent (NewsAgent only)** strips the system down to one analyst reading headlines and trading its signal each day — it answers "does the *protocol* (macro + technical + debate + memory + hysteresis) add anything over a lone news reader?". And **pure AV-sentiment** trades purely on Alpha Vantage's own `ticker_sentiment_score` from the news cache — long when sentiment is positive, short/flat when negative — and this is **the baseline to beat**: it is the cheapest possible "sentiment → trade" strategy, and the whole NewsAgent prompt was deliberately designed (the surprise / priced-in nudge) so the LLM does *not* simply re-derive this score. Each baseline runs through the **same dollar-accounting backtest loop** as the real strategy (same \$1M base, same `fee_bps`, same `t+1` execution, same metric set) so the comparison is fair to the decimal. Each emits an equity curve and a full metrics row, ready to be stacked beside the strategy and the ablations in one comparison table.

## Inputs and Outputs
**Inputs**
- `config.py` knobs: `ticker`, `test_start`, `test_end` (the window all baselines run over); `initial_capital` (\$1M base), `fee_bps`, `allow_short`; `relevance_cutoff`, `max_news_per_day` (for the news-driven baselines).
- Caches only (no network, no LLM): `data/{ticker}_prices.parquet` (buy & hold + mark-to-market), `data/{ticker}_news.parquet` (carries per-item `av_sentiment` / `ticker_sentiment_score` and `relevance`).
- The Step-4 dollar P&L loop / metrics helper (reused, not reimplemented) and `plot_equity(...)`.
- For single-agent: the Step-2 `NewsAgent` chain + the Step-3 `run_one_day` engine driven with all non-news nodes bypassed (reuses the LLM cache).

**Outputs**
- `results/curves/baseline_buyhold.csv`, `results/curves/baseline_newsonly.csv`, `results/curves/baseline_avsentiment.csv` — per-baseline dollar equity curves (date, equity, position), starting at \$1M.
- A metrics row per baseline (total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period) — folded into the shared `results/ablation_table.csv` / `.md` produced in S5.3.
- Optional `results/curves/baseline_*.png` per-curve charts via `plot_equity` for the notebook.
- `corr(LLM_sentiment, AV_score)` diagnostic value emitted into the comparison report (shows the NewsAgent is not just echoing AV).

## Skeleton Python Code
```python
# src/eval/baselines.py
from __future__ import annotations

from config import Config


def baseline_buy_and_hold(config: Config) -> dict:
    """Buy & hold AAPL: deploy initial_capital at the test-window open, mark to market to
    the end (no fees after entry). Returns {'curve': DataFrame, 'metrics': dict}."""
    ...


def baseline_av_sentiment(config: Config) -> dict:
    """THE baseline to beat. From data/{ticker}_news.parquet, take the per-day AV
    ticker_sentiment_score (relevance-filtered, capped), map sign(score) -> target
    position, run it through the shared dollar P&L loop. Returns {'curve', 'metrics'}."""
    ...


def baseline_single_agent(config: Config) -> dict:
    """NewsAgent-only: run the engine with macro/technical/memory/debate bypassed, trade the
    NewsAgent signal each day (reuses the LLM cache). Returns {'curve', 'metrics'}."""
    ...


def _position_from_sentiment(score: float, config: Config) -> int:
    """Map a sentiment score to a target position: +1 if score>0, -1 if score<0 (and
    allow_short) else 0. Deterministic, no LLM."""
    ...


def run_baselines(config: Config) -> dict:
    """Compute all three baselines from caches (no LLM for buyhold/av-sentiment), persist
    each equity curve to results/curves/, and return {name: {'curve','metrics'}}."""
    ...
```

## How It Connects
The baselines are the measuring sticks that turn the strategy's equity curve into a verdict, and they earn their credibility by sharing the strategy's plumbing rather than inventing their own: buy & hold and AV-sentiment are pure vectorized reads off the same price and news caches, while single-agent reruns the very same Step-3 engine with every node but the NewsAgent switched off — yet all three are pushed through the identical Step-4 dollar-accounting loop, on the identical \$1M base, with the identical `fee_bps` and `t+1` execution and the identical metric set. Because the apparatus is held constant and only the *decision logic* varies, any gap between the full system and AV-sentiment is attributable to the protocol and not to some accounting quirk — exactly the fair comparison the ablation suite (S5.3) then extends component-by-component, all of it stacked into one comparison table where "beats the AV-sentiment baseline" is the headline claim.

## Key Technology, Design Patterns & Packages
- **pandas / numpy** — vectorized equity curves straight from the Parquet caches; no LLM, no network, fully deterministic.
- **Strategy pattern** — each baseline is a swappable "decision rule" plugged into the one shared dollar P&L loop, so the engine and accounting stay fixed while only the rule changes (the same idea ablations use via config flags).
- **Reuse of the Step-4 backtest loop + `plot_equity`** — guarantees baselines and the real strategy are measured by the exact same code (no divergent accounting), which is what makes the comparison honest.
- **Cache-only inputs (Repository reuse)** — reading the AV `ticker_sentiment_score` and prices straight from cache keeps the cheapest baseline genuinely cheap and obviously look-ahead-free.
- **Diagnostic `corr(LLM_sentiment, AV_score)`** — evidence the NewsAgent adds signal beyond the AV score it is built to beat, not a restatement of it.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_eval.py -k baseline -q` (curves/metrics emitted via the `--mode ablation` / baselines run).
- [ ] **Tests:** offline & deterministic (caches/fixtures only — no network, no LLM for buy & hold and AV-sentiment; single-agent reuses the LLM cache + `MockLLM`). Each of the three baselines **runs through the SAME Step-4 dollar-accounting loop** (same \$1M base, same `fee_bps`, same `t+1` execution) and **emits one full metrics row** (total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period).
- [ ] **Gate:** `make check` green (lint + typecheck + test + e2e).
- [ ] **features.json:** `F13` → `passing` with evidence (the passing baseline test command + date; curve paths).
- [ ] **Artifacts:** `results/curves/baseline_buyhold.csv`, `baseline_newsonly.csv`, `baseline_avsentiment.csv` (date, equity, position; start \$1M); metric rows folded into `results/ablation_table.csv` + `.md` (S5.3); optional `results/curves/baseline_*.png`.
- [ ] **Rules:** **AV `ticker_sentiment_score` is the baseline-to-beat, not the signal** (using it as the primary signal launders AV's alpha as ours); `relevance_cutoff` filters the AAPL channel only; reuse the Step-4 loop + `plot_equity` (no divergent accounting); emit `corr(LLM_sentiment, AV_score)` diagnostic; all knobs are numbers in `config.py`.
- [ ] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` ADR only if a non-obvious baseline choice is made (e.g. AV-sentiment sign/flat mapping).
