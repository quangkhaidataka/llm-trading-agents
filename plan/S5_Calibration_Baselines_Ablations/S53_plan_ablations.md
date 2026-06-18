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

## Key Technology, Design Patterns & Packages
- **Config-flag Strategy pattern** — each ablation is a `dataclasses.replace` of one base `Config`; the graph selects which nodes to run from the flags, so behavior varies without a single code fork (the project's "ablations are toggles, not forks" rule).
- **LangGraph conditional node bypass** — the Step-3 builder includes/skips nodes (MacroAgent, DebateAgent, MemoryStore retrieval, hysteresis band) by feature flag, the mechanism that makes one engine serve every variant.
- **Shared LLM cache (keyed by `(ticker, date, agent)`)** — reused across all variants so the suite is essentially free after the first full run.
- **pandas** — aggregate variant + baseline metrics into a tidy DataFrame, emit `.csv` and `.md` (`to_markdown`) for the notebook and write-up.
- **matplotlib (`plot_equity` reuse)** — per-variant curves under `results/curves/`, drawn with the same helper as the strategy and baselines for visual consistency.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m src.main --mode ablation` (and `.venv/bin/python -m pytest tests/test_eval.py -k ablation -q`).
- [ ] **Tests:** offline & deterministic (`Config(offline=True)`, `MockLLM`, fixtures, shared LLM cache — no network). Every variant (`full`, `stateless`, `no_memory`, `no_macro`, `no_debate`, `no_hysteresis`) **runs through the SAME compiled graph + dollar-accounting loop + frozen calibrator** with exactly one flag flipped, and **each emits a metrics row** (total return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg holding period).
- [ ] **Gate:** `make check` green (lint + typecheck + test + e2e).
- [ ] **features.json:** `F14` → `passing` with evidence (the passing `--mode ablation` run + date; `ablation_table.md` path). M5a acceptance = comparison table + reliability diagram produced.
- [ ] **Artifacts:** `results/ablation_table.csv` + `results/ablation_table.md` (one row per variant **and** the three S5.2 baselines); `results/curves/<variant>.csv` (+ optional `.png`).
- [ ] **Rules:** ablations are **`Config` feature-flag toggles over ONE engine — no code forks** (`dataclasses.replace`, graph bypasses nodes by flag); all variants **reuse the shared LLM cache + the frozen `results/calibrator.pkl`** and hold `test_start/end`, `fee_bps`, `tau_*`, `h` constant; **never report warm-up PnL**.
- [ ] **Tracking:** `PROGRESS.md` updated; **add the ablation feature flags to `config.py`** (`use_memory/use_macro/use_debate/use_hysteresis=True`, `stateless=False`) if not already present; `DECISIONS.md` ADR for the no-hysteresis collapse rule (`tau_exit := tau_enter`) or any non-obvious flag semantics.
