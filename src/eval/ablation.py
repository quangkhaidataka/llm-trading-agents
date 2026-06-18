"""Baselines + ablations + model-sensitivity (spec §8).

Baselines:
  1. Buy & Hold AAPL
  2. Single-agent (NewsAgent only)
  3. Pure AV-sentiment (trade on ticker_sentiment_score) — the baseline to BEAT

Ablations (each toggled via a Config variant, not code edits):
  - Full vs stateless daily classifier (remove PortfolioState + hysteresis)
  - Full vs no-memory (the central ablation)
  - Full vs no-macro (remove MacroAgent)
  - Full vs no-debate (remove Bull/Bear)
  - Full vs no-hysteresis (keep state but tau_enter == tau_exit)

Model-sensitivity: re-run on llama-3.3-70b vs gpt-4o-mini (both cutoffs < 2025).
Stable results => value is in the protocol, not the model.

Metrics: cumulative return, Sharpe, Sortino, MaxDD, hit rate, turnover, avg
holding period; plus corr(LLM sentiment, AV score).
"""

from __future__ import annotations

from config import Config


def run_ablations(base_config: Config) -> dict:
    """Run each baseline/ablation variant and return a comparison table."""
    raise NotImplementedError("M5")
