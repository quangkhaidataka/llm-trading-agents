"""NewsAgent (spec §5.1) — idiosyncratic / AAPL-specific channel.

Reads the day's AAPL news (already relevance-filtered, newest-first) and judges
SURPRISE vs priced-in: sentiment is the raw tone, signal is the trading implication
(which may differ). Output: NewsSignal. On a no-news day it short-circuits to a flat,
no-edge signal without calling the LLM (nothing to reason about).
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.prompts import CONFIDENCE_RUBRIC, NEWS_HUMAN, NEWS_SYSTEM
from src.data.loaders import Observation
from src.schemas import NewsSignal, PortfolioState


class NewsAgent(BaseAgent):
    """Idiosyncratic AAPL-news analyst: surprise vs priced-in, tone vs trading signal."""

    def _build_chain(self):
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [("system", NEWS_SYSTEM), ("human", NEWS_HUMAN)]
        ).partial(CONFIDENCE_RUBRIC=CONFIDENCE_RUBRIC)
        return prompt | self.llm.with_structured_output(NewsSignal)

    def run(self, obs: Observation, state: PortfolioState) -> NewsSignal:
        if not obs.has_news():
            return NewsSignal(
                rationale="No relevant AAPL news today; no idiosyncratic edge.",
                sentiment=0.0,
                signal="flat",
                confidence=self.config.no_news_confidence,
            )
        return self.chain.invoke(
            {
                "ticker": self.config.ticker,
                "t": obs.t.isoformat(),
                "news": obs.render_news(),
            }
        )
