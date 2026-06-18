"""DebateAgent (spec §5.5) — state-aware Bull/Bear fusion.

Fuses NewsSignal + MacroSignal + TechnicalSignal + MemoryContext + PortfolioState
via a mandatory Bull/Bear debate, considering the CURRENT position, to recommend
hold/open/close/flip. Output: ResearchStance.

System prompt (4 steps): (1) strongest Bull case, (2) strongest Bear case,
(3) is the original thesis STILL valid?, (4) recommend action + conviction. "If a
position is held and the thesis still holds, prefer HOLD unless clear contradicting
evidence" — forces defense of the held position, avoiding flips on noise.

For §7.3 self-consistency, this agent is run K times at temperature>0; the raw
LLM conviction is replaced by the calibrated number computed in eval/calibration.
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    PortfolioState,
    ResearchStance,
    TechnicalSignal,
)


class DebateAgent(BaseAgent):
    def _build_chain(self):
        raise NotImplementedError("M2: ChatPromptTemplate | llm.with_structured_output(ResearchStance)")

    def run(  # type: ignore[override]
        self,
        obs: Observation,
        state: PortfolioState,
        news: NewsSignal,
        macro: MacroSignal,
        technical: TechnicalSignal,
        memory: MemoryContext,
    ) -> ResearchStance:
        raise NotImplementedError("M2")
