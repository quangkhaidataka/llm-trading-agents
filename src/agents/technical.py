"""TechnicalAgent (spec §5.3) — interprets precomputed indicators.

Indicators (RSI14, MACD, MA20/50, annualized 20d vol, momentum) are computed
deterministically with `ta`/pandas in the data layer — the LLM only INTERPRETS
them, never crunches numbers (avoids hallucination, ensures reproducibility). It
prefers CONFLUENCE over a single indicator. Output: TechnicalSignal.
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.prompts import CONFIDENCE_RUBRIC, TECH_HUMAN, TECH_SYSTEM
from src.data.loaders import Observation
from src.schemas import PortfolioState, TechnicalSignal


class TechnicalAgent(BaseAgent):
    """Indicator interpreter — interprets, never computes; prefers confluence."""

    def _build_chain(self):
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [("system", TECH_SYSTEM), ("human", TECH_HUMAN)]
        ).partial(CONFIDENCE_RUBRIC=CONFIDENCE_RUBRIC)
        return prompt | self.llm.with_structured_output(TechnicalSignal)

    def run(self, obs: Observation, state: PortfolioState) -> TechnicalSignal:
        return self.chain.invoke(
            {
                "ticker": self.config.ticker,
                "t": obs.t.isoformat(),
                "indicators": obs.render_indicators(),  # labeled text; n/a on warm-up
            }
        )
