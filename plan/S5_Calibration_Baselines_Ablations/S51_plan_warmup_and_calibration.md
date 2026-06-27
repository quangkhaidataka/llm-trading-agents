# S5.1 — Warm-up & Conviction Calibration

## Objective
This is the moment the conviction number stops being a vibe and becomes a probability. Up to now (Steps 2–3) the system produces a raw score `z = alpha·conviction_raw + beta·conviction_sc` — a tidy 0–1 blend of agent agreement, mean confidence, memory consistency and self-consistency — but nobody has checked whether `z = 0.7` actually means the decision was right 70% of the time. It almost never does: a raw blend like this is usually mis-scaled. So before we touch the 2025–2026 test window, we replay the *entire* pipeline across the **2022–2024 warm-up** (`config.warmup_start` → `config.warmup_end`). This run does two jobs at once. First, it **populates the episodic memory** day by day with delayed-write discipline, so that by the time the test period starts, the FAISS index is already full of closed episodes for the test days to retrieve from — without that, the test period would face a cold-start memory and the no-memory ablation would look unfairly similar to the real thing. Second, on every warm-up day it records the pair `(z, hit)` — the raw conviction the system felt, and whether the decision was actually correct, where **"hit" is the sign of the drift-demeaned forward return matching the action** (the exact same definition as the memory reward, so the whole project agrees on what "right" means). We then fit a `Calibrator` (isotonic regression, with Platt/logistic as the small-data fallback) that learns the monotone map `z → P(correct)`, validate it with a **reliability diagram**, freeze it to `results/calibrator.pkl`, and from then on the PositionManager reads conviction through `calibrator.predict_proba(z)`. Only after this does `tau_enter = 0.70` honestly mean "≥70% real chance of being right." The iron rule: we **calibrate only on warm-up, freeze before the test, and never report warm-up PnL** — the warm-up exists to teach memory and the calibrator, nothing else.

## Inputs and Outputs
**Inputs**
- `config.py` knobs: `warmup_start`, `warmup_end` (2022-01-01 → 2024-12-31); `alpha`, `beta`, `w1`, `w2`, `w3` (the `z` blend); `h` and `reward_drift_window` (define the forward return + drift μ for the hit label); `tau_enter/tau_exit/tau_flip` (consumers of calibrated conviction); `seed`.
- The runnable pipeline from Steps 3–4: `build_graph`, `run_one_day`, `MemoryStore`; price cache `data/{ticker}_prices.parquet` (for the forward return / drift label).
- LLM cache `data/{ticker}_llm_cache.json` (so the warm-up replay is cheap on reruns).
- Stubs extended here: `src/eval/calibration.py` (`fit_calibrator`, `reliability_diagram`).

**Outputs**
- `results/calibrator.pkl` — pickled fitted `Calibrator` (isotonic or Platt); loaded by the PositionManager path. Frozen before the test.
- `results/reliability_diagram.png` — matplotlib reliability plot (predicted vs empirical hit rate per bin + diagonal).
- `results/calibration_report.json` — JSON: method used, n samples, per-bin counts, Brier score, ECE.
- Warm-up-populated FAISS index persisted on disk under `data/` / `faiss_index/` (gitignored).
- `results/warmup_pairs.csv` — the collected `(date, z, hit)` rows (diagnostic; never a PnL artifact).
- **No PnL artifact of any kind from the warm-up** — explicitly excluded.

## Skeleton Python Code
```python
# src/eval/calibration.py  (extends the Step-2 conviction module)
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from config import Config


@dataclass
class WarmupPair:
    """One calibration datum: raw conviction z and whether the decision was correct."""
    t: date
    z: float           # alpha*conviction_raw + beta*conviction_sc  (from raw_conviction)
    hit: int           # 1 if sign(drift-demeaned forward return) == action, else 0


def collect_warmup_pairs(config: Config) -> list[WarmupPair]:
    """Replay the full pipeline over [warmup_start, warmup_end] populating memory
    (delayed write) and collecting (z, hit) pairs. NEVER computes or reports PnL."""
    ...


def _hit_label(action: int, prices, t: date, config: Config) -> int:
    """hit = 1 if sign(action) == sign(forward_return(t,h) - mu) else 0; mu = trailing
    AAPL drift over reward_drift_window (point-in-time <= t). Same rule as memory reward."""
    ...


class Calibrator:
    """Wraps a fitted z -> P(correct) map (isotonic primary, Platt/logistic fallback)."""

    def __init__(self, method: str = "isotonic") -> None:
        """Hold the chosen sklearn estimator (IsotonicRegression or LogisticRegression)."""
        ...

    def fit(self, z_values: np.ndarray, hits: np.ndarray) -> "Calibrator":
        """Fit the monotone map on warm-up (z, hit) pairs. Returns self."""
        ...

    def predict_proba(self, z: float) -> float:
        """Map a raw conviction z to a calibrated probability of being correct (0..1)."""
        ...

    def save(self, path: str) -> None:
        """Pickle the fitted calibrator to results/calibrator.pkl (frozen before test)."""
        ...

    @classmethod
    def load(cls, path: str) -> "Calibrator":
        """Load a frozen calibrator; the PositionManager uses it (fallback to raw z if absent)."""
        ...


def fit_calibrator(z_values, hits, method: str = "isotonic") -> Calibrator:
    """Build + fit a Calibrator on the 2022-2024 (z, hit) set; return it (z -> P(correct))."""
    ...


def reliability_diagram(calibrator: Calibrator, z_values, hits, out_path: str) -> None:
    """Bin predicted vs empirical hit rate, plot against the diagonal with matplotlib,
    save to results/reliability_diagram.png; also report Brier + ECE."""
    ...


def run_warmup_calibration(config: Config) -> Calibrator:
    """Orchestrate S5.1: collect_warmup_pairs -> fit_calibrator -> reliability_diagram
    -> save results/calibrator.pkl + calibration_report.json. Returns the frozen Calibrator."""
    ...
```

## How It Connects
The warm-up is the rehearsal that makes the real performance honest: we walk the system day by day through 2022–2024 exactly as it will walk the test, so memory fills up with genuine closed episodes and the conviction engine emits a raw `z` for every decision, which we pair with whether that decision turned out right (sign of the drift-demeaned forward return, the same yardstick memory uses). Those `(z, hit)` pairs train a monotone calibrator that bends the raw blend onto the real probability axis, and we draw a reliability diagram to prove the bend worked before pickling the calibrator and locking it away. From that point nothing about the test can change the calibrator: when the backtest later runs 2025–2026, the PositionManager loads the frozen `results/calibrator.pkl`, turns each day's `z` into a true `P(correct)`, and compares it against `tau_enter / tau_exit / tau_flip` — so the thresholds finally carry their intended meaning. Crucially the warm-up's own profit-and-loss is thrown away entirely; its only legacy is a warmed memory index and a frozen calibrator, which is precisely what lets the baselines and ablations (S5.2, S5.3) reuse the same engine and the same calibrator for a clean, apples-to-apples comparison.

## Key Technology, Design Patterns & Packages
- **scikit-learn `IsotonicRegression`** (primary) — non-parametric, monotone, ideal for a `z → P` map; robust with the ~750 warm-up days. **`LogisticRegression` (Platt)** fallback when per-bin data is thin, to avoid isotonic overfitting.
- **matplotlib** — the reliability diagram (predicted vs empirical per bin + diagonal); same plotting stack as the equity curve so the notebook stays uniform.
- **Wrapper / Adapter pattern (`Calibrator`)** — a tiny `fit/predict_proba/save/load` facade hides which sklearn estimator is inside, so the PositionManager calls one stable method and the isotonic-vs-Platt choice never leaks out.
- **pickle** — freeze the fitted calibrator to disk so it is identical across the backtest, baselines and every ablation (reproducibility, no re-fit drift).
- **Frozen-after-fit discipline** — calibrate on warm-up only, then treat the artifact as read-only; this is the anti-lookahead guarantee for the conviction layer, mirroring the data gate's `≤ t` rule.

## Definition of Done
- [x] **Acceptance command:** `.venv/bin/python -m pytest tests/test_calibration.py -q` → 11 passed (✅ 2026-06-23). The LIVE `.venv/bin/python -m src.main --mode warmup` (produces the frozen artifacts over real 2022-2024 data) is the user's online run — wired + import-safe, not part of `make check`.
- [x] **Tests:** offline & deterministic. Assert isotonic **monotonicity** (`test_calibrator_isotonic_is_monotone`), **reliability on synthetic mis-scaled `z`** (`test_calibrator_bends_misscaled_z_toward_diagonal`: true P=z², Brier AND ECE improve), the **hit-label rule** (`test_hit_label_matches_drift_demeaned_forward_sign`), the **identity fallback** (unfitted/one-class → `predict_proba(z)=z`), and the reliability PNG write. The **"hit" label == the memory reward rule** — `_hit_label` returns `int(MemoryStore._reward(action, prices, t, config) > 0)`, so it is provably identical (uses `h` + `reward_drift_window`, μ point-in-time `≤ t`).
- [x] **Gate:** `make check` green (lint + typecheck + 89 unit + e2e); `check-lookahead` audit clean (the forward-looking `_hit_label` is the FROZEN training label, never a day-t input; warm-up emits no PnL).
- [x] **features.json:** `F15` → `passing` with evidence (test command + date, ADR-019).
- [x] **Artifacts (produced by the LIVE `--mode warmup`):** `results/calibrator.pkl`, `results/reliability_diagram.png`, `results/calibration_report.json` (method, n, per-bin counts, Brier, ECE), diagnostic `results/warmup_pairs.csv`. **Warm-up FAISS index persistence is now DONE (A2, ADR-023)** — `collect_warmup_pairs` calls `MemoryStore.save()` → `data/{ticker}_memory/`, and `Backtester.run` warm-starts via `store.load()` (online only), so the test inherits the warmed memory. The calibrator is frozen to `calibrator.pkl` (that is F15).
- [x] **Rules:** calibrate **ONLY on 2022–2024 warm-up** and **FREEZE** `calibrator.pkl` before any test-window run; **NEVER report warm-up PnL** (no PnL artifact emitted — only `warmup_pairs.csv` + the frozen calibrator); all thresholds/windows are numbers in `config.py`. Offline always uses raw z (hermetic); warm-up builds the graph with `calibrator=None` so the collected `z` is RAW.
- [ ] **Threshold priors validated here too:** the re-tuned hysteresis/veto **priors** (`tau_enter 0.60`, `tau_flip 0.70`, `vol_cap 0.50` — see S32 amendment) were set from *diagnosing* the 2025–2026 test window, so they must be **confirmed on this warm-up and frozen** alongside the calibrator before the test run. Calibration only makes the taus *meaningful* (z→P(correct)); it does not move them — any threshold tuning is a separate warm-up-only step (spec §7.2, stretch). **Never tune a threshold to improve the test-window curve** (look-ahead on the eval set, guiding-principle #1).
- [x] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` **ADR-019** records the isotonic-vs-Platt fallback threshold, the `hit=reward>0` reuse, the hermetic calibrator wiring, and the deferred FAISS persistence.
