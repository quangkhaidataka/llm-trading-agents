# S2.1 — LLM Factory & MockLLM

> **Update (2026-06-20, ADR-015):** the "Groq-only online" decision below was widened — `make_llm` now
> also supports `provider="openrouter"` (ChatOpenAI → OpenRouter, the SAME Llama 3.3 70B, Dec-2023 cutoff)
> because Groq's Dev tier is unavailable and its free tier can't complete the backtest (ADR-014). Both
> backbones live behind one `config.provider` switch (spec §12.2 / RQ4 / F16); the structured-output
> wrapper is generalized to `_StructuredJSON`. The MockLLM/offline design below is unchanged.

## Objective
Before any agent can think, it needs something to think *with* — and we need that
something to be swappable, free to test, and honest about the fact that offline and
online must behave identically. This sub-step builds the one seam through which the
whole system touches a language model: `make_llm(config)`. Online, it hands back a
real `ChatGroq` client (Groq only — the project's budget is all-free, so there is no
OpenAI path); offline, it hands back a deterministic `MockLLM` that reads canned
answers from `fixtures/llm_responses.json`. The trick that makes the rest of the
codebase blissfully unaware of which brain it got is that *both* expose the exact same
`with_structured_output(Schema)` interface: you give it a Pydantic schema, you get back
a runnable whose `.invoke(...)` returns a validated instance of that schema. The MockLLM
goes one step further — it can produce *seeded variation* across repeated calls so the
Step-2 self-consistency machinery (asking the DebateAgent the same thing K times) has
something realistic to chew on offline, all without a single network call or API key.

## Inputs and Outputs
- **Inputs**
  - `config` (`src/llm.py` reads `config.offline`, `config.provider`, `config.model_id`,
    `config.temperature`, `config.groq_api_key`, `config.seed`).
  - `fixtures/llm_responses.json` — canned per-schema responses (a dict keyed by
    `Schema.__name__`, each value a list of response dicts to enable seeded variation).
  - The stubs in `src/llm.py` (`make_llm`, `MockLLM`).
- **Outputs**
  - Working `make_llm(config) -> ChatGroq | MockLLM` in `src/llm.py`.
  - `MockLLM.with_structured_output(Schema)` → a small runnable whose `.invoke()` returns
    a validated `Schema` instance (e.g. `NewsSignal`, `MacroSignal`, `TechnicalSignal`,
    `ResearchStance`, `MemoryContext`), drawn from the fixtures with seeded spread.
  - `tests/test_llm.py` — proves both backends honor the same contract; offline is
    deterministic and supports an action spread for self-consistency.
  - Fixture file: `fixtures/llm_responses.json` (created/extended here).

## Skeleton Python Code
```python
"""src/llm.py — LLM factory + offline MockLLM (Groq-only online)."""
from __future__ import annotations

from typing import Any

from config import Config


class _StructuredRunnable:
    """A tiny runnable returned by MockLLM.with_structured_output(Schema).

    Mimics LangChain's structured-output runnable: `.invoke(prompt_value)` returns a
    validated `schema` instance, so agents cannot tell offline from online.
    """

    def __init__(self, schema: type, responses: dict, seed: int) -> None:
        """Hold the target Pydantic schema, the canned response pool, and a seed counter."""
        ...

    def invoke(self, _input: Any) -> Any:
        """Look up canned data by `schema.__name__`, pick one (seeded index for variation),
        and return `schema(**data)` — a validated Pydantic instance."""
        ...


class MockLLM:
    """Offline stand-in: returns canned schema responses from fixtures.

    Used when config.offline=True so the pipeline + tests run with no API keys, no
    network, no cost, and deterministically (spec §13.6).
    """

    def __init__(self, responses: dict | None = None, seed: int = 42) -> None:
        """Load canned responses (from fixtures/llm_responses.json if none passed)."""
        ...

    def with_structured_output(self, schema: type) -> _StructuredRunnable:
        """Return a runnable that yields validated `schema` instances from fixtures.

        Mirrors ChatGroq.with_structured_output so BaseAgent chains are backend-agnostic.
        Seeded variation across calls supports Layer-2 self-consistency offline."""
        ...


def make_llm(config: Config):
    """Return MockLLM (offline) or ChatGroq (online). Groq only — no OpenAI path.

    The single instantiation seam: callers only ever do
    `make_llm(config).with_structured_output(Schema)`."""
    if config.offline:
        ...  # return MockLLM(seed=config.seed)

    if config.provider == "groq":
        from langchain_groq import ChatGroq  # import kept function-local

        ...  # return ChatGroq(model=config.model_id, temperature=config.temperature,
             #                  api_key=config.groq_api_key)

    raise ValueError(f"unknown provider: {config.provider}")
```

```json
// fixtures/llm_responses.json — shape (keyed by Schema.__name__, list enables spread)
{
  "NewsSignal":      [{"reasoning": "...", "sentiment": 0.4, "signal": "long", "confidence": 0.65}],
  "MacroSignal":     [{"reasoning": "...", "regime": "neutral", "macro_risk": 0.3, "drivers": ["Fed"]}],
  "TechnicalSignal": [{"reasoning": "...", "signal": "long", "confidence": 0.6, "indicators": {}}],
  "ResearchStance":  [{"bull_case": "...", "bear_case": "...", "thesis_still_valid": true,
                       "action": "hold", "target_direction": 1, "conviction": 0.7}],
  "MemoryContext":   [{"analogs": ["..."], "lesson": "..."}]
}
```

## How It Connects
Everything that follows in Step 2 leans on this one doorway. When a `BaseAgent` subclass
builds its chain, it calls `make_llm(config)` once and pipes a `ChatPromptTemplate` into
`llm.with_structured_output(Schema)`; the agent neither knows nor cares whether the brain
on the other side is a live Groq model or the canned `MockLLM`, because both speak the
same `with_structured_output` language and both return a validated Pydantic signal —
`NewsSignal`, `MacroSignal`, `TechnicalSignal`, or `ResearchStance`. Offline, the MockLLM
reaches into `fixtures/llm_responses.json`, picks a canned answer keyed by the schema's
class name, and (thanks to its seed counter) can give slightly different actions across
repeated calls — which is exactly what the DebateAgent needs when the conviction engine
samples it K times to measure self-consistency. So this small factory is what lets the
whole agent layer be developed, tested, and self-verified for free and deterministically,
and lets a real model swap in for the live backtest by flipping `config.offline`.

## Key Technology, Design Patterns & Packages
- **Factory pattern** (`make_llm`) — the single place a model is instantiated; one line
  switches offline↔online, keeping every consumer ignorant of the choice.
- **Strategy pattern** — online vs offline are interchangeable strategies behind the
  identical `with_structured_output(Schema)` interface.
- **LangChain `with_structured_output`** — the contract `MockLLM` must imitate so agents
  receive validated Pydantic objects instead of raw text (no hand-parsing JSON).
- **ChatGroq (`langchain_groq`)** — the only online backbone; import kept function-local
  so offline runs need no LLM dependency installed.
- **Pydantic** — schemas (`src/schemas.py`) are both the structured-output target and the
  validation layer; `Schema(**data)` guarantees fixtures are well-formed.
- **Why:** the seam makes the pipeline free + deterministic to test, swappable in one line,
  and ensures the conviction math downstream operates on identical typed objects regardless
  of backend.

## Definition of Done
- [x] **Acceptance command:** `.venv/bin/python -m pytest tests/test_llm.py -q` green (9 passed). ✅ 2026-06-19
- [x] **Tests (offline & deterministic):** with `Config(offline=True)`, `make_llm` returns `MockLLM`; `MockLLM.with_structured_output(Schema).invoke(...)` returns a **validated** instance of each schema (`NewsSignal`, `MacroSignal`, `TechnicalSignal`, `ResearchStance`, `MemoryContext`) from `fixtures/llm_responses.json`; same seed → identical output; seeded spread yields >1 distinct action across K calls.
- [x] **Contract parity:** `MockLLM` exposes the exact `with_structured_output(Schema)` surface a `ChatGroq` client does; no `config.offline` branch leaks above the factory.
- [x] **Gate:** `make check` green (ruff + mypy 22 files + 25 unit + e2e).
- [x] **features.json:** S21 owns no feature → it **enables F04–F08** (offline MockLLM parity); no F flipped.
- [x] **Rules:** one `make_llm(config)` seam (no inline `ChatGroq`/`ChatOpenAI`; OpenAI branch removed); Groq-only with function-local import; `langchain_groq` not needed offline; fixtures committed; no keys/network/MCP; numbers only in config (`seed`, `temperature`). ADR-006.
- [x] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` ADR-006 added.
