# S6.2 — Non-LLM Robustness: Forward-Window `h` Sensitivity Sweep

## Objective
A single good equity curve invites the obvious question: *did you just get lucky with
one parameter?* This step answers it without spending a cent on a second LLM provider
(LLM-backbone robustness is descoped — Groq only, all-free). The most consequential
knob we have not yet stress-tested is `config.h`, the **forward-return / delayed-write
window** — it sets how far ahead "did the trade work?" is judged, which shapes both the
memory reward and how long an episode waits before it becomes retrievable. So we sweep
`h ∈ {1, 5, 10, 21}` (one day, one week, two weeks, one month; spec §7.1), re-run the
pipeline for each, and lay the headline metrics side by side. The beautiful part is
that this is *cheap*: changing `h` changes only the reward window and the write delay —
**not a single agent call** — so the `(ticker, date, agent)` LLM cache from the first
backtest is reused verbatim and every sweep run after the first is essentially free.
If the strategy's edge survives across `h`, the result is a property of the protocol,
not of one lucky setting. This sweep is one of *two* robustness artifacts; the other is
the Step-5 **ablation table**, which varies the components rather than the window.

## Inputs and Outputs
- **Inputs:**
  - A base `Config` (the calibrated, test-window config from Steps 4–5).
  - The shared LLM cache `data/{ticker}_llm_cache.json` (reused across every `h`),
    the price cache, and the warm-up-populated/calibrator artifacts.
  - The `h` grid `(1, 5, 10, 21)` and `run_backtest(config) -> dict` (Step 4).
  - `config.offline=True` path so `tests/test_robustness.py` runs deterministically.
- **Outputs:**
  - **`results/robustness_h.csv`** — one row per `h`, columns = the full metric set
    (total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period),
    all net of fees on the 2025–2026 window. Location: `results/` (gitignored).
  - **`results/robustness_h.md`** — the same table rendered as Markdown for the README
    / notebook / write-up.
  - **`tests/test_robustness.py`** — offline test asserting the sweep runs and emits a
    well-formed table (one row per `h`, expected columns, finite metrics).
  - Replaces the old model-sensitivity feature **F16** (LLM-swap descoped).
  - *Pointer:* `results/ablation_table.csv` / `.md` (Step 5) is the companion
    robustness artifact (component sensitivity).

## Skeleton Python Code
```python
# src/eval/robustness.py — non-LLM robustness: forward-window h sensitivity sweep (spec §7.1)
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from config import Config

H_GRID: tuple[int, ...] = (1, 5, 10, 21)  # 1d / 1w / 2w / 1mo forward windows


def run_h_sweep(base_config: Config, h_grid: tuple[int, ...] = H_GRID) -> pd.DataFrame:
    """Re-run the backtest for each h in h_grid and collect headline metrics into a tidy table.

    For each h, build a variant via dataclasses.replace(base_config, h=h) and call
    run_backtest. Only the memory reward window + delayed-write change — agent calls are
    identical — so the (ticker,date,agent) LLM cache is reused and reruns are ~free.
    Returns a DataFrame indexed by h with one column per metric (net of fees).
    """
    ...


def write_robustness_artifacts(table: pd.DataFrame,
                               csv_path: str = "results/robustness_h.csv",
                               md_path: str = "results/robustness_h.md") -> None:
    """Persist the sweep table to results/robustness_h.csv and a Markdown twin
    (results/robustness_h.md) for the README / notebook / write-up. No recompute here."""
    ...


def _backtest_metrics_for_h(base_config: Config, h: int) -> dict:
    """Run one backtest variant (h overridden) and return its metrics dict (the
    run_backtest(...) result), reusing the shared LLM cache. One row of the sweep."""
    ...
```

```python
# tests/test_robustness.py — offline, deterministic
from config import Config
from src.eval.robustness import H_GRID, run_h_sweep


def test_h_sweep_runs_offline_and_tabulates() -> None:
    """Offline (MockLLM + fixtures) sweep over h produces one row per h with the
    expected metric columns and finite values — proves the robustness driver works."""
    table = run_h_sweep(Config(offline=True))
    assert list(table.index) == list(H_GRID)
    ...
```

## How It Connects
This step leans entirely on machinery that already exists. The Step-4 backtester
(`run_backtest`) is the engine; all this driver does is hand it the same base config
with `h` swapped, four times, and stack the returned metrics into a table. Because the
LLM cache is keyed by `(ticker, date, agent)` and `h` never enters that key, the
expensive agent reasoning computed during the first backtest is reused untouched —
only the memory layer's reward window and write delay shift, which are pure arithmetic
over the price cache. The resulting `robustness_h.csv`/`.md` is then read (never
recomputed) by the S6.3 notebook and quoted in the README's results summary, where it
sits beside the Step-5 ablation table to make the same point from two angles: the
edge is not an artifact of one window or one component. Together they are the project's
non-LLM robustness story, standing in for the descoped model-swap experiment.

## Key Technology, Design Patterns & Packages
- **`dataclasses.replace(base_config, h=h)`** — config-only variation (the project's
  ablation/robustness idiom): every variant is a toggle over one engine, never a code
  fork, so all runs share data, fees, and calibrator.
- **LLM response cache reuse (`data/{ticker}_llm_cache.json`)** — keyed by
  `(ticker, date, agent)`; since `h` is not in the key, the sweep adds no LLM cost.
- **pandas** — tidy DataFrame indexed by `h` → `to_csv` + `to_markdown` for the two
  artifacts; the notebook reads them back with no recompute.
- **Offline-first testing (`config.offline=True`, MockLLM + fixtures)** — the sweep is
  deterministic and key-free in CI, so `test_robustness.py` runs in `make check`.
- **No new provider, no OpenAI, no server** — robustness is shown via the `h` sweep +
  the Step-5 ablations, honoring the all-free Groq-only budget.

## Definition of Done

- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_robustness.py -q` (offline) green; the sweep writes `results/robustness_h.csv` + `results/robustness_h.md`.
- [ ] **Tests:** `tests/test_robustness.py` runs **offline & deterministically** (`Config(offline=True)`, MockLLM + fixtures) — `run_h_sweep` produces one row per `h ∈ {1,5,10,21}` with the expected metric columns and finite, net-of-fees values, and `write_robustness_artifacts` emits the CSV + Markdown table.
- [ ] **Gate:** `make check` green (lint + typecheck + test + e2e).
- [ ] **features.json:** the `h`-sweep robustness work **replaces the descoped F16** (LLM model-swap is out of scope, Groq-only); flip F16 to `passing` with evidence reframed as the forward-window sweep (or mark descoped per the Step-5 ablation companion).
- [ ] **Artifacts:** `results/robustness_h.csv` (one row per `h`; total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period — all net of fees over 2025–2026) and `results/robustness_h.md` (the same table as Markdown for the README / notebook).
- [ ] **Rules:** each variant is `dataclasses.replace(base_config, h=h)` over the **one** backtest engine (no code fork); the shared `(ticker,date,agent)` LLM cache is reused since `h` is not in the key (no new LLM cost, no new provider); artifacts are written once and **read, not recomputed**, downstream.
- [ ] **Tracking:** `PROGRESS.md` updated; run the `update-progress` + `feature-status` skills to record state + evidence; note the F16-replacement decision in `DECISIONS.md`.
