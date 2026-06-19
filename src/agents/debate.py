"""DebateAgent (spec §5.5) — state-aware Bull/Bear fusion.

Fuses NewsSignal + MacroSignal + TechnicalSignal + MemoryContext + PortfolioState
via a mandatory four-step Bull/Bear debate, RELATIVE to the current position, to
recommend hold/open/close/flip. Output: ResearchStance.

Continuity bias lives in the PROMPT ("prefer HOLD unless clear contradicting
evidence") — not in code; the deterministic hysteresis is the PositionManager's job
(S3). The stance's self-reported `conviction` is NOT trusted: it is one input to the
conviction math (eval/calibration.py), never the decision number (spec §7.3).

`run` invokes once at temperature=0 (reproducible). `sample` invokes K times at
config.debate_temperature (>0) for Layer-2 self-consistency; offline the variation
comes from the MockLLM's seeded response cycling.
"""

from __future__ import annotations

from dataclasses import replace

from src.agents.base import BaseAgent
from src.agents.prompts import DEBATE_HUMAN, DEBATE_SYSTEM
from src.data.loaders import Observation
from src.llm import make_llm
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    PortfolioState,
    ResearchStance,
    TechnicalSignal,
)


class DebateAgent(BaseAgent):
    """State-aware Bull/Bear moderator → ResearchStance. Sampled K times for self-consistency."""

    def _build_chain(self):
        from langchain_core.prompts import ChatPromptTemplate

        self._prompt = ChatPromptTemplate.from_messages(
            [("system", DEBATE_SYSTEM), ("human", DEBATE_HUMAN)]
        )
        return self._prompt | self.llm.with_structured_output(ResearchStance)

    def _inputs(
        self,
        obs: Observation,
        state: PortfolioState,
        news: NewsSignal,
        macro: MacroSignal,
        technical: TechnicalSignal,
        memory: MemoryContext,
    ) -> dict:
        """Render the four signals + PortfolioState into the prompt variables."""
        return {
            "ticker": self.config.ticker,
            "t": obs.t.isoformat(),
            "current_position": state.current_position,
            "active_thesis": state.active_thesis or "(none)",
            "days_held": state.days_held,
            "news": (
                f"signal={news.signal} sentiment={news.sentiment:+.2f} "
                f"confidence={news.confidence:.2f} — {news.rationale}"
            ),
            "macro": (
                f"regime={macro.regime} macro_risk={macro.macro_risk:.2f} "
                f"drivers={macro.drivers} — {macro.rationale}"
            ),
            "technical": (
                f"signal={technical.signal} confidence={technical.confidence:.2f} "
                f"— {technical.rationale}"
            ),
            "memory": f"analogs={memory.analogs} lesson={memory.lesson}",
        }

    def run(  # type: ignore[override]
        self,
        obs: Observation,
        state: PortfolioState,
        news: NewsSignal,
        macro: MacroSignal,
        technical: TechnicalSignal,
        memory: MemoryContext,
    ) -> ResearchStance:
        return self.chain.invoke(self._inputs(obs, state, news, macro, technical, memory))

    def sample(
        self,
        obs: Observation,
        state: PortfolioState,
        news: NewsSignal,
        macro: MacroSignal,
        technical: TechnicalSignal,
        memory: MemoryContext,
        k: int,
    ) -> list[str]:
        """Invoke the chain k times at temperature>0 and return the recommended `action`s —
        the input to self_consistency_conviction. A fresh sampling chain per call keeps the
        offline (MockLLM) cycling deterministic; online, config.debate_temperature drives it."""
        sample_llm = make_llm(replace(self.config, temperature=self.config.debate_temperature))
        chain = self._prompt | sample_llm.with_structured_output(ResearchStance)
        inputs = self._inputs(obs, state, news, macro, technical, memory)
        return [chain.invoke(inputs).action for _ in range(k)]
