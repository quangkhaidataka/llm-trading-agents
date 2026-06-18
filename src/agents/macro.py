"""MacroAgent (spec §5.2) — systematic / macro channel.

Reads macro news (fetched BY TOPIC, not ticker) + SPY trend; assesses the regime
and systematic risk — the beta channel the NewsAgent misses. Output: MacroSignal.
Routes to the DebateAgent (context) AND the PositionManager (risk-off veto).

System prompt: "You are a macro strategist. Based on macro news + market context
up to day {t}, assess risk-on/neutral/risk-off and systematic risk (0-1). State
the main drivers (Fed, rates, geopolitics). Do NOT form a view on AAPL here."
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState


class MacroAgent(BaseAgent):
    def _build_chain(self):
        raise NotImplementedError("M2: ChatPromptTemplate | llm.with_structured_output(MacroSignal)")

    def run(self, obs: Observation, state: PortfolioState) -> MacroSignal:
        raise NotImplementedError("M2")
