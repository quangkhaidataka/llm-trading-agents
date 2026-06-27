"""S23 tests — the conviction engine (Layers 1-2; Layer 3 = Step 5).

Pure, deterministic math: the decision number is COMPUTED from measurable signals +
self-consistency, never the LLM's self-report (spec §7.3). Weights/blend from config.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import Config
from src.eval.calibration import (
    Calibrator,
    _hit_label,
    _reliability_stats,
    composite_conviction,
    fit_calibrator,
    raw_conviction,
    reliability_diagram,
    self_consistency_conviction,
)


def test_composite_conviction_blends_weighted_signals() -> None:
    cfg = Config()  # w1=0.4, w2=0.3, w3=0.3
    signals = [
        {"direction": 1, "confidence": 0.8},
        {"direction": 1, "confidence": 0.6},
        {"direction": -1, "confidence": 0.2},
    ]
    # agreement = |0.8 + 0.6 - 0.2| / (0.8 + 0.6 + 0.2) = 1.2 / 1.6 = 0.75
    # mean_confidence = 1.6 / 3 ; memory_consistency = 0.5
    expected = cfg.w1 * 0.75 + cfg.w2 * (1.6 / 3) + cfg.w3 * 0.5
    assert composite_conviction(signals, 0.5, cfg) == pytest.approx(expected)


def test_composite_conviction_abstention_does_not_dilute_lone_short() -> None:
    """Gate-B (ADR-017): a flat (abstaining) agent must NOT dilute a confident directional minority.

    News abstains (flat), Technical is confidently short → the agreement denominator counts only the
    directional voter, so a lone short reaches FULL agreement (1.0) instead of the old diluted 0.545.
    """
    cfg = Config()  # w1=0.4, w2=0.3, w3=0.3; tau_enter=0.60, alpha=beta=0.5
    signals = [
        {"direction": 0, "confidence": 0.5},   # news abstains (flat)
        {"direction": -1, "confidence": 0.6},  # technical: confident short
    ]
    # NEW agreement = |0*0.5 + (-1)*0.6| / 0.6 (directional only) = 1.0   (OLD was 0.6/1.1 = 0.545)
    mean_confidence = (0.5 + 0.6) / 2
    expected = cfg.w1 * 1.0 + cfg.w2 * mean_confidence + cfg.w3 * 0.5
    composite = composite_conviction(signals, 0.5, cfg)
    assert composite == pytest.approx(expected)
    # with a self-consistent short debate (sc=1.0), z clears tau_enter — the lone short can now open.
    z = raw_conviction(composite, 1.0, cfg)
    assert z >= cfg.tau_enter


def test_composite_conviction_zero_confidence_guard() -> None:
    cfg = Config()
    signals = [
        {"direction": 1, "confidence": 0.0},
        {"direction": -1, "confidence": 0.0},
    ]
    # Σc == 0 → agreement 0, mean 0; memory 0 → overall 0 (no divide-by-zero).
    assert composite_conviction(signals, 0.0, cfg) == pytest.approx(0.0)


def test_self_consistency_conviction_majority_frequency() -> None:
    actions = ["open", "open", "open", "hold", "open"]
    assert self_consistency_conviction(actions, 5) == pytest.approx(0.8)


def test_self_consistency_conviction_empty_guard() -> None:
    assert self_consistency_conviction([], 0) == 0.0


def test_raw_conviction_blends_layers() -> None:
    cfg = Config()  # alpha=0.5, beta=0.5
    assert raw_conviction(0.6, 0.8, cfg) == pytest.approx(cfg.alpha * 0.6 + cfg.beta * 0.8)


# ── Layer 3: the calibrator (S5.1) ────────────────────────────────────────────
def test_calibrator_isotonic_is_monotone() -> None:
    """Isotonic predict_proba must be non-decreasing in z (and stay in [0,1])."""
    rng = np.random.default_rng(0)
    z = np.linspace(0.0, 1.0, 400)
    hits = (rng.random(400) < z).astype(int)  # P(hit) = z
    cal = Calibrator("isotonic").fit(z, hits)
    probs = [cal.predict_proba(v) for v in (0.1, 0.3, 0.5, 0.7, 0.9)]
    assert all(probs[i] <= probs[i + 1] + 1e-9 for i in range(len(probs) - 1))
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_calibrator_bends_misscaled_z_toward_diagonal() -> None:
    """A known mis-scaled z (raw z overstates: true P = z²) is bent toward the diagonal —
    Brier AND ECE improve post-fit."""
    rng = np.random.default_rng(1)
    z = rng.uniform(0.0, 1.0, 2000)
    hits = (rng.random(2000) < z**2).astype(int)
    cal = fit_calibrator(z, hits, method="isotonic", config=Config())
    raw = _reliability_stats(z, hits, 10)
    calibrated = _reliability_stats([cal.predict_proba(v) for v in z], hits, 10)
    assert calibrated["brier"] < raw["brier"]
    assert calibrated["ece"] < raw["ece"]


def test_calibrator_identity_when_unfitted_or_one_class() -> None:
    """Graceful fallback: an unfitted calibrator (and one-class warm-up data) → predict_proba is
    the identity, so the PositionManager degrades to raw z when nothing is frozen."""
    assert Calibrator("isotonic").predict_proba(0.42) == pytest.approx(0.42)
    one_class = fit_calibrator([0.2, 0.5, 0.8], [1, 1, 1], config=Config())
    assert one_class.predict_proba(0.3) == pytest.approx(0.3)


def test_hit_label_matches_drift_demeaned_forward_sign() -> None:
    """hit = sign(action) matches sign(forward_return − μ) — identical rule to the memory reward.
    Flat closes (μ≈0) then a clear up-move → long hits, short misses, flat is no bet."""
    cfg = Config()  # h=5
    closes = [100.0] * 8 + [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    prices = pd.DataFrame({"close": closes}, index=idx)
    t = idx[7].date()  # pos 7; forward window 7+1+5 = 13 < 15
    assert _hit_label(1, prices, t, cfg) == 1   # long into a rise beyond drift → hit
    assert _hit_label(-1, prices, t, cfg) == 0  # short into a rise → miss
    assert _hit_label(0, prices, t, cfg) == 0   # flat → no directional bet


def test_reliability_diagram_writes_png(tmp_path) -> None:
    z = list(np.linspace(0.0, 1.0, 50))
    hits = [int(v > 0.5) for v in z]
    cal = Calibrator("isotonic").fit(z, hits)
    out = tmp_path / "rel.png"
    reliability_diagram(cal, z, hits, str(out), 10)
    assert out.exists() and out.stat().st_size > 0
