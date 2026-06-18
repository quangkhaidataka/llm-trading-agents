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

from config import Config


def composite_conviction(signals, memory_consistency: float, config: Config) -> float:
    raise NotImplementedError("M5: Layer 1")


def self_consistency_conviction(actions: list[str], K: int) -> float:
    raise NotImplementedError("M5: Layer 2")


def fit_calibrator(z_values, hits):
    """Fit isotonic/Platt on the 2022-2024 set; return a z -> P(correct) map."""
    raise NotImplementedError("M5: Layer 3")


def reliability_diagram(calibrator, z_values, hits, out_path: str) -> None:
    raise NotImplementedError("M5: validation plot")
