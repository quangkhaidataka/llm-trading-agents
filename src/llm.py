"""LLM factory — the ONE place a model is instantiated (spec §12.2, §13.6, RQ4).

Going offline (MockLLM) or swapping the live backbone happens here in one line; the
rest of the system never knows which it got. Callers only ever do
`make_llm(config).with_structured_output(Schema)`. Online backbones are selected by
`config.provider`: "openrouter" (pay-as-you-go, OpenAI-compatible) or "groq". Both serve
the SAME Llama 3.3 70B (Dec-2023 cutoff → the anti-lookahead claim holds either way).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
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


class _LLMCache:
    """Process-wide PERSISTENT cache of structured LLM outputs (spec §6, §12.6).

    Key = sha256(rendered prompt messages + schema name + temperature). Because the key IS the
    exact rendered prompt (which already encodes ticker/date/news/upstream signals AND the prompt
    template text), a cache hit can only ever return the response for that identical point-in-time
    input — so reruns/ablations/sweeps cost no API calls, and changing a prompt (e.g. the debate
    prompt) MISSES correctly instead of replaying a stale answer. Stored as append-only JSONL
    (O(1) writes, crash-safe). Per key we keep a LIST replayed in call order, so the DebateAgent's
    K self-consistency samples (same prompt, K varied draws) are cached + reproduced faithfully."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.store: dict[str, list[dict]] = {}
        self.counter: dict[str, int] = {}
        self.lock = threading.Lock()
        if os.path.exists(path):
            with open(path) as fh:
                for line in fh:
                    if line.strip():
                        rec = json.loads(line)
                        self.store.setdefault(rec["key"], []).append(rec["payload"])

    @staticmethod
    def key(prompt_value: Any, schema: type, temperature: float) -> str:
        msgs = prompt_value.to_messages() if hasattr(prompt_value, "to_messages") else prompt_value
        if isinstance(msgs, list):
            text = "\n".join(f"{getattr(m, 'type', '?')}:{getattr(m, 'content', m)}" for m in msgs)
        else:
            text = str(msgs)
        raw = f"{schema.__name__}|{temperature}|{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_or_compute(self, key: str, compute) -> dict:
        """Return the next cached payload for `key` (by call order), else compute it, append, and
        persist. The expensive compute runs OUTSIDE the lock."""
        with self.lock:
            n = self.counter.get(key, 0)
            self.counter[key] = n + 1
            pool = self.store.get(key)
            if pool is not None and n < len(pool):
                return pool[n]  # hit
        payload = compute().model_dump()  # miss — real LLM call (slow), not under the lock
        with self.lock:
            self.store.setdefault(key, []).append(payload)
            with open(self.path, "a") as fh:
                fh.write(json.dumps({"key": key, "payload": payload}) + "\n")
        return payload


class _CachingStructured:
    """Wraps an inner structured-output runnable; consults the cache around `.invoke`."""

    def __init__(self, inner: Any, schema: type, cache: _LLMCache, temperature: float) -> None:
        self._inner = inner
        self._schema = schema
        self._cache = cache
        self._temp = temperature

    def invoke(self, prompt_value: Any, **kwargs: Any) -> Any:
        key = self._cache.key(prompt_value, self._schema, self._temp)
        payload = self._cache.get_or_compute(key, lambda: self._inner.invoke(prompt_value, **kwargs))
        return self._schema(**payload)

    def __call__(self, prompt_value: Any) -> Any:
        return self.invoke(prompt_value)


class _CachingLLM:
    """Transparent caching layer over an online backbone — same `with_structured_output(Schema)`
    contract, so no agent code changes (the cache lives only at this seam)."""

    def __init__(self, inner: Any, cache: _LLMCache, temperature: float) -> None:
        self._inner = inner
        self._cache = cache
        self._temp = float(temperature)

    def with_structured_output(self, schema: type, **kwargs: Any) -> _CachingStructured:
        return _CachingStructured(
            self._inner.with_structured_output(schema, **kwargs), schema, self._cache, self._temp
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


_CACHES: dict[str, _LLMCache] = {}


def _get_cache(path: str) -> _LLMCache:
    """One shared cache per file path (so every agent + the debate K-samples share one budget)."""
    if path not in _CACHES:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _CACHES[path] = _LLMCache(path)
    return _CACHES[path]


def _maybe_cache(inner: Any, config: Config) -> Any:
    """Wrap an online backbone in the persistent prompt-hash cache when enabled."""
    if not config.use_llm_cache:
        return inner
    return _CachingLLM(inner, _get_cache(config.llm_cache_path()), config.temperature)


def make_llm(config: Config):
    """Return MockLLM (offline) or the online backbone chosen by config.provider.

    The single instantiation seam: callers only ever do
    `make_llm(config).with_structured_output(Schema)`. Online backbones are wrapped in a persistent
    prompt-hash cache (`config.use_llm_cache`) so reruns cost no API calls."""
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
        return _maybe_cache(_StructuredJSON(
            ChatOpenAI(
                model=config.openrouter_model,
                temperature=config.temperature,
                api_key=SecretStr(config.openrouter_api_key),
                base_url=config.openrouter_base_url,
                max_retries=config.openrouter_max_retries,
                timeout=config.llm_timeout,  # stalled call fails → retried (never hangs the run)
                rate_limiter=_shared_rate_limiter(config.openrouter_requests_per_second),
                extra_body=extra_body,
            ),
            parse_retries=config.llm_parse_retries,
        ), config)

    if config.provider == "groq":
        from langchain_groq import ChatGroq  # import kept function-local
        from pydantic import SecretStr

        # Client-side throttle + retries so a live run survives Groq's per-minute token cap
        # (free tier ~12k TPM) instead of crashing on the first 429.
        return _maybe_cache(_StructuredJSON(
            ChatGroq(
                model=config.model_id,
                temperature=config.temperature,
                api_key=SecretStr(config.groq_api_key),
                max_retries=config.groq_max_retries,
                timeout=config.llm_timeout,  # stalled call fails → retried (never hangs the run)
                rate_limiter=_shared_rate_limiter(config.groq_requests_per_second),
            ),
            parse_retries=config.llm_parse_retries,
        ), config)

    raise ValueError(f"unknown provider: {config.provider}")
