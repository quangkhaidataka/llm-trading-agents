"""MemoryAgent (spec §5.4) — provides experience from the past.

Retrieves the top-k CLOSED episodes for day t from the shared MemoryStore (point-in-time;
only outcomes that have already closed) and summarizes them into one short lesson. Output:
MemoryContext. On a cold start (no precedents) it says so calmly — it never invents analogs.
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.prompts import MEMORY_HUMAN, MEMORY_SYSTEM
from src.data.loaders import Observation
from src.memory.store import MemoryStore
from src.schemas import MemoryContext, PortfolioState


class MemoryAgent(BaseAgent):
    """Wraps MemoryStore.retrieve + a short LLM 'lesson' summary into a MemoryContext."""

    def __init__(self, config, store: MemoryStore) -> None:
        self.store = store
        super().__init__(config)

    def _build_chain(self):
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [("system", MEMORY_SYSTEM), ("human", MEMORY_HUMAN)]
        )
        return prompt | self.llm.with_structured_output(MemoryContext)

    def run(self, obs: Observation, state: PortfolioState) -> MemoryContext:
        episodes = self.store.retrieve(obs, self.config.k)
        if not episodes:
            return MemoryContext(
                analogs=[],
                lesson="No comparable past episodes yet; deciding without precedent.",
            )
        analogs = "\n".join(
            f"- {ep.t.isoformat()}: action={ep.action:+d} realized_reward={ep.reward:+.4f}"
            for ep in episodes
        )
        return self.chain.invoke(
            {
                "ticker": self.config.ticker,
                "t": obs.t.isoformat(),
                "k": self.config.k,
                "analogs": analogs,
            }
        )
