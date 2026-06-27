# S5.3 — Ablations

## Objective
Beating the baselines proves the system works; the ablations prove *why* it works — and which parts actually earn their keep. The trick that makes this scientific instead of anecdotal is a discipline borrowed from the guiding principles: **every variant is a `Config` toggle, never a code fork.** We run the *same* compiled graph over the *same* test window with the *same* frozen calibrator and the *same* LLM cache, flipping one feature flag at a time, and the LangGraph builder from Step 3 simply bypasses the corresponding node. Five ablations isolate the project's headline contributions. **Stateless daily classifier** (`stateless=True`) throws away `PortfolioState` and hysteresis so the system re-decides from scratch each day — the contrast that shows the state-aware policy cuts turnover and lifts risk-adjusted return (research question #3). **No-memory** (`use_memory=False`) drops the FAISS retrieval + MemoryAgent — the central ablation answering "does episodic memory add alpha?" (question #2). **No-macro** (`use_macro=False`) removes the MacroAgent and its risk-off veto. **No-debate** (`use_debate=False`) skips the Bull/Bear DebateAgent and lets the analyst signals decide directly — answering "does adversarial debate help?" (question #1). **No-hysteresis** (`use_hysteresis=False`) keeps state but collapses the thresholds (`tau_enter == tau_exit`) so there is no asymmetric dead-band. Each variant runs through the identical dollar-accounting backtest and emits a full metrics row and an equity curve; we aggregate everything — baselines included — into one tidy table (`results/ablation_table.csv` + `.md`) and a folder of per-variant curves. Because only one knob moves per run and everything else is frozen, each row is a clean attribution of that one component's contribution. **Note:** the flags `use_memory/use_macro/use_debate/use_hysteresis/stateless` are referenced in PLAN.md (Step-3 inputs) as "added here for Step 5's ablations" but are **not yet present in `config.py`** — they must be added to the `Config` dataclass (default `True`/`False` for full behavior) as part of this step.

## Inputs and Outputs
**Inputs**
- `config.py`: a `base_config` (the full system) plus the ablation feature flags to be **added** — `use_memory: bool = True`, `use_macro: bool = True`, `use_debate: bool = True`, `use_hysteresis: bool = True`, `stateless: bool = False`. Plus shared knobs held constant across variants: `test_start/end`, `initial_capital`, `fee_bps`, `tau_enter/tau_exit/tau_flip`, `h`.
- The frozen `results/calibrator.pkl` (S5.1) — the same calibrator for every variant.
- The shared LLM cache `data/{ticker}_llm_cache.json` (reused so the suite is cheap after the first full run).
- The Step-3 graph (`build_graph` honoring the flags) + Step-4 backtest loop; the S5.2 baselines.
- `src/eval/ablation.py` (`run_ablations`); `--mode ablation` in `src/main.py`.

**Outputs**
- `results/ablation_table.csv` and `results/ablation_table.md` — one row per variant (full + 5 ablations) **and** the three baselines; columns: total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period.
- `results/curves/<variant>.csv` (+ optional `.png`) — per-variant dollar equity curves under `results/curves/`.
- `python -m src.main --mode ablation` produces all of the above (and triggers S5.1 calibration + S5.2 baselines if their artifacts are missing).

## Skeleton Python Code
```python
# src/eval/ablation.py
from __future__ import annotations

from dataclasses import replace

from config import Config


# Each entry: variant name -> the config overrides (feature-flag toggles only).
ABLATION_VARIANTS: dict[str, dict] = {
    "full":           {},
    "stateless":      {"stateless": True, "use_hysteresis": False},
    "no_memory":      {"use_memory": False},
    "no_macro":       {"use_macro": False},
    "no_debate":      {"use_debate": False},
    "no_hysteresis":  {"use_hysteresis": False},  # collapse: tau_exit := tau_enter
}


def make_variant_config(base_config: Config, overrides: dict) -> Config:
    """Return a copy of base_config with only the given feature flags toggled
    (dataclasses.replace) — variants are config toggles, never code forks."""
    ...


def run_one_variant(name: str, config: Config) -> dict:
    """Run a single variant over the test window via the SAME engine + frozen calibrator
    + shared LLM cache; persist its curve to results/curves/. Returns {'curve','metrics'}."""
    ...


def run_ablations(base_config: Config) -> dict:
    """Ensure calibrator + baselines exist, run every ABLATION_VARIANTS variant over the
    same engine (reusing the LLM cache), aggregate all rows (+ baselines) into a tidy table,
    write results/ablation_table.csv + .md and per-variant curves. Returns the comparison dict."""
    ...


def _write_table(rows: list[dict], csv_path: str, md_path: str) -> None:
    """Render the aggregated metrics rows to results/ablation_table.csv and a Markdown
    table for the write-up (pandas.to_csv / to_markdown)."""
    ...
```

## How It Connects
The ablation suite is where the whole Step-5 machinery pays off as evidence: the warm-up of S5.1 left a frozen calibrator and a warmed memory, the S5.2 baselines fixed the yardsticks, and now each ablation reruns the *identical* compiled graph and dollar-accounting loop with exactly one feature flag flipped — the LangGraph builder reads that flag and quietly bypasses a node (no MacroAgent, no debate, no retrieval, or a stateless re-decide), so the only thing that differs between two rows of the table is the one component under test. Because every variant shares the same test window, the same fees, the same frozen calibrator and the same LLM cache, the suite is both cheap to rerun and rigorously fair, and the resulting `ablation_table.md` reads as a direct, side-by-side attribution: how much Sharpe memory adds, how much turnover hysteresis removes, whether debate beats raw analyst signals — the scientific spine of the final report (Step 6).

## Additional experiments folded in (first live run: under-investment / never-shorts / churn)

The first live backtest (2025–2026: +9.1% vs buy & hold +23.0%, flat 65% of days, 0 shorts, fees ~40% of
gross) motivates three extra experiments. Each stays a **`Config` toggle / new knob over the same engine**
(no code fork), and each is scored as one more row in `ablation_table.md` against `full`:

- **`risk_off` veto: persistence / size-down** (`risk_off_persistence: int = 1`, `risk_off_mode: "flat"|"size_down"`).
  The `regime == risk_off` veto was the biggest forced-flat driver (52 days) and also ejected positions
  during recoveries. Variant: require ≥2 consecutive risk-off sessions to fire, or down-size instead of
  forcing flat. Tests whether the crash-avoidance edge survives a less twitchy veto.
- **Turnover control** (`min_holding_days: int = 0`, and/or a wider `tau_enter↔tau_exit` dead-band).
  Avg hold was 3.2 days; fees ate ~40% of gross P&L. Variant: enforce a minimum holding period and/or
  smooth the thesis-invalidation gate (the LLM flipping its own thesis day-to-day, which the taus do not
  touch). Tests how much fee drag is recoverable without hurting return.
- **Shorts on/off + short-trade expectancy** (`allow_short` already exists). With Gate-A (ADR-016) +
  Gate-B (abstention `agreement`) in place, run `allow_short=True` vs `False` and **report short-trade
  expectancy on the 2022–2024 warm-up** before trusting shorts in the test window. If warm-up shows no
  short edge, calibration should keep shorts rare (the system working, not failing).

These are **stretch rows** — they must not block `F14` (the original five ablations are the acceptance
bar). New knobs go in `config.py` with safe defaults that reproduce current behavior
(`risk_off_persistence=1`, `risk_off_mode="flat"`, `min_holding_days=0`). Validate any threshold/knob on
the **2022–2024 warm-up** and freeze before the test (never tune on the 2025–2026 curve).

## Key Technology, Design Patterns & Packages
- **Config-flag Strategy pattern** — each ablation is a `dataclasses.replace` of one base `Config`; the graph selects which nodes to run from the flags, so behavior varies without a single code fork (the project's "ablations are toggles, not forks" rule).
- **LangGraph conditional node bypass** — the Step-3 builder includes/skips nodes (MacroAgent, DebateAgent, MemoryStore retrieval, hysteresis band) by feature flag, the mechanism that makes one engine serve every variant.
- **Shared LLM cache (keyed by `(ticker, date, agent)`)** — reused across all variants so the suite is essentially free after the first full run.
- **pandas** — aggregate variant + baseline metrics into a tidy DataFrame, emit `.csv` and `.md` (`to_markdown`) for the notebook and write-up.
- **matplotlib (`plot_equity` reuse)** — per-variant curves under `results/curves/`, drawn with the same helper as the strategy and baselines for visual consistency.

## Definition of Done
- [x] **Acceptance command:** `.venv/bin/python -m pytest tests/test_eval.py -k ablation -q` → 3 passed (✅ 2026-06-25); `--mode ablation` wired (`run_ablations`).
- [x] **Tests:** offline & deterministic. Every variant (`full`, `stateless`, `no_memory`, `no_macro`, `no_debate`, `no_hysteresis`) runs through the SAME `Backtester` loop with one flag flipped and emits a full metrics row; `make_variant_config`, `_write_table`, and the no-hysteresis collapse have unit tests. Integration runs over a short (~6-session) window for speed (each obs still carries full history ≤ t).
- [x] **Gate:** `make check` green (lint + typecheck + 105 unit + e2e); check-lookahead clean (variants reuse the t+1 loop; test window only).
- [x] **features.json:** `F14` → `passing` (ADR-022).
- [x] **Artifacts:** `results/ablation_table.{csv,md}` (6 variant rows + the 3 S5.2 baselines) + `results/curves/<variant>.csv`. (MD written manually — no `tabulate` dep; per-variant `.png` skipped, optional.)
- [x] **Rules:** `Config` toggles over ONE engine — no code forks (`dataclasses.replace`); variants reuse the LLM cache + the frozen calibrator (when present) and hold `test_start/end`, `fee_bps`, `tau_*`, `h` constant; test window only (no warm-up PnL). `use_hysteresis` wired into the PositionManager (collapse `tau_exit:=tau_enter`).
- [x] **Tracking:** `PROGRESS.md` updated; ablation flags already in `config.py`; `DECISIONS.md` **ADR-022** records the no-hysteresis collapse + `Backtester.run(write=)` + the deferred stretch experiments.
