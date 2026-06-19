"""LLM factory — the ONE place a model is instantiated (spec §12.2, §13.6).

Going offline (MockLLM) or swapping the live backbone happens here in one line; the
rest of the system never knows which it got. Callers only ever do
`make_llm(config).with_structured_output(Schema)`. Groq is the sole online backbone —
the project's budget is all-free, so there is no OpenAI path.
"""

from __future__ import annotations

import json
import os
from typing import Any

from config import Config, config


class _StructuredRunnable:
    """A tiny runnable returned by MockLLM.with_structured_output(Schema).

    Mimics LangChain's structured-output runnable: `.invoke(prompt_value)` returns a
    validated `schema` instance, so agents cannot tell offline from online.
    """

    def __init__(self, schema: type, responses: dict, seed: int) -> None:
        """Hold the target Pydantic schema, the canned response pool, and a seed counter."""
        self.schema = schema
        self.responses = responses
        self.seed = seed
        self._calls = 0

    def invoke(self, _input: Any) -> Any:
        """Look up canned data by `schema.__name__`, pick one (seeded index for variation),
        and return `schema(**data)` — a validated Pydantic instance."""
        pool = self.responses.get(self.schema.__name__)
        if not pool:
            raise KeyError(f"no canned MockLLM responses for {self.schema.__name__}")
        data = pool[(self.seed + self._calls) % len(pool)]
        self._calls += 1
        return self.schema(**data)

    # Callable so a LangChain prompt can pipe straight into it offline
    # (`prompt | runnable` coerces a plain callable to a RunnableLambda) — keeps
    # this class langchain-free while staying chain-composable. Mirrors ChatGroq's
    # structured-output runnable, which is itself invoked with the prompt value.
    def __call__(self, _input: Any) -> Any:
        return self.invoke(_input)


class MockLLM:
    """Offline stand-in: returns canned schema responses from fixtures.

    Used when config.offline=True so the pipeline + tests run with no API keys, no
    network, no cost, and deterministically (spec §13.6).
    """

    def __init__(self, responses: dict | None = None, seed: int = 42) -> None:
        """Load canned responses (from fixtures/llm_responses.json if none passed)."""
        self.seed = seed
        if responses is None:
            with open(os.path.join(config.fixtures_dir, "llm_responses.json")) as fh:
                responses = json.load(fh)
        self.responses = responses

    def with_structured_output(self, schema: type) -> _StructuredRunnable:
        """Return a runnable that yields validated `schema` instances from fixtures.

        Mirrors ChatGroq.with_structured_output so BaseAgent chains are backend-agnostic.
        Seeded variation across calls supports Layer-2 self-consistency offline."""
        return _StructuredRunnable(schema, self.responses, self.seed)


def make_llm(config: Config):
    """Return MockLLM (offline) or ChatGroq (online). Groq only — no OpenAI path.

    The single instantiation seam: callers only ever do
    `make_llm(config).with_structured_output(Schema)`."""
    if config.offline:
        return MockLLM(seed=config.seed)

    if config.provider == "groq":
        from langchain_groq import ChatGroq  # import kept function-local

        return ChatGroq(
            model=config.model_id,
            temperature=config.temperature,
            api_key=config.groq_api_key,
        )

    raise ValueError(f"unknown provider: {config.provider}")
