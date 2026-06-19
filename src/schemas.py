"""A2A message contracts (spec §4.3).

Every agent communicates ONLY through these fixed Pydantic schemas — never free
text. This turns agent dialogue into a structured, testable, ablatable protocol.
Each agent is built as `prompt | llm.with_structured_output(Schema)`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PortfolioState(BaseModel):
    """State carried across days by the LangGraph loop."""

    current_position: Literal[-1, 0, 1] = 0
    active_thesis: str = ""               # reason for entry; empty if flat
    entry_price: float | None = None
    days_held: int = 0


class NewsSignal(BaseModel):
    """NewsAgent — idiosyncratic / AAPL-specific channel.

    `rationale` is first so the model REASONS before it commits (schema order =
    generation order; spec §5, PLAN fix #4)."""

    rationale: str
    sentiment: float = Field(ge=-1.0, le=1.0)
    signal: Literal["long", "flat", "short"]
    confidence: float = Field(ge=0.0, le=1.0)


class MacroSignal(BaseModel):
    """MacroAgent — systematic / macro channel (routes to risk veto).

    `rationale` first (reason-first generation; PLAN fix #4)."""

    rationale: str
    regime: Literal["risk_on", "neutral", "risk_off"]
    macro_risk: float = Field(ge=0.0, le=1.0)   # today's systematic risk level
    drivers: list[str]                          # e.g. ["Fed meeting", "Iran tensions"]


class TechnicalSignal(BaseModel):
    """TechnicalAgent — interprets precomputed indicators (no number-crunching).

    `rationale` first (reason-first generation; PLAN fix #4)."""

    rationale: str
    signal: Literal["long", "flat", "short"]
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: dict


class MemoryContext(BaseModel):
    """MemoryAgent — experience retrieved from FAISS."""

    analogs: list[str]                          # k similar past situations + outcomes
    lesson: str


class ResearchStance(BaseModel):
    """DebateAgent — decision RELATIVE to the current position.

    Reason-first order (PLAN fix #4): the bull/bear/thesis REASONING is generated
    before the model commits to an action/conviction (schema order = generation order).
    `conviction` here is the LLM's self-report — ONE input to the conviction math, never
    the decision number (spec §7.3)."""

    bull_case: str
    bear_case: str
    thesis_still_valid: bool
    action: Literal["hold", "open", "close", "flip"]
    target_direction: Literal[-1, 0, 1]
    conviction: float = Field(ge=0.0, le=1.0)


class TradeDecision(BaseModel):
    """PositionManager — final position transition for session t+1."""

    new_position: Literal[-1, 0, 1]
    new_thesis: str                             # updated on open/flip
    vetoed: bool = False
    reason: str
