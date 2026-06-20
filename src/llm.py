"""LLM factory — the ONE place a model is instantiated (spec §12.2, §13.6, RQ4).

Going offline (MockLLM) or swapping the live backbone happens here in one line; the
rest of the system never knows which it got. Callers only ever do
`make_llm(config).with_structured_output(Schema)`. Online backbones are selected by
`config.provider`: "openrouter" (pay-as-you-go, OpenAI-compatible) or "groq". Both serve
the SAME Llama 3.3 70B (Dec-2023 cutoff → the anti-lookahead claim holds either way).
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


class _StructuredJSON:
    """Provider-agnostic robust `with_structured_output(Schema)` for any OpenAI-compatible
    chat model (ChatGroq / ChatOpenAI→OpenRouter).

    LLMs (esp. Groq's Llama tool-calling) often emit numeric/boolean fields as STRINGS
    (`"conviction": "0.6"`, `"target_direction": "1"`, `"thesis_still_valid": "false"`) and
    strict server-side validation then rejects the call. We instead use JSON mode + a
    client-side PydanticOutputParser, which COERCES those strings to the schema's types.
    The Schema contract and every agent's `prompt | llm.with_structured_output(Schema)`
    stay identical — the fix lives only here, the single model seam (spec §12.2)."""

    def __init__(self, llm: Any, parse_retries: int = 4) -> None:
        self._llm = llm
        self._parse_retries = parse_retries

    def with_structured_output(self, schema: type, **_kwargs: Any) -> Any:
        from langchain_core.messages import HumanMessage
        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_core.runnables import RunnableLambda

        parser: Any = PydanticOutputParser(pydantic_object=schema)
        instructions = parser.get_format_instructions()  # includes the JSON schema + "json"
        fmt = {"type": "json_object"}

        def _invoke(prompt_value: Any) -> Any:
            base = list(prompt_value.to_messages()) + [HumanMessage(content=instructions)]
            messages = base
            last_err: Exception | None = None
            for attempt in range(self._parse_retries):
                # A live provider occasionally returns empty / non-schema content; re-ask with a
                # nudge (and a small temperature bump after the first retries to break a stuck
                # deterministic generation) so one bad reply can't kill a long backtest.
                llm = self._llm.bind(response_format=fmt, temperature=0.4) if attempt >= 2 \
                    else self._llm.bind(response_format=fmt)
                try:
                    return parser.parse(llm.invoke(messages).content)
                except Exception as e:  # noqa: BLE001 — retry any parse/transport failure
                    last_err = e
                    messages = base + [HumanMessage(
                        content="Your previous reply was not valid JSON matching the schema. "
                                "Reply with ONLY the JSON object, nothing else."
                    )]
            raise last_err  # type: ignore[misc]

        return RunnableLambda(_invoke)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


_RATE_LIMITER: Any = None


def _shared_rate_limiter(requests_per_second: float) -> Any:
    """Process-wide shared rate limiter so ALL agents throttle against one global budget
    (a per-agent limiter would let N agents collectively blow past the provider's TPM cap)."""
    global _RATE_LIMITER
    if _RATE_LIMITER is None:
        from langchain_core.rate_limiters import InMemoryRateLimiter

        _RATE_LIMITER = InMemoryRateLimiter(
            requests_per_second=requests_per_second,
            check_every_n_seconds=0.5,
            max_bucket_size=1,
        )
    return _RATE_LIMITER


def make_llm(config: Config):
    """Return MockLLM (offline) or the online backbone chosen by config.provider.

    The single instantiation seam: callers only ever do
    `make_llm(config).with_structured_output(Schema)`."""
    if config.offline:
        return MockLLM(seed=config.seed)

    if config.provider == "openrouter":
        from langchain_openai import ChatOpenAI  # import kept function-local
        from pydantic import SecretStr

        # Optionally pin ONE backend (reproducibility); "" = let OpenRouter route.
        extra_body: dict = {}
        if config.openrouter_provider:
            extra_body["provider"] = {
                "order": [config.openrouter_provider],
                "allow_fallbacks": False,
            }
        return _StructuredJSON(
            ChatOpenAI(
                model=config.openrouter_model,
                temperature=config.temperature,
                api_key=SecretStr(config.openrouter_api_key),
                base_url=config.openrouter_base_url,
                max_retries=config.openrouter_max_retries,
                rate_limiter=_shared_rate_limiter(config.openrouter_requests_per_second),
                extra_body=extra_body,
            ),
            parse_retries=config.llm_parse_retries,
        )

    if config.provider == "groq":
        from langchain_groq import ChatGroq  # import kept function-local
        from pydantic import SecretStr

        # Client-side throttle + retries so a live run survives Groq's per-minute token cap
        # (free tier ~12k TPM) instead of crashing on the first 429.
        return _StructuredJSON(
            ChatGroq(
                model=config.model_id,
                temperature=config.temperature,
                api_key=SecretStr(config.groq_api_key),
                max_retries=config.groq_max_retries,
                rate_limiter=_shared_rate_limiter(config.groq_requests_per_second),
            ),
            parse_retries=config.llm_parse_retries,
        )

    raise ValueError(f"unknown provider: {config.provider}")
