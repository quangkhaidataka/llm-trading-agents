"""MemoryAgent (spec §5.4) — provides experience from the past.

Embeds (news + market state) for day t -> retrieves top-k most similar episodes
from FAISS (only episodes whose outcome has CLOSED, i.e. t+1+h <= t) -> summarizes
a lesson. Output: MemoryContext. Retrieval is point-in-time (see memory/store.py).

System prompt: "Below are {k} similar past situations with the action taken and
the ACTUAL outcome. Summarize a short lesson. Do not assume info after day {t}."
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.memory.store import MemoryStore
from src.schemas import MemoryContext, PortfolioState


class MemoryAgent(BaseAgent):
    def __init__(self, config, store: MemoryStore) -> None:
        self.store = store
        super().__init__(config)

    def _build_chain(self):
        raise NotImplementedError("M3: ChatPromptTemplate | llm.with_structured_output(MemoryContext)")

    def run(self, obs: Observation, state: PortfolioState) -> MemoryContext:
        raise NotImplementedError("M3: store.retrieve(obs, k) then summarize")
