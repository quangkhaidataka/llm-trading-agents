"""MacroAgent (spec §5.2) — systematic / macro channel.

Reads macro news (fetched BY TOPIC, never relevance-filtered) + SPY trend and
classifies the regime + systematic risk — the beta channel the NewsAgent misses.
By design it forms NO AAPL-specific view (channel hygiene): the MacroSignal schema
has no per-asset signal field. Output: MacroSignal. Routes to the DebateAgent
(context) AND the PositionManager (risk-off veto).
"""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.prompts import MACRO_HUMAN, MACRO_SYSTEM
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState


class MacroAgent(BaseAgent):
    """Systematic regime strategist — never forms an asset-specific (AAPL) view."""

    def _build_chain(self):
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [("system", MACRO_SYSTEM), ("human", MACRO_HUMAN)]
        )
        return prompt | self.llm.with_structured_output(MacroSignal)

    def run(self, obs: Observation, state: PortfolioState) -> MacroSignal:
        rate_chg = "n/a" if obs.rate_change is None else f"{obs.rate_change:+.3f}"
        return self.chain.invoke(
            {
                "ticker": self.config.ticker,
                "t": obs.t.isoformat(),
                "macro_headlines": obs.render_macro(),  # NEVER relevance-filtered
                "spy_trend": f"{obs.spy_trend:+.3f}",
                "rate_chg": rate_chg,
            }
        )
