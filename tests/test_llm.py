"""S21 tests — the make_llm factory + offline MockLLM parity.

All offline, deterministic, no keys/network: with Config(offline=True) the factory
returns a MockLLM whose with_structured_output(Schema) yields validated Pydantic
instances from fixtures, reproducibly, with a seeded action spread for S23.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from config import Config
from src.llm import MockLLM, _CachingLLM, _LLMCache, _maybe_cache, make_llm
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    ResearchStance,
    TechnicalSignal,
)


class _Toy(BaseModel):
    """Minimal schema for cache tests (round-trips via model_dump / **payload)."""

    n: int
    label: str


class _FakeInner:
    """Stand-in online backbone: counts REAL calls so a test can prove a cache hit means zero
    calls. Each call returns a fresh _Toy whose `n` is the call index, so replays are identifiable."""

    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema: type, **_kw: object):
        outer = self

        class _R:
            def invoke(self, _prompt: object, **_kwargs: object) -> object:
                outer.calls += 1
                return schema(n=outer.calls, label="x")

            __call__ = invoke

        return _R()


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


# ── LLM cache (spec §6, §12.6) ────────────────────────────────────────────────
def test_llm_cache_replays_across_runs_with_no_api_call(tmp_path) -> None:
    """The money saver: a SECOND run (fresh cache object loading the JSONL) serves the same prompt
    from disk with ZERO calls to the backbone, returning the identical payload."""
    path = str(tmp_path / "c.jsonl")
    cold = _FakeInner()
    out1 = _CachingLLM(cold, _LLMCache(path), 0.0).with_structured_output(_Toy).invoke("prompt-A")
    assert cold.calls == 1  # cold run pays once

    warm = _FakeInner()
    out2 = _CachingLLM(warm, _LLMCache(path), 0.0).with_structured_output(_Toy).invoke("prompt-A")
    assert warm.calls == 0  # warm run: served from disk, no API call
    assert out1.model_dump() == out2.model_dump()


def test_llm_cache_replays_k_samples_in_order(tmp_path) -> None:
    """K self-consistency samples (same prompt, K varied draws) are cached as an ordered list and
    replayed in the same order next run — so conviction stays reproducible AND free."""
    path = str(tmp_path / "c.jsonl")
    cold = _FakeInner()
    r1 = _CachingLLM(cold, _LLMCache(path), 0.7).with_structured_output(_Toy)
    first = [r1.invoke("same").n for _ in range(3)]
    assert cold.calls == 3 and first == [1, 2, 3]  # cold: 3 real varied draws

    warm = _FakeInner()
    r2 = _CachingLLM(warm, _LLMCache(path), 0.7).with_structured_output(_Toy)
    replay = [r2.invoke("same").n for _ in range(3)]
    assert warm.calls == 0 and replay == [1, 2, 3]  # warm: same 3, in order, no calls


def test_llm_cache_misses_on_changed_prompt(tmp_path) -> None:
    """Changing the prompt (e.g. the Gate-A debate prompt) MUST miss — never replay a stale answer."""
    path = str(tmp_path / "c.jsonl")
    _CachingLLM(_FakeInner(), _LLMCache(path), 0.0).with_structured_output(_Toy).invoke("v1")
    changed = _FakeInner()
    _CachingLLM(changed, _LLMCache(path), 0.0).with_structured_output(_Toy).invoke("v2")
    assert changed.calls == 1  # different prompt → different key → real call


def test_llm_cache_keys_separate_by_temperature(tmp_path) -> None:
    """run() (temp 0) and sample() (temp>0) share a prompt but must NOT share cache entries."""
    path = str(tmp_path / "c.jsonl")
    _CachingLLM(_FakeInner(), _LLMCache(path), 0.0).with_structured_output(_Toy).invoke("same")
    hot = _FakeInner()
    _CachingLLM(hot, _LLMCache(path), 0.7).with_structured_output(_Toy).invoke("same")
    assert hot.calls == 1  # same prompt, different temperature → different key → miss


def test_maybe_cache_respects_flag(tmp_path) -> None:
    inner = _FakeInner()
    assert _maybe_cache(inner, Config(use_llm_cache=False)) is inner  # opt-out → raw backbone
    wrapped = _maybe_cache(inner, Config(use_llm_cache=True, cache_dir=str(tmp_path)))
    assert isinstance(wrapped, _CachingLLM)
