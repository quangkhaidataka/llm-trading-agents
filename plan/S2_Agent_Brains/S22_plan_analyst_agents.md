# S2.2 — Analyst Agents (News / Macro / Technical)

## Objective
With a brain wired in, the system starts forming opinions. This sub-step builds the three
analysts, each reading a different slice of the immutable `Observation` and returning a
typed signal — never free text. The `NewsAgent` reads the idiosyncratic AAPL headlines and
asks the question a baseline can't: is this news a genuine *surprise* or already *priced in*?
The `MacroAgent` reads the topic-feed macro headlines and market context to classify the
*regime*, and is forbidden from forming any AAPL-specific view (channel hygiene). The
`TechnicalAgent` reads the pre-computed indicators and *interprets* them — it must never
invent or recompute a number. All three share two disciplines baked into their prompts:
**reason-first** (a short `reasoning` field generated before any commitment, since schema
order is generation order) and a shared `CONFIDENCE_RUBRIC` that defines `confidence` as a
calibrated probability, so the numbers mean the same thing across agents and the downstream
conviction math can actually compare them. Each agent is the same shape: a `BaseAgent`
Template Method whose `_build_chain` returns the LCEL chain `prompt | llm.with_structured_output(Schema)`,
and a thin `run` that renders the `Observation` into the prompt.

## Inputs and Outputs
- **Inputs**
  - `Observation` from `get_observation(ticker, t)` (its `render_news` / `render_macro` /
    `render_indicators` helpers feed the prompts), `PortfolioState`.
  - `make_llm(config)` (S2.1); `config` (`ticker`, `temperature=0` for these decision agents,
    `relevance_cutoff`, `max_news_per_day`).
  - `BaseAgent` (`src/agents/base.py`); `CONFIDENCE_RUBRIC` constant (added to a prompts module).
- **Outputs (each agent returns its Pydantic schema from `src/schemas.py`)**
  - `src/agents/news.py` → `NewsAgent.run(...) -> NewsSignal` (reasoning, sentiment, signal, confidence).
  - `src/agents/macro.py` → `MacroAgent.run(...) -> MacroSignal` (reasoning, regime, macro_risk, drivers).
  - `src/agents/technical.py` → `TechnicalAgent.run(...) -> TechnicalSignal` (reasoning, signal, confidence, indicators).
  - Note (PLAN fix #4): analyst schemas in `src/schemas.py` are reordered so `reasoning`/`rationale`
    is the **first** field (reason-first generation).
  - `tests/test_agents.py` — each agent returns its schema on a fixture day (offline).

## Skeleton Python Code
```python
"""src/agents/prompts.py — shared prompt constants."""
CONFIDENCE_RUBRIC = """confidence = your estimated probability that this signal's DIRECTION
is correct over the next ~5 trading sessions. Use the scale honestly: 0.5 = no edge
(coin flip), 0.6-0.7 = mild edge, 0.8+ = strong, well-supported edge. Do not be overconfident."""

NEWS_SYSTEM = """You are an equity news analyst for the asset referred to as {ticker}. Reason
ONLY from the news below — no outside knowledge, and nothing you may know about events after {t}.
Work in order: (1) identify the key events; (2) judge whether each is a genuine SURPRISE or is
already expected / priced in — only fresh, market-moving information should move your signal;
(3) then decide. sentiment = the raw tone of the news (-1..1); signal = the TRADING implication,
which MAY differ from sentiment when news is already priced in. If there is no relevant news,
return signal=flat, sentiment~0, low confidence.
{CONFIDENCE_RUBRIC}
Return: reasoning (<=2 sentences), sentiment, signal, confidence."""
NEWS_HUMAN = """Date: {t}\nNews for {ticker}:\n{news}"""

MACRO_SYSTEM = """You are a macro strategist. Using ONLY the macro news and market context up to
{t} (no outside or future knowledge), assess the systematic backdrop. Do NOT form a view on
{ticker} specifically.
Definitions: risk_on = easing conditions, supportive of equities; risk_off = stress / tightening /
flight-to-safety; neutral = mixed or unclear. macro_risk in [0,1] = current systematic risk to
equities (0 = calm, 1 = acute stress such as a crisis or major Fed shock).
Work in order: identify the main drivers (Fed/rates, growth, geopolitics), then classify.
Return: reasoning, regime in {{risk_on, neutral, risk_off}}, macro_risk, drivers (list)."""
MACRO_HUMAN = """Date: {t}\nMacro news (by topic, never relevance-filtered):\n{macro_headlines}
SPY trend: {spy_trend}    Rate change: {rate_chg}"""

TECH_SYSTEM = """You are a technical analyst. The indicators below are pre-computed for {ticker}
as of {t}. Do NOT invent or recompute any number — interpret only what is given. Look for
CONFLUENCE (multiple indicators agreeing) rather than one indicator, and mind context (e.g.
RSI>70 in a strong uptrend is not automatically bearish). If indicators conflict, prefer flat /
lower confidence.
{CONFIDENCE_RUBRIC}
Return: reasoning, signal in {{long, flat, short}}, confidence."""
TECH_HUMAN = """Date: {t}
RSI(14)={rsi}  MACD={macd}  MA20={ma20}  MA50={ma50}  realized_vol20={vol}  momentum={mom}"""
```

```python
"""src/agents/news.py / macro.py / technical.py — LCEL analyst agents (Template Method)."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import NewsSignal, MacroSignal, TechnicalSignal, PortfolioState


class NewsAgent(BaseAgent):
    """Idiosyncratic AAPL-news analyst: surprise vs priced-in, tone vs trading signal."""

    def _build_chain(self):
        """Return ChatPromptTemplate.from_messages([NEWS_SYSTEM, NEWS_HUMAN])
        | self.llm.with_structured_output(NewsSignal)."""
        ...

    def run(self, obs: Observation, state: PortfolioState) -> NewsSignal:
        """Render obs.render_news() into the prompt and invoke the chain. Empty news → flat."""
        ...


class MacroAgent(BaseAgent):
    """Systematic regime strategist — never forms an asset-specific (AAPL) view."""

    def _build_chain(self):
        """Return prompt(MACRO_SYSTEM, MACRO_HUMAN) | self.llm.with_structured_output(MacroSignal)."""
        ...

    def run(self, obs: Observation, state: PortfolioState) -> MacroSignal:
        """Render obs.render_macro() (NEVER relevance-filtered) + spy_trend/rate_change, then invoke."""
        ...


class TechnicalAgent(BaseAgent):
    """Indicator interpreter — interprets, never computes; prefers confluence."""

    def _build_chain(self):
        """Return prompt(TECH_SYSTEM, TECH_HUMAN) | self.llm.with_structured_output(TechnicalSignal)."""
        ...

    def run(self, obs: Observation, state: PortfolioState) -> TechnicalSignal:
        """Render obs.render_indicators() into the prompt and invoke the chain."""
        ...
```

## How It Connects
Each analyst is a thin specialization of the same `BaseAgent` skeleton: at construction it
asks `make_llm(config)` for a brain (real Groq or the offline MockLLM, identical interface),
then `_build_chain` assembles the LCEL pipe `ChatPromptTemplate | llm.with_structured_output(Schema)`,
binding the agent to its output contract. At decision time, `run` takes the day's immutable
`Observation`, calls the right render helper to turn raw news / macro headlines / indicators
into compact labeled text, fills the prompt's `{ticker}`/`{t}` slots, and invokes the chain —
which hands back a validated `NewsSignal`, `MacroSignal`, or `TechnicalSignal`. Because every
prompt is reason-first and shares the same `CONFIDENCE_RUBRIC`, the three `confidence` numbers
mean the same thing, so when the DebateAgent and the conviction engine later collect these
signals as directional votes, the agreement and mean-confidence math is comparing apples to
apples rather than three differently-scaled gut feelings.

## Key Technology, Design Patterns & Packages
- **Template Method (`BaseAgent`)** — fixes `__init__`/`run` lifecycle; each subclass only
  supplies `_build_chain` and its render logic. Uniform, testable, low-duplication.
- **Strategy** — News/Macro/Technical are interchangeable analyst strategies producing
  comparable typed signals into the same downstream conviction math.
- **LangChain LCEL (`prompt | llm.with_structured_output(Schema)`)** — declarative chain
  composition; the schema is the contract, no hand-parsed JSON.
- **`ChatPromptTemplate.from_messages`** — System/Human templates parameterized by
  `{ticker}`/`{t}`/thresholds; the v2 prompts (rubric, surprise/priced-in, reason-first).
- **Pydantic schemas** — `NewsSignal`/`MacroSignal`/`TechnicalSignal`; reason-first field
  order so the model reasons before it commits.
- **`temperature=0`** for these decision agents (determinism); the DebateAgent (S2.3) is the
  only one sampled at `temperature>0`, for self-consistency.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_agents.py -k "news or macro or technical" -q` green (per-agent: `-k news` → F04, `-k macro` → F05, `-k technical` → F06).
- [ ] **Tests (offline & deterministic):** with `Config(offline=True)` (MockLLM + `fixtures/llm_responses.json`), each agent's `run(obs, state)` returns its correct Pydantic schema on **one fixture day** — `NewsAgent`→`NewsSignal`, `MacroAgent`→`MacroSignal`, `TechnicalAgent`→`TechnicalSignal` — all fields valid/in-range; empty-news day → `NewsSignal(signal=flat, sentiment≈0, low confidence)`.
- [ ] **Channel/hygiene cases:** MacroAgent fed from the topic feed, **never relevance-filtered**, and forms no AAPL-specific view; TechnicalAgent only interprets the provided indicators (no fabricated numbers).
- [ ] **Gate:** `make check` green (ruff + mypy + pytest unit + e2e).
- [ ] **features.json:** F04, F05, F06 → `passing` with evidence (the matching `pytest -k` command output).
- [ ] **Rules:** LCEL `prompt | llm.with_structured_output(Schema)` in `_build_chain` (never hand-parse JSON); model only via `make_llm`; `temperature=0`; offline parity (agents never branch on `config.offline`); System prompts parameterized by `{ticker}`/`{t}` with the mandatory anti-leak line — no hardcoded `"AAPL"`; thresholds/limits only in config.
- [ ] **Tracking:** `PROGRESS.md` updated; note PLAN fix #4 — `src/schemas.py` analyst schemas reordered so `reasoning`/`rationale` is the **first** field (reason-first generation order), with conformance tests adjusted.
