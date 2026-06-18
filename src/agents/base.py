"""BaseAgent interface (spec §12.4).

Each agent is an LCEL runnable `prompt | llm.with_structured_output(Schema)`
(spec §12.2) — never hand-parse JSON. Subclasses wire their ChatPromptTemplate
and output schema; `run` injects the point-in-time Observation + PortfolioState.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from config import Config
from src.data.loaders import Observation
from src.llm import make_llm
from src.schemas import PortfolioState


class BaseAgent(ABC):
    def __init__(self, config: Config) -> None:
        self.config = config
        self.llm = make_llm(config)
        self.chain = self._build_chain()

    @abstractmethod
    def _build_chain(self):
        """Return the LCEL runnable: prompt | llm.with_structured_output(Schema)."""

    @abstractmethod
    def run(self, obs: Observation, state: PortfolioState):
        """Produce this agent's Pydantic signal for day obs.t."""
