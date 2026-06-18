"""TechnicalAgent (spec §5.3) — interprets precomputed indicators.

Indicators are computed deterministically with `ta`/pandas in the data layer
(RSI14, MACD, MA20/50, 20d vol, momentum) — the LLM only INTERPRETS them, never
crunches numbers (avoids hallucination, ensures reproducibility). Output:
TechnicalSignal.

System prompt: "You are a technical analyst. Below are the precomputed indicators
for {ticker} up to day {t}. Do NOT make up numbers; only interpret them."
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import PortfolioState, TechnicalSignal


class TechnicalAgent(BaseAgent):
    def _build_chain(self):
        raise NotImplementedError("M2: ChatPromptTemplate | llm.with_structured_output(TechnicalSignal)")

    def run(self, obs: Observation, state: PortfolioState) -> TechnicalSignal:
        raise NotImplementedError("M2")
