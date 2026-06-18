"""LLM factory — the ONE place the model is instantiated (spec §12.2, §13.6).

Swapping provider (ChatGroq -> ChatOpenAI) or going offline (MockLLM) happens
here in one line; the rest of the system never knows which it got. Callers only
ever do `make_llm(config).with_structured_output(Schema)`.
"""

from __future__ import annotations

from config import Config


class MockLLM:
    """Offline stand-in: returns canned schema responses from fixtures.

    Used when config.offline=True so the pipeline + tests run with no API keys,
    no network, no cost, and deterministically (spec §13.6).
    """

    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}

    def with_structured_output(self, schema):
        raise NotImplementedError("M2: return a runnable yielding a canned `schema`")


def make_llm(config: Config):
    """Return MockLLM, ChatGroq, or ChatOpenAI depending on config."""
    if config.offline:
        return MockLLM()

    if config.provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=config.model_id,
            temperature=config.temperature,
            api_key=config.groq_api_key,
        )

    if config.provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=config.model_id, temperature=config.temperature)

    raise ValueError(f"unknown provider: {config.provider}")
