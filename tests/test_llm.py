"""S21 tests — the make_llm factory + offline MockLLM parity.

All offline, deterministic, no keys/network: with Config(offline=True) the factory
returns a MockLLM whose with_structured_output(Schema) yields validated Pydantic
instances from fixtures, reproducibly, with a seeded action spread for S23.
"""

from __future__ import annotations

import pytest

from config import Config
from src.llm import MockLLM, make_llm
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    ResearchStance,
    TechnicalSignal,
)


def test_make_llm_offline_returns_mockllm() -> None:
    assert isinstance(make_llm(Config(offline=True)), MockLLM)


@pytest.mark.parametrize(
    "schema", [NewsSignal, MacroSignal, TechnicalSignal, MemoryContext, ResearchStance]
)
def test_mockllm_returns_validated_schema(schema: type) -> None:
    out = make_llm(Config(offline=True)).with_structured_output(schema).invoke("ignored")
    assert isinstance(out, schema)  # a validated Pydantic instance, not raw text


def test_mockllm_is_deterministic_for_same_seed() -> None:
    a = make_llm(Config(offline=True)).with_structured_output(ResearchStance).invoke("x")
    b = make_llm(Config(offline=True)).with_structured_output(ResearchStance).invoke("x")
    assert a == b


def test_mockllm_action_spread_feeds_self_consistency() -> None:
    runnable = make_llm(Config(offline=True)).with_structured_output(ResearchStance)
    actions = {runnable.invoke("x").action for _ in range(6)}
    assert len(actions) > 1  # seeded variation across K calls (S23 self-consistency)


def test_mockllm_unknown_schema_fails_loud() -> None:
    class Unknown:  # no canned responses for this name
        pass

    with pytest.raises(KeyError):
        make_llm(Config(offline=True)).with_structured_output(Unknown).invoke("x")
