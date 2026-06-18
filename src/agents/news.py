"""NewsAgent (spec §5.1) — idiosyncratic / AAPL-specific channel.

Reads the day's AAPL news (title + summary, relevance-filtered), extracts
sentiment/events, proposes a signal. Output: NewsSignal.

System prompt: "You are a news analyst for {ticker}. Rely ONLY on the provided
news, do not use outside knowledge or events after the news date. Return signal,
confidence (0-1), sentiment (-1..1), reason <=2 sentences. Do not infer based on
anything you know about the future."
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import NewsSignal, PortfolioState


class NewsAgent(BaseAgent):
    def _build_chain(self):
        raise NotImplementedError("M2: ChatPromptTemplate | llm.with_structured_output(NewsSignal)")

    def run(self, obs: Observation, state: PortfolioState) -> NewsSignal:
        raise NotImplementedError("M2")
