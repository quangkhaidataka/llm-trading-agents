"""S23 tests — the conviction engine (Layers 1-2; Layer 3 = Step 5).

Pure, deterministic math: the decision number is COMPUTED from measurable signals +
self-consistency, never the LLM's self-report (spec §7.3). Weights/blend from config.
"""

from __future__ import annotations

import pytest

from config import Config
from src.eval.calibration import (
    composite_conviction,
    raw_conviction,
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
