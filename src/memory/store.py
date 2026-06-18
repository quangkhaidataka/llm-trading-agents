"""MemoryStore — FAISS wrapper with point-in-time write/retrieve (spec §7, §12.1).

Non-parametric "learning": the LLM is frozen; behavior changes only because the
retrieved memory changes. An episode is (state -> action -> outcome).

DELAYED WRITE (mandatory anti-leak, spec §7.1): the day-t episode is written only
at t+1+h (h=5), when the forward-return window closes. Retrieval pulls only
episodes whose outcome has closed (t+1+h <= current_t). Writing earlier = leakage.

Reward stored on each episode is the ABNORMAL forward return (spec §7.1):
  reward = sign(action) * (forward_return(t,h) - benchmark_return(t,h))
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config import Config
from src.data.loaders import Observation


@dataclass
class Episode:
    t: date
    state_text: str          # embedded text: news + market state at t
    action: int              # -1/0/1 taken
    reward: float | None     # abnormal forward return; None until window closes
    outcome_closed_t: date   # t+1+h — not retrievable before this date


class MemoryStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        # FAISS index + episode metadata initialized in M3.

    def stage(self, obs: Observation, action: int) -> None:
        """Record a pending episode at t; reward filled and indexed at t+1+h."""
        raise NotImplementedError("M3")

    def flush_due(self, current_t: date, price_series) -> None:
        """Compute rewards and write episodes whose window has closed by current_t."""
        raise NotImplementedError("M3")

    def retrieve(self, obs: Observation, k: int) -> list[Episode]:
        """Top-k similar CLOSED episodes (outcome_closed_t <= obs.t)."""
        raise NotImplementedError("M3")
