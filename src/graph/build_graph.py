"""LangGraph orchestration (spec §4.2, §12.2).

Wires the agents into a state machine and carries PortfolioState across days.

Per-day flow:
  get_observation(t)
    -> [NewsAgent, MacroAgent, TechnicalAgent, MemoryAgent]   (parallel)
    -> DebateAgent (state-aware)                              -> ResearchStance
    -> conviction = calibrate(...)                            (spec §7.3)
    -> PositionManager (hysteresis + veto)                    -> TradeDecision
    -> new_position applied to session t+1; update PortfolioState
    -> MemoryStore.stage(t); MemoryStore.flush_due(t)         (delayed write, h)
"""

from __future__ import annotations

from config import Config
from src.memory.store import MemoryStore


def build_graph(config: Config, store: MemoryStore):
    """Construct and compile the LangGraph app carrying PortfolioState."""
    raise NotImplementedError("M3: assemble nodes/edges and compile")
