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

from collections import Counter

from config import Config


def composite_conviction(
    signals: list[dict], memory_consistency: float, config: Config
) -> float:
    """Layer 1 — blend measurable quantities into conviction_raw (0–1); NOT the LLM self-report.

    `signals` = the directional agent outputs, each {direction: -1|0|+1, confidence: 0..1}.
      agreement       = |Σ sᵢcᵢ| / Σ cᵢ      (guard Σcᵢ==0 → 0)
      mean_confidence = mean(cᵢ)              (guard empty → 0)
    Folds in `memory_consistency` (share of retrieved analogs that supported the action).
    Returns w1·agreement + w2·mean_confidence + w3·memory_consistency (weights from config)."""
    confidences = [float(s["confidence"]) for s in signals]
    total_conf = sum(confidences)
    if total_conf == 0:
        agreement = 0.0
    else:
        agreement = abs(sum(float(s["direction"]) * float(s["confidence"]) for s in signals)) / total_conf
    mean_confidence = (total_conf / len(confidences)) if confidences else 0.0
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


def fit_calibrator(z_values, hits):
    """Fit isotonic/Platt on the 2022-2024 set; return a z -> P(correct) map."""
    raise NotImplementedError("M5: Layer 3")


def reliability_diagram(calibrator, z_values, hits, out_path: str) -> None:
    raise NotImplementedError("M5: validation plot")
