"""Conviction calibration (spec §7.3) — the decision number comes from MATH.

The LLM only supplies direction + reasoning; never trust its self-reported
confidence. Conviction is built in 3 layers and calibrated on 2022-2024:

  Layer 1 — composite from measurable signals:
    conviction_raw = w1*agreement + w2*mean_confidence + w3*memory_consistency
      agreement          = |sum_i s_i*c_i| / sum_i c_i      # direction s_i, confidence c_i
      mean_confidence    = mean_i c_i
      memory_consistency = #(analogs whose abnormal-return supports action) / k

  Layer 2 — self-consistency: run DebateAgent K times at temp>0,
    conviction_sc = #(majority action) / K

  Layer 3 — calibrate z = alpha*conviction_raw + beta*conviction_sc into a true
    probability via isotonic regression (or Platt scaling) on (z, hit) from the
    calibration set. Validate with a reliability diagram. Only then does
    tau_enter=0.7 truly mean "P(correct) >= 70%".
"""

from __future__ import annotations

import os
import pickle
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any

from config import Config


def composite_conviction(
    signals: list[dict], memory_consistency: float, config: Config
) -> float:
    """Layer 1 — blend measurable quantities into conviction_raw (0–1); NOT the LLM self-report.

    `signals` = the directional agent outputs, each {direction: -1|0|+1, confidence: 0..1}.
      agreement       = |Σ sᵢcᵢ| / Σ_{sᵢ≠0} cᵢ  (abstention-aware: directional agents only; guard → 0)
      mean_confidence = mean(cᵢ)                  (guard empty → 0)
    Folds in `memory_consistency` (share of retrieved analogs that supported the action).
    Returns w1·agreement + w2·mean_confidence + w3·memory_consistency (weights from config).

    Gate-B (ADR-017): the agreement denominator sums confidence over DIRECTIONAL agents only, so a
    flat vote is an abstention that neither reinforces nor dilutes — a confident lone short is no
    longer suppressed below tau_enter by an abstaining peer (the "never-shorts" fix)."""
    confidences = [float(s["confidence"]) for s in signals]
    # Numerator already ignores flat agents (sᵢ=0); the denominator must too — otherwise an
    # abstaining agent's confidence dilutes a confident directional minority.
    directional_conf = sum(float(s["confidence"]) for s in signals if float(s["direction"]) != 0)
    if directional_conf == 0:
        agreement = 0.0
    else:
        agreement = abs(sum(float(s["direction"]) * float(s["confidence"]) for s in signals)) / directional_conf
    mean_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0
    return (
        config.w1 * agreement
        + config.w2 * mean_confidence
        + config.w3 * memory_consistency
    )


def self_consistency_conviction(actions: list[str], K: int) -> float:
    """Layer 2 — turn a fuzzy judgment into a frequency.

    `actions` = the K actions the DebateAgent produced when asked the same question K times at
    temperature>0. Returns (count of the most common action) / K — high = stable/confident, low =
    wavering. Example: ['open','open','open','hold','open'] → 0.8. Guard K<=0 → 0."""
    if K <= 0 or not actions:
        return 0.0
    most_common_count = Counter(actions).most_common(1)[0][1]
    return most_common_count / K


def raw_conviction(conviction_raw: float, conviction_sc: float, config: Config) -> float:
    """Combine Layers 1 and 2 into the raw score z = alpha·conviction_raw + beta·conviction_sc
    (alpha, beta from config). z is a 0–1 score; it becomes a true probability only after the
    Step-5 calibrator maps it via P(correct | z)."""
    return config.alpha * conviction_raw + config.beta * conviction_sc


# ── Layer 3 — calibration on the 2022-2024 warm-up (S5.1) ─────────────────────


@dataclass
class WarmupPair:
    """One calibration datum: raw conviction z and whether the decision was correct."""

    t: date
    z: float           # alpha*conviction_raw + beta*conviction_sc  (raw, from raw_conviction)
    hit: int           # 1 if sign(action) == sign(drift-demeaned forward return), else 0


def _hit_label(direction: int, prices, t: date, config: Config) -> int:
    """hit = 1 if `direction` agrees with the drift-demeaned forward return, else 0.

    Grades a DIRECTIONAL VIEW (ADR-025): `direction` is the debate's `target_direction` — was the
    proposed up/down call correct? — NOT the executed position, so veto/hysteresis-forced flats don't
    mislabel a correct view as a miss. Same rule as the memory reward (`store._reward > 0`):
    reward = sign(direction)·(forward − μ) > 0 ⟺ sign(direction) == sign(forward − μ). μ is
    point-in-time (closes ≤ t). The caller skips no-view days (direction == 0) and ensures the
    t+1+h forward window exists in `prices`."""
    from src.memory.store import MemoryStore

    return int(MemoryStore._reward(direction, prices, t, config) > 0.0)


class Calibrator:
    """Wraps a fitted z -> P(correct) map (isotonic primary, Platt/logistic fallback).

    Unfitted (no warm-up data / one-class) → predict_proba is the identity (returns raw z),
    so the PositionManager degrades gracefully to raw conviction when no calibrator is frozen."""

    def __init__(self, method: str = "isotonic") -> None:
        self.method = method
        self._model: Any = None

    def fit(self, z_values, hits) -> Calibrator:
        """Fit the monotone map on warm-up (z, hit) pairs. Returns self."""
        import numpy as np

        z = np.asarray(z_values, dtype=float)
        y = np.asarray(hits, dtype=float)
        if self.method == "platt":
            from sklearn.linear_model import LogisticRegression

            self._model = LogisticRegression().fit(z.reshape(-1, 1), y)
        else:
            from sklearn.isotonic import IsotonicRegression

            self._model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(z, y)
        return self

    def predict_proba(self, z: float) -> float:
        """Map a raw conviction z to a calibrated probability of being correct (0..1).
        Identity (returns z) when unfitted."""
        import numpy as np

        if self._model is None:
            return float(z)
        if self.method == "platt":
            return float(self._model.predict_proba(np.asarray([[z]], dtype=float))[0, 1])
        return float(np.clip(self._model.predict(np.asarray([z], dtype=float))[0], 0.0, 1.0))

    def save(self, path: str) -> None:
        """Pickle the fitted calibrator (frozen before the test window)."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @classmethod
    def load(cls, path: str) -> Calibrator:
        """Load a frozen calibrator; the PositionManager path uses it (fallback to raw z if absent)."""
        with open(path, "rb") as fh:
            return pickle.load(fh)


def fit_calibrator(z_values, hits, method: str = "isotonic", config: Config | None = None) -> Calibrator:
    """Build + fit a Calibrator on the 2022-2024 (z, hit) set; return it (z -> P(correct)).

    Isotonic primary; falls back to Platt (logistic) when the data is thin
    (< config.calibration_min_isotonic) to avoid isotonic overfitting. Returns an UNFITTED
    (identity) Calibrator when there is no usable data or only one class is present."""
    import numpy as np

    z = np.asarray(z_values, dtype=float)
    y = np.asarray(hits, dtype=int)
    if len(z) == 0 or len(set(y.tolist())) < 2:
        return Calibrator(method)  # cannot calibrate → identity predict_proba
    min_iso = config.calibration_min_isotonic if config is not None else 200
    chosen = "platt" if (method == "isotonic" and len(z) < min_iso) else method
    return Calibrator(chosen).fit(z, y)


def _reliability_stats(probs, hits, n_bins: int) -> dict:
    """Brier score, ECE, and per-bin (count, mean predicted, empirical hit-rate) over n_bins
    equal-width bins — shared by reliability_diagram and the calibration report."""
    import numpy as np

    p = np.asarray(probs, dtype=float)
    y = np.asarray(hits, dtype=float)
    n = len(p)
    if n == 0:
        return {"brier": 0.0, "ece": 0.0, "n_bins": n_bins, "bins": []}
    brier = float(np.mean((p - y) ** 2))
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict] = []
    ece = 0.0
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (p >= lo) & (p <= hi) if i == n_bins - 1 else (p >= lo) & (p < hi)
        cnt = int(mask.sum())
        if cnt:
            mean_pred = float(p[mask].mean())
            empirical = float(y[mask].mean())
            ece += (cnt / n) * abs(mean_pred - empirical)
            bins.append({"lo": lo, "hi": hi, "count": cnt,
                         "mean_pred": mean_pred, "empirical": empirical})
    return {"brier": brier, "ece": float(ece), "n_bins": n_bins, "bins": bins}


def reliability_diagram(calibrator: Calibrator, z_values, hits, out_path: str, n_bins: int) -> None:
    """Bin calibrated predicted vs empirical hit rate, plot against the diagonal, save the PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    probs = [calibrator.predict_proba(float(z)) for z in z_values]
    stats = _reliability_stats(probs, hits, n_bins)
    xs = [b["mean_pred"] for b in stats["bins"]]
    ys = [b["empirical"] for b in stats["bins"]]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="perfectly calibrated")
    ax.plot(xs, ys, "o-", color="C0", label=f"{calibrator.method} (n={len(probs)})")
    ax.set_xlabel("predicted P(correct)")
    ax.set_ylabel("empirical hit rate")
    ax.set_title(f"Reliability — Brier {stats['brier']:.3f}, ECE {stats['ece']:.3f}")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def collect_warmup_pairs(config: Config) -> list[WarmupPair]:
    """Replay the full pipeline over [warmup_start, warmup_end], populating memory (delayed write)
    and collecting (z, hit) pairs. NEVER computes or reports PnL (warm-up exists only to teach memory
    + the calibrator). Days whose t+1+h forward window does not close within the cache are skipped."""
    import pandas as pd

    from src.data.loaders import load_prices
    from src.graph.build_graph import build_graph, run_one_day
    from src.memory.store import MemoryStore
    from src.schemas import PortfolioState

    store = MemoryStore(config)
    app = build_graph(config, store, calibrator=None)  # warm-up fits the calibrator → use RAW z here
    full = load_prices(config.ticker, date.fromisoformat(config.warmup_end))
    window = full.loc[pd.Timestamp(config.warmup_start) : pd.Timestamp(config.warmup_end)]
    dates = [ts.date() for ts in window.index]
    n = len(full.index)

    portfolio = PortfolioState()
    pairs: list[WarmupPair] = []
    for t in dates:
        run_one_day(app, t, portfolio, store)  # mutates portfolio, stages/flushes memory, writes trace
        pos = full.index.get_loc(pd.Timestamp(t))
        if pos + 1 + config.h >= n:  # forward window not closed within the cache → no label
            continue
        z, target = _read_trace_fields(config, t)
        if target == 0:  # debate proposed NO directional view → not a calibration datum (ADR-025)
            continue
        hit = _hit_label(target, full, t, config)  # grade the proposed DIRECTION, not the executed action
        pairs.append(WarmupPair(t=t, z=z, hit=hit))
    store.save()  # persist the warmed FAISS memory so the test inherits it (ADR-019 follow-up)
    return pairs


def run_warmup_calibration(config: Config) -> Calibrator:
    """Orchestrate S5.1: collect_warmup_pairs -> fit_calibrator -> reliability_diagram -> save
    results/calibrator.pkl + calibration_report.json + warmup_pairs.csv. Returns the frozen
    Calibrator. Emits NO PnL artifact of any kind."""
    import csv
    import json

    pairs = collect_warmup_pairs(config)
    z = [p.z for p in pairs]
    hits = [p.hit for p in pairs]
    calibrator = fit_calibrator(z, hits, method="isotonic", config=config)

    out = config.results_dir
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "warmup_pairs.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "z", "hit"])
        for p in pairs:
            w.writerow([p.t.isoformat(), p.z, p.hit])

    report: dict = {"method": calibrator.method, "n_samples": len(pairs)}
    if pairs:
        report["brier_raw"] = _reliability_stats(z, hits, config.calibration_bins)["brier"]
        cal_stats = _reliability_stats([calibrator.predict_proba(v) for v in z], hits, config.calibration_bins)
        report.update({"brier": cal_stats["brier"], "ece": cal_stats["ece"], "bins": cal_stats["bins"]})
        reliability_diagram(calibrator, z, hits, os.path.join(out, "reliability_diagram.png"),
                            config.calibration_bins)

    calibrator.save(config.calibrator_path())
    with open(os.path.join(out, "calibration_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"[warmup] pairs={len(pairs)} method={calibrator.method} "
          f"brier_raw={report.get('brier_raw')} brier={report.get('brier')} "
          f"-> {config.calibrator_path()}")
    return calibrator


def _read_trace_fields(config: Config, t: date) -> tuple[float, int]:
    """Read (raw conviction z, debate target_direction) from the per-day trace the commit node wrote
    (same trace-reading pattern the backtester uses). (0.0, 0) if the trace is missing."""
    import json

    path = os.path.join(config.log_dir, f"{config.ticker}_{t.isoformat()}.json")
    if os.path.exists(path):
        with open(path) as fh:
            d = json.load(fh)
        return float(d.get("conviction", 0.0)), int((d.get("debate") or {}).get("target_direction", 0))
    return 0.0, 0
