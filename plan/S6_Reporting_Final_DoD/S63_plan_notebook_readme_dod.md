# S6.3 — Results Notebook, Final README & Definition-of-Done Acceptance

## Objective
This is the closing chapter — the part a reviewer actually reads first. We assemble
`notebooks/results.ipynb` into a clean narrative that *renders the work without redoing
it*: it loads the artifacts every prior step already saved to `results/` and displays
them — the equity curve (strategy vs buy & hold), the metrics-vs-baseline table, the
ablation comparison, the reliability diagram, the `h` robustness sweep, and a link to
the interactive `report.html`. No cell re-runs the backtest; the notebook is a fast,
deterministic *viewer*, so it always agrees with the saved numbers. Then we finalize
the `README.md` so it tells the whole story in one screen: the headline results, the
anti-lookahead commitment (the one promise a quant reviewer checks first), the
**pinned model** (OpenRouter Llama 3.3 70B, Dec-2023 cutoff — reproducibility), and the honest limitations (spec §11) — single
asset, title+summary news only, ~18-month one-regime test, one debate round. Finally we
add the project's **Definition of Done** gate: one acceptance test (and a `make` target)
that asserts every `results/*` artifact exists and the DoD invariants hold — the
backtest is net of fees and `test_no_lookahead` is green (spec §13.1). When this passes,
the project is *done* in a way anyone can verify with one command.

## Inputs and Outputs
- **Inputs:**
  - All saved artifacts under `results/` (no recompute): `metrics.json`,
    `equity_curve.csv` + `equity_curve.png`, `ablation_table.csv` (+ `.md`),
    `reliability_diagram.png`, `robustness_h.csv` (+ `.md`), and `report.html`.
  - Skeletons/files to finalize: `notebooks/results.ipynb`, `README.md`,
    `features.json`, `PROGRESS.md`.
  - `config` (pinned `provider="openrouter"` + `openrouter_model`, fee/date knobs) for the
    README's reproducibility + anti-lookahead sections.
- **Outputs:**
  - **`notebooks/results.ipynb`** — populated; cells load each artifact and render it
    (matplotlib + pandas tables + an HTML link to `report.html`). Read-only viewer.
  - **`README.md`** — final: results summary, anti-lookahead commitment, pinned model
    (OpenRouter Llama 3.3 70B), limitations (spec §11). Located at repo root.
  - **`tests/test_dod.py`** — acceptance test asserting all `results/*` artifacts
    exist + DoD invariants (backtest net of fees, `test_no_lookahead` green).
  - **`make report`** (or `make dod`) target running the acceptance check end-to-end.
  - `features.json` (F12–F15, F18, F02) flipped to `passing` with evidence;
    `PROGRESS.md` updated.

## Skeleton Python Code
```python
# tests/test_dod.py — final Definition-of-Done acceptance gate (spec §13.1)
from __future__ import annotations

from pathlib import Path

import pytest

# Every artifact the finished project must have produced under results/.
REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "results/metrics.json",
    "results/equity_curve.csv",
    "results/equity_curve.png",
    "results/ablation_table.csv",
    "results/reliability_diagram.png",
    "results/robustness_h.csv",
    "results/report.html",
)


@pytest.mark.parametrize("artifact", REQUIRED_ARTIFACTS)
def test_required_artifact_exists(artifact: str) -> None:
    """DoD: each headline results/* artifact was produced by the end-to-end run."""
    assert Path(artifact).exists()


def test_backtest_net_of_fees() -> None:
    """DoD invariant: results/metrics.json reflects a fee-charged run (fees applied on
    position changes) — equity/returns are net of fees, not gross."""
    ...


def test_no_lookahead_green() -> None:
    """DoD invariant: the anti-lookahead gate still holds — re-assert tests/test_no_lookahead.py
    passes so the credibility guarantee is part of the final acceptance, not a one-off."""
    ...
```

```python
# notebooks/results.ipynb — VIEWER cells (no recompute). Sketch of the key calls:
def render_results_notebook() -> None:
    """Notebook body, expressed as one helper for the skeleton: load saved artifacts
    and display them — never re-run the pipeline.

    Cells:
      1. img('results/equity_curve.png')                       # strategy vs buy & hold
      2. pd.read_json('results/metrics.json')                  # headline metrics table
      3. pd.read_csv('results/ablation_table.csv')             # component ablations
      4. img('results/reliability_diagram.png')                # conviction calibration
      5. pd.read_csv('results/robustness_h.csv')               # h-sweep robustness
      6. HTML('<a href="../results/report.html">interactive report</a>')
    """
    ...
```

## How It Connects
Everything upstream has been quietly writing files into `results/`; this step is where
those files become a story a person can read. The notebook opens each saved artifact —
the equity PNG from Step 4, the metrics and ablation tables from Steps 4–5, the
reliability diagram from Step 5, the `h`-sweep from S6.2 — and simply *shows* them,
with a link out to the clickable `report.html` from S6.1, so the notebook, the static
figures, and the interactive page all draw on the exact same numbers and can never
disagree. The README then distills the same artifacts into the one-screen pitch a
reviewer reads first, anchored by the anti-lookahead commitment and the pinned model
(OpenRouter Llama 3.3 70B). The DoD acceptance test is the seal on the package: it confirms the artifacts
are all present and the two non-negotiable invariants — fees charged, no look-ahead —
still hold, so "done" is something you *run*, not something we merely claim.

## Key Technology, Design Patterns & Packages
- **Jupyter notebook as a read-only viewer** — cells `pd.read_*` / `IPython.display`
  the saved `results/*`; deliberately *no* pipeline calls, so it renders fast and
  deterministically and stays consistent with the committed numbers.
- **matplotlib + pandas** — display the saved PNGs and tabulate the CSV/JSON metrics;
  the same libraries the upstream steps used to *make* them (no new dependency).
- **pytest acceptance gate + `make` target** — `test_dod.py` (artifact-existence +
  invariant checks) wired into `make report`/`make dod`, so the Definition of Done is
  executable and lands in `make check`.
- **Single-source-of-truth docs** — README / `features.json` / `PROGRESS.md` are kept
  in agreement via the `update-progress` + `feature-status` skills (the `doc_agent`),
  per the execution discipline; honest limitations (spec §11) over over-claiming.
- **No recompute, no new packages, no server** — the chapter only *packages* results,
  honoring YAGNI; the live backbone is pay-as-you-go OpenRouter.

## Definition of Done

- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_dod.py -q` (or `make dod` / `make report`) green — the project Definition of Done is something you *run*, not claim (spec §13.1).
- [ ] **Tests:** `tests/test_dod.py` is the final acceptance gate — it asserts **every `results/*` artifact exists** (`metrics.json`, `equity_curve.csv` + `.png`, `ablation_table.csv`, `reliability_diagram.png`, `robustness_h.csv`, `report.html`) and the two non-negotiable DoD invariants hold: **backtest is net of fees** (`metrics.json` reflects a fee-charged run) and **`test_no_lookahead` is green** (re-asserted, not a one-off).
- [ ] **Gate:** `make check` green, with `test_dod.py` wired into it (lint + typecheck + test + e2e); `make dod`/`make report` runs the acceptance check end-to-end.
- [ ] **features.json:** all relevant features flipped to `passing` with evidence (F12–F15 backtest/eval, **F18** report, **F02** anti-lookahead) **and F17 ticker-dynamic** moved from `active` to `passing` after full-pipeline verification (`config.ticker` swap re-runs with no other line changed).
- [ ] **Artifacts:** populated `notebooks/results.ipynb` (read-only viewer cells rendering the saved equity PNG, metrics, ablation, reliability diagram, `h`-sweep + an HTML link to `report.html`) and a finalized root `README.md`.
- [ ] **Rules:** the notebook **renders saved artifacts with no recompute** (no pipeline calls, no new dependency); `README.md` states the **anti-lookahead commitment** (priority #1), the **pinned model** (`provider="openrouter"` + `openrouter_model`, Llama 3.3 70B Dec-2023 cutoff, for reproducibility), and the honest **limitations** (spec §11: single asset, title+summary news only, ~18-month one-regime test, one debate round); honest framing over over-claiming.
- [ ] **Tracking:** `PROGRESS.md` updated; README / `features.json` / `PROGRESS.md` kept in agreement via the `update-progress` + `feature-status` skills (`doc_agent`); record the DoD close-out in `DECISIONS.md`.
