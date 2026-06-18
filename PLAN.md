# PLAN.md — Implementation Roadmap

> Multi-Agent LLM Trading System for AAPL. This document is the engineering roadmap from the current
> scaffold (M0 done) to the finished, evaluated system. Each step is a runnable milestone that leaves
> something working and keeps `make check` green. Authoritative spec: `project_description.md`.
> Architecture summary: `CLAUDE.md` + `docs/`. Rules every step must obey: `.claude/rules/`.

## Where we are

**M0 (Setup) is complete.** The repo skeleton, A2A Pydantic schemas (`src/schemas.py`), the
`get_observation` contract (`src/data/loaders.py`), all agent/graph/backtest/eval stubs, the harness
(`.claude/`, `docs/`, `Makefile`, `features.json`), and offline fixtures exist. Every `src/` function
raises `NotImplementedError("Mx: ...")`. `make setup` + `make check` pass; git is initialized with a
clean checkpoint. The Alpha Vantage and Groq keys are in `.env`, so live data download and live LLM
calls are unblocked.

## Guiding principles (apply to every step)

1. **Anti-lookahead is priority #1.** All data flows through the single `get_observation(ticker, t)`
   gate; execute at `t+1`; memory writes are delayed to `t+1+h`; never report warm-up PnL. (spec §12.1)
2. **The A2A protocol is the product.** Agents speak only through Pydantic schemas, built as
   `prompt | llm.with_structured_output(Schema)`. Never hand-parse JSON.
3. **Numbers live in `config.py` only.** Propose defaults from domain knowledge, tune on 2022–2024.
4. **Offline-first.** Everything must run with `config.offline=True` (MockLLM + fixtures) — no keys,
   no network, deterministic. This is how every step self-verifies.
5. **Ticker-dynamic.** No hardcoded `"AAPL"`; setting `config.ticker = "AMZN"` must just work.
6. **YAGNI.** Build the MVP path first; add robustness layers only once the spine runs end-to-end.

## Step map

The 15 fine-grained tasks are grouped into **6 milestone-aligned steps**. Build them in order; each
ends with its acceptance test green and `make check` passing before the next begins.

```
Step 1 (M1) Data layer & anti-lookahead gate
        ▼
Step 2 (M2) Agent brains: LLM plumbing + analysts + debate + conviction
        ▼
Step 3 (M3) Memory + decision (position manager) + LangGraph orchestration  ── one day end-to-end
        ▼
Step 4 (M4) Walk-forward backtest (vectorbt, fees, t+1)
        ▼
Step 5 (M5) Conviction calibration + baselines + ablations
        ▼
Step 6 (M5) Reporting + final DoD (+ non-LLM robustness checks)
```

Milestone mapping: **M1** = Step 1 · **M2** = Step 2 · **M3** = Step 3 · **M4** = Step 4 ·
**M5** = Steps 5–6.

---

### Step 1: Data Layer & Anti-Lookahead Gate

#### Objective
In this first step we build the foundation everything else stands on: the data layer. We open two taps
to the outside world — **Alpha Vantage (AV)** for *news* (AAPL-specific and macro-by-topic) and **Yahoo
Finance (`yfinance`)** for *prices* (AAPL + SPY adjusted OHLCV) — cache each to Parquet exactly once,
compute the technical indicators with plain math, and then assemble everything the system is allowed to
know on day `t` into one immutable `Observation`. Finally we lock the door with a test that proves no
future data can ever leak through. After this step, the rest of the project reads only from disk.

#### Why This Step Matters
This is the project's credibility and the literal entry point for all downstream work. A quant reviewer
asks first, "are you sure there's no look-ahead?" — and our answer is "there is exactly one function
that returns data, and it provably filters to `≤ t`." Centralizing point-in-time logic in
`get_observation` means every agent, the backtest, and the memory layer inherit the guarantee for free.
Splitting sources is deliberate: the free AV tier allows only 25 requests/day, so its scarce budget is
spent entirely on the heavy windowed *news* download, while prices come key-free from yfinance (spec
§2.1 explicitly lists price as swappable: "AV `TIME_SERIES_DAILY_ADJUSTED` (or WRDS/CRSP)"). This step
also physically establishes the **two-channel separation** (idiosyncratic AAPL news vs. systematic
macro), a core design contribution.

#### Inputs
- `ALPHAVANTAGE_API_KEY` in `.env` — **news only**. `yfinance` needs **no key**.
- `config.py`: `ticker`, `benchmark`, `warmup_start`, `test_end`, `macro_topics`, `relevance_cutoff`,
  `max_news_per_day`, `cache_dir`; plus indicator windows added here (`rsi_period=14`, `ma_short=20`,
  `ma_long=50`, `vol_window=20`, `mom_window=10`) — in config, not inline.
- AV endpoints (news): `NEWS_SENTIMENT&tickers=AAPL`, `NEWS_SENTIMENT&topics=...`.
- yfinance: `yfinance.download(symbol, start, end, auto_adjust=True)` for AAPL and SPY.
- The stubs in `src/data/loaders.py` (`get_observation`, `load_*`, `compute_indicators`), the
  `--mode download` branch in `src/main.py`, and the existing fixtures.
- New dependency: `yfinance` (not yet in `requirements.txt`).

#### Outputs
- **AV → news caches:** `data/{ticker}_news.parquet` (`title, summary, time_published, relevance,
  av_sentiment`; string numerics cast to float; AAPL entry picked from `ticker_sentiment`) and
  `data/macro_news.parquet` (`title, summary, time_published, topics`; **not** relevance-filtered).
- **yfinance → price caches:** `data/{ticker}_prices.parquet`, `data/SPY_prices.parquet` (adjusted
  OHLCV, lowercase columns `date, open, high, low, close, volume`).
- Two adapter modules: `src/data/alpha_vantage.py` (news HTTP) and `src/data/yahoo.py` (prices); a
  `cache.py` helper.
- Working `compute_indicators(prices_until_t) -> dict` → `{rsi, macd, ma20, ma50, vol20, mom}` (rows
  `≤ t`) and `get_observation(ticker, t) -> Observation` (news/macro/indicators/price/spy_trend all
  `≤ t`). `python -m src.main --mode download` writes caches + prints one rendered `Observation`.
- **Tests:** green, un-`xfail`ed `tests/test_no_lookahead.py` (for every `t`, no field dated `> t`) +
  `tests/test_observation.py` (indicator values, NaN-warmup handling). Enlarged `fixtures/` (~40
  sessions). All cache files gitignored. → `features.json` F02/F03 `passing`.
- **Acceptance (M1):** `test_no_lookahead` green; one observation prints.

#### Challenges and Risks
- **Silent future leakage.** Any `shift(-1)`, `bfill`, or centered rolling window leaks the future;
  slice `prices.loc[:t]` *before* computing indicators. MACD/MA need enough prior history.
- **AV rate limits / dirty data.** ≤1000 items/call, time-windowed, multi-year → windowed requests
  with backoff; numbers as strings; one item may list several tickers (pick the AAPL entry).
- **Timezone correctness.** AV `time_published` is `YYYYMMDDTHHMMSS`; mis-parsing silently breaks every
  later point-in-time guarantee. Normalize once (US/Eastern → date).
- **Do not relevance-filter macro** — that filter is AAPL-only; filtering macro drops the
  Fed/geopolitical coverage that justifies the channel.
- **yfinance adjustment back-fill.** `auto_adjust=True` back-adjusts using future splits/dividends —
  same property as AV's adjusted series, standard for close-to-close backtests; caching freezes it (not
  tradeable lookahead). It is an unofficial scraper → **pin the version**; offline tests use fixtures.
- **Calendar alignment.** News dates, trading days, and SPY must align on sessions; holidays/missing
  bars must not shift the index.

#### Technical Implementation Details
- **Design patterns: Adapter + Repository + Facade.** Two thin Adapters (`alpha_vantage.py` over AV
  REST news; `yahoo.py` over yfinance). The `load_*` functions are the Repository: call the right
  Adapter (online) or read fixtures (offline), return clean records. `get_observation` is the **Facade**
  — the *only* public entry; nothing else touches a full dataframe. Source choice lives entirely here.
- **Indicators** via the `ta` library (`RSIIndicator`, `MACD`, `SMAIndicator`) + pandas
  `rolling(...).std()` / `pct_change`. Windows from `config`. `Observation` stays a frozen dataclass.
- **Caching:** `read_or_fetch(path, fetch_fn)` — read Parquet if present else fetch+write (`pyarrow`),
  idempotent. Cache LLM nothing here.
- **Offline branch:** `config.offline` → `load_news/macro` read `fixtures/*.json`, `load_prices` reads
  `fixtures/prices_sample.csv` (already `open,high,low,close,volume,spy_close`).
- **Libraries:** `yfinance`, `requests`, `pandas`+`pyarrow`, `python-dateutil`. Heavy imports
  function-local. Add `yfinance==0.2.x` (+ `python-dateutil` if missing) to `requirements.txt`;
  `make setup-full`.
- **Record the decision:** add an ADR to `DECISIONS.md` ("prices via yfinance, news via AV").

**`Observation` class skeleton** (expands the frozen dataclass already stubbed in
`src/data/loaders.py`; methods show structure + intent only, not full logic):

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Observation:
    """Immutable, point-in-time snapshot of everything the system may know on day t.

    Built ONLY by get_observation(ticker, t); every field is guaranteed <= t.
    Agents depend on this contract, not on how data was loaded — so swapping a data
    source (AV/yfinance/WRDS) never touches any consumer.
    """

    # ---- Fields (all already filtered to <= t by the gate) ----
    ticker: str                       # asset under management (from config.ticker)
    t: date                           # the decision date ("today")
    aapl_news: list[dict]             # idiosyncratic AAPL news: {title, summary, time_published, relevance, av_sentiment}
    macro_news: list[dict]            # systematic macro-by-topic news: {title, summary, time_published, topics}
    indicators: dict                  # precomputed TA: {rsi, macd, ma20, ma50, vol20, mom}
    price: float                      # adjusted close at t (valuation only; execution is at t+1)
    spy_trend: float                  # SPY trend signal up to t (market/beta context)
    rate_change: float | None = None  # (stretch) Fed funds / treasury yield change up to t

    # ---- Validation ----
    def __post_init__(self) -> None:
        """Fail-loud point-in-time backstop: assert no news item is dated after `t`
        and required fields are present; raise ValueError on any future-dated record.
        (get_observation already filters; this guards against a future regression.)"""
        ...

    # ---- Prompt-rendering helpers (compact labeled text the agents inject) ----
    def render_news(self, max_items: int | None = None) -> str:
        """Render the AAPL news block ('title — summary' per line, newest first,
        capped at max_items / config.max_news_per_day) for the NewsAgent prompt."""
        ...

    def render_macro(self) -> str:
        """Render the macro headlines block for the MacroAgent prompt. NOTE: macro
        news is never relevance-filtered — channel hygiene (idiosyncratic vs systematic)."""
        ...

    def render_indicators(self) -> str:
        """Render indicators as labeled text ('RSI=.. MACD=.. MA20=..') for the
        TechnicalAgent, which interprets these numbers but never computes them."""
        ...

    # ---- Memory / embedding ----
    def to_memory_text(self) -> str:
        """Build the compact text (news gist + indicators + market context) that
        MemoryStore embeds as the retrieval key for this day's episode."""
        ...

    # ---- Convenience / introspection ----
    def has_news(self) -> bool:
        """True if any AAPL news exists today, so agents can degrade gracefully
        (flat, low confidence) on empty-news days instead of hallucinating."""
        ...

    def to_dict(self) -> dict:
        """JSON-serializable view (t as isoformat, indicator values, price, news
        counts) for the per-day decision log and the (ticker, date) cache."""
        ...
```

**`get_observation(ticker, t)` gate** (the single doorway; structure + intent only — the
comments describe each stage, the bodies are filled in during Step 1):

```python
def get_observation(ticker: str, t: date) -> Observation:
    """THE single point-in-time gate — the ONLY function that returns data to the rest
    of the system. Assembles an Observation in which every field is <= t.

    Online (config.offline=False): reads the Parquet caches from `--mode download`
    (yfinance prices, AV news). Offline: reads fixtures/. Either way, consumers only
    ever see the returned Observation — never the raw frames, an API, or a future row.
    """
    # 1. Prices up to and including t (adjusted OHLCV). The loader slices to <= t
    #    BEFORE any computation, so future rows are physically absent (no shift(-1)).
    prices = load_prices(ticker, until_t=t)          # yfinance cache / fixtures
    spy = load_prices(config.benchmark, until_t=t)   # SPY for market context

    # 2. Deterministic technical indicators, computed on rows <= t only (ta/pandas).
    indicators = compute_indicators(prices)

    # 3. News strictly point-in-time (time_published <= t), via the two channels:
    #    - AAPL: relevance-filtered + capped at config.max_news_per_day (idiosyncratic)
    #    - macro: fetched by config.macro_topics, NEVER relevance-filtered (systematic)
    aapl_news = load_news(ticker, t)
    macro_news = load_macro_news(config.macro_topics, t)

    # 4. Market/beta context up to t (e.g. sign/slope of SPY trend) + optional rate move.
    spy_trend = compute_spy_trend(spy)
    rate_change = None  # (stretch) Fed funds / treasury yield change <= t

    # 5. Assemble the immutable snapshot; Observation.__post_init__ re-asserts the
    #    <= t invariant as a fail-loud backstop before it is handed to any agent.
    return Observation(
        ticker=ticker,
        t=t,
        aapl_news=aapl_news,
        macro_news=macro_news,
        indicators=indicators,
        price=float(prices.iloc[-1]["close"]),   # close at t; execution happens at t+1
        spy_trend=spy_trend,
        rate_change=rate_change,
    )
```

> The internal loaders it calls (`load_prices`, `load_news`, `load_macro_news`,
> `compute_indicators`, and the small `compute_spy_trend` helper) are the only code that
> touches a cache/fixture or a full dataframe; nothing outside this module does.

---

### Step 2: Agent Brains — LLM Plumbing, Analysts, Debate & Conviction

#### Objective
Now the system starts to think. We first give it a brain and a fake brain: the `make_llm` factory that
returns a real `ChatGroq` client online and a deterministic `MockLLM` offline, both speaking the same
`with_structured_output(Schema)` language. Then we build the reasoning agents — the three analysts
(News reads idiosyncratic headlines, Macro judges the regime, Technical interprets the indicators) and
the state-aware DebateAgent that runs a Bull-vs-Bear argument relative to the current position. Finally
we build the conviction engine that turns the debate's fuzzy confidence into a number grounded in
measurable signals and self-consistency.

#### Why This Step Matters
This step turns raw `Observation` data into typed opinions and a defensible decision signal — the heart
of the A2A protocol that is this project's contribution. The News/Macro split operationalizes the
idiosyncratic-vs-systematic design; the "interpret, don't compute" rule keeps the Technical agent from
hallucinating numbers; the DebateAgent's "is the thesis still valid?" framing and hold-bias are what
make the system a position manager, not a daily classifier. The conviction engine is what lets later
thresholds mean probabilities rather than vibes. The clean factory seam also lets us swap the Groq
model in one line, and keeps the whole pipeline runnable offline for free, deterministic testing.

#### Inputs
- Step 1 (`get_observation`), `src/llm.py` (`make_llm`, `MockLLM` stubs), `src/schemas.py`
  (`NewsSignal`, `MacroSignal`, `TechnicalSignal`, `MemoryContext`, `ResearchStance`), `BaseAgent`.
- `fixtures/llm_responses.json` (canned per-agent responses).
- `config`: `provider`, `model_id`, `temperature`, `offline`; `K`, `w1/w2/w3`, `alpha/beta`;
  `ticker`, `relevance_cutoff`, `max_news_per_day`.
- Prompt designs from spec §5.1–§5.3, §5.5, §7.3.

#### Outputs
- Working `make_llm(config)` (ChatGroq online / MockLLM offline) and a `MockLLM` whose
  `.with_structured_output(Schema)` yields a validated `Schema` from fixtures (controllable spread for
  self-consistency). `tests/test_llm.py`.
- `src/agents/{news,macro,technical}.py` and `src/agents/debate.py` as LCEL chains returning their
  schemas. `DebateAgent` consumes the four signals + `PortfolioState` → `ResearchStance`.
- Conviction engine in `src/eval/calibration.py`: `composite_conviction(...)` (Layer 1: agreement,
  mean confidence, memory consistency) and `self_consistency_conviction(...)` (Layer 2: K samples,
  majority frequency), combined into raw `z`. (Isotonic calibration = Step 5.)
- **Tests:** `tests/test_agents.py` (each agent returns its schema on a fixture day; DebateAgent
  prefers `hold` when a held thesis stays valid) + conviction unit tests. → F04/F05/F06/F08.
- **Acceptance (M2):** each agent returns the correct Pydantic schema on one day (offline).

#### Challenges and Risks
- **MockLLM fidelity.** Must mimic LangChain's `with_structured_output` return contract so agents can't
  tell online from offline; must support a seeded action spread for self-consistency tests.
- **Anti-leak prompts.** Every System prompt forbids outside/future knowledge; MacroAgent must *not*
  form an AAPL-specific view; TechnicalAgent must not invent numbers; handle empty-news days (→ flat).
- **Macro channel hygiene.** Confirm macro headlines come from the topic feed, never relevance-filtered.
- **Conviction edge cases.** Guard divide-by-zero in `agreement` when all confidences are 0.
- **Cost of K-sampling.** K× DebateAgent calls/day; Groq free tier covers it; cache by
  `(ticker, date, agent, sample_idx)` so reruns/ablations are free.

#### Technical Implementation Details
- **Design patterns: Factory** (`make_llm`, online/offline Strategy) + **Template Method** (`BaseAgent`
  defines `__init__`/`run`; each subclass implements `_build_chain` = `ChatPromptTemplate |
  llm.with_structured_output(Schema)` and a thin `run` rendering the `Observation`).
- `MockLLM.with_structured_output(Schema)` → a small runnable whose `.invoke` looks up a canned dict by
  `Schema.__name__` (optionally varied by seeded index) and returns `Schema(**data)`.
- Prompts via `ChatPromptTemplate.from_messages`, parameterized by `{ticker}` + thresholds; render
  helpers turn news/indicators/state into compact labeled text. `temperature=0` for decision agents;
  DebateAgent sampled at `temperature>0` only for Layer 2.
- Conviction = pure functions implementing spec §7.3 formulas; randomness lives only in the LLM layer.
- Keep `langchain_groq` imports function-local. (Provider stays Groq-only; no OpenAI — the project's
  budget is all-free, so any backbone swap uses a second Groq model.)

**The conviction methodology (why and how).** The system needs one number — *conviction* — to drive
the hysteresis thresholds (open if `≥ tau_enter`, exit if `< tau_exit`, …). The naive way is to ask the
LLM "how confident are you?" — but LLMs are overconfident and inconsistent, so that number is garbage.
Instead we **compute** conviction from measurable quantities, in three layers. Layers 1–2 (build the
raw score `z`) are this step; Layer 3 (turn `z` into a real probability) is Step 5.

- **Layer 1 — composite from measurable signals.** Blend three observable quantities, not a gut feeling:
  - *agreement* `= |Σ sᵢcᵢ| / Σ cᵢ` — do the directional agents point the same way? (each casts a vote
    `sᵢ ∈ {−1,0,+1}` weighted by its confidence `cᵢ`). All-agree → 1.0; conflicting → near 0.
  - *mean_confidence* `= mean(cᵢ)` — how confident on average.
  - *memory_consistency* `= (#analogs whose stored reward supported the action) / k` — did similar
    past situations actually work out?
  - → `conviction_raw = w1·agreement + w2·mean_confidence + w3·memory_consistency`.
    *Example:* agreement 1.0, mean_conf 0.7, mem 0.8, weights 0.4/0.3/0.3 → `0.85`.
- **Layer 2 — self-consistency.** Ask the DebateAgent the same question `K` times at `temperature>0`;
  conviction = how often it gives the **majority** action. Stable answer → confident; wavering → not.
  *Example:* `open,open,open,hold,open` → `4/5 = 0.8`.
- **Combine into raw `z`:** `z = alpha·conviction_raw + beta·conviction_sc`
  *(e.g. 0.5·0.85 + 0.5·0.8 = 0.825)*. This `z` is a 0–1 score, **not yet a probability**.
- **Layer 3 (Step 5) — calibration.** Learn the mapping `z → P(correct)` from 2022–2024 history (e.g.
  `z≈0.825` was actually right 74% of the time → conviction `= 0.74`). Only then does `tau_enter = 0.7`
  truly mean "≥70% real chance of being right." It lives in Step 5 because it needs historical results.
- *Headline:* the LLM supplies only **direction + reasoning**; the decision **number comes from math**.

**Conviction function skeletons** (in `src/eval/calibration.py`; structure + intent only — Layers 1–2
here, the `fit_calibrator`/`reliability_diagram` of Layer 3 are filled in Step 5):

```python
def composite_conviction(signals: list[dict], memory_consistency: float, config: Config) -> float:
    """Layer 1 — blend measurable quantities into conviction_raw (0–1), NOT the LLM's self-report.

    `signals` = the directional agent outputs, each {direction: -1|0|+1, confidence: 0..1}.
    Computes: agreement = |Σ sᵢcᵢ| / Σ cᵢ  (guard Σcᵢ==0 → 0),
              mean_confidence = mean(cᵢ),
              and folds in memory_consistency (share of retrieved analogs that supported the action).
    Returns w1·agreement + w2·mean_confidence + w3·memory_consistency  (weights from config, Σw=1)."""
    ...


def self_consistency_conviction(actions: list[str], K: int) -> float:
    """Layer 2 — turn a fuzzy judgment into a frequency.

    `actions` = the K actions the DebateAgent produced when asked the same question K times at
    temperature>0. Returns (count of the most common action) / K — high = stable/confident,
    low = wavering. Example: ['open','open','open','hold','open'] → 0.8."""
    ...


def raw_conviction(conviction_raw: float, conviction_sc: float, config: Config) -> float:
    """Combine Layers 1 and 2 into the raw score z = alpha·conviction_raw + beta·conviction_sc
    (alpha, beta from config). z is a 0–1 score; it becomes a true probability only after the
    Step-5 calibrator maps it via P(correct | z)."""
    ...
```

**Prompt design — v1 (build now) + v2 improvements.** The spec §5 prompts are a solid MVP; build them
as **v1**, then apply five cheap, high-leverage fixes **now** and defer two as **ablations** (the Step-5
eval framework turns "prompt v1 vs v2" into evidence, not guesswork). Because conviction is *math over
the agents' numbers*, the consistency/meaning of those numbers matters more here than in a normal
chatbot prompt — which is why fix #1 is the most important.

| # | Improvement | Why it matters | When |
|---|---|---|---|
| 1 | Define `confidence` via a shared rubric | it feeds the conviction math; undefined → not comparable across agents | now |
| 2 | "surprise / priced-in" nudge (News) | avoid just mimicking the AV-sentiment baseline you must beat | now |
| 3 | split `sentiment` (tone) vs `signal` (trading implication) | prevents inconsistent News output | now |
| 4 | reason-first field order | model reasons before it commits (schema order = generation order) | now |
| 5 | empty-news handling + regime definitions | no hallucinated signal on quiet days; consistent macro labels | now |
| 6 | anonymize the ticker ("the asset") | less reliance on memorized AAPL facts (strengthens anti-leak) | ablation |
| 7 | two-persona Bull/Bear vs single LLM | less sycophantic debate (≈2–3× cost) | ablation |

Fix #4 requires reordering the analyst schemas in `src/schemas.py` so a short `reasoning` field comes
first; add a shared `CONFIDENCE_RUBRIC` constant to the prompts module. MemoryAgent (§5.4) keeps its
summarizer prompt; PositionManager (§5.6) is a deterministic rule in this plan (no prompt).

**Improved prompt templates (v2)** — concrete System/Human; `{...}` are `ChatPromptTemplate` params:

```text
# Shared snippet injected into the analyst prompts
CONFIDENCE_RUBRIC:
  confidence = your estimated probability that this signal's DIRECTION is correct over the next
  ~5 trading sessions. Use the scale honestly: 0.5 = no edge (coin flip), 0.6-0.7 = mild edge,
  0.8+ = strong, well-supported edge. Do not be overconfident.
```

```text
NewsAgent  ->  NewsSignal(reasoning, sentiment, signal, confidence)
System:
  You are an equity news analyst for the asset referred to as {ticker}. Reason ONLY from the news
  below — no outside knowledge, and nothing you may know about events after {t}.
  Work in order: (1) identify the key events; (2) judge whether each is a genuine SURPRISE or is
  already expected / priced in — only fresh, market-moving information should move your signal;
  (3) then decide. sentiment = the raw tone of the news (-1..1); signal = the TRADING implication,
  which MAY differ from sentiment when news is already priced in. If there is no relevant news,
  return signal=flat, sentiment~0, low confidence.
  {CONFIDENCE_RUBRIC}
  Return: reasoning (<=2 sentences), sentiment, signal, confidence.
Human:
  Date: {t}
  News for {ticker}:
  {title_1} — {summary_1}
  {title_2} — {summary_2}
  ...
```

```text
MacroAgent  ->  MacroSignal(reasoning, regime, macro_risk, drivers)
System:
  You are a macro strategist. Using ONLY the macro news and market context up to {t} (no outside or
  future knowledge), assess the systematic backdrop. Do NOT form a view on {ticker} specifically.
  Definitions: risk_on = easing conditions, supportive of equities; risk_off = stress / tightening /
  flight-to-safety; neutral = mixed or unclear. macro_risk in [0,1] = current systematic risk to
  equities (0 = calm, 1 = acute stress such as a crisis or major Fed shock).
  Work in order: identify the main drivers (Fed/rates, growth, geopolitics), then classify.
  Return: reasoning, regime in {risk_on, neutral, risk_off}, macro_risk, drivers (list).
Human:
  Date: {t}
  Macro news (by topic, never relevance-filtered):
  {macro_headlines}
  SPY trend: {spy_trend}    Rate change: {rate_chg}
```

```text
TechnicalAgent  ->  TechnicalSignal(reasoning, signal, confidence, indicators)
System:
  You are a technical analyst. The indicators below are pre-computed for {ticker} as of {t}.
  Do NOT invent or recompute any number — interpret only what is given. Look for CONFLUENCE (multiple
  indicators agreeing) rather than one indicator, and mind context (e.g. RSI>70 in a strong uptrend is
  not automatically bearish). If indicators conflict, prefer flat / lower confidence.
  {CONFIDENCE_RUBRIC}
  Return: reasoning, signal in {long, flat, short}, confidence.
Human:
  Date: {t}
  RSI(14)={rsi}  MACD={macd}  MA20={ma20}  MA50={ma50}  realized_vol20={vol}  momentum={mom}
```

```text
DebateAgent  ->  ResearchStance(bull_case, bear_case, thesis_still_valid, action, target_direction, conviction)
(sampled K times at temperature>0 for self-consistency, varying the evidence order between runs)
System:
  You moderate a position-management debate for the asset {ticker}. Current position {current_position}
  (-1 short, 0 flat, +1 long); entry thesis: "{active_thesis}"; held {days_held} sessions.
  Use ONLY the signals provided (no outside/future knowledge). Work in order:
    Step 1 - Bull case: the strongest GENUINE argument to be long, citing the signals.
    Step 2 - Bear case: the strongest GENUINE argument to be short/flat. Steelman both; never strawman.
    Step 3 - Thesis check: is the ORIGINAL entry thesis still valid today? (true/false + why).
    Step 4 - Recommend action in {hold, open, close, flip} and target_direction in {-1,0,1}.
  Bias to continuity: if a position is held and its thesis still holds, prefer HOLD unless there is
  clear, specific contradicting evidence; only flip on strong opposing evidence.
  Also return conviction in [0,1] = probability the recommended action is correct over ~5 sessions;
  be honest, not strategic — the final decision number is recomputed downstream from math.
Human:
  Date: {t}
  PortfolioState: position={current_position}, thesis="{active_thesis}", days_held={days_held}
  NewsSignal: {news}
  MacroSignal: {macro}
  TechnicalSignal: {technical}
  MemoryContext: {memory}
```

---

### Step 3: Memory, Decision & Orchestration

#### Objective
Here the parts become an organism. We build the episodic memory — a FAISS store where each trading
episode `(situation → action → outcome)` is embedded and retrieved, but only after its outcome window
closes — and the MemoryAgent that distills retrieved analogs into a lesson. We build the PositionManager
that turns a recommendation into an actual position change using asymmetric hysteresis and a risk veto.
Then, with LangGraph, we wire the four analysts → debate → conviction → position manager into a per-day
state machine that carries `PortfolioState` across days. Running one day end-to-end now yields a real
`TradeDecision`.

#### Why This Step Matters
This is the M3 milestone — the moment the system first works as a whole, and the orchestration/protocol
layer (the core contribution) made executable. Non-parametric memory is the project's second headline
contribution and answers research question #2; its delayed-write discipline is a second anti-lookahead
frontier as important as not reading tomorrow's price. Hysteresis + thesis-persistence are the
mechanism behind the low-turnover, hold-across-sessions behavior (research question #3), and the veto
cleanly separates risk control from signal generation. Carrying `PortfolioState` is what makes the
policy stateful.

#### Inputs
- Step 2 (agents + conviction), Step 1 (prices, for reward + vol/drawdown).
- `src/memory/store.py` (`Episode`, `MemoryStore`), `src/agents/memory.py`,
  `src/agents/position_manager.py`, `src/graph/build_graph.py` stubs.
- `config`: `h`, `k`, `embedding_model`; `tau_enter/tau_exit/tau_flip`, `vol_cap`, `dd_cap`,
  `allow_short`; feature flags (`use_memory/use_macro/use_debate/use_hysteresis/stateless`) added here
  for Step 5's ablations.
- `faiss`, `sentence-transformers`, `langgraph`.

#### Outputs
- `MemoryStore` with `stage(obs, action)`, `flush_due(current_t, prices)`, `retrieve(obs, k)`; FAISS
  index persisted under `data/`/`faiss_index/` (gitignored). `MemoryAgent.run(...) -> MemoryContext`.
- `PositionManager.decide(...) -> TradeDecision` (`new_position`, `new_thesis`, `vetoed`, `reason`).
- `build_graph(config, store)` → compiled LangGraph app + a `run_one_day(t)` path; state holds
  `PortfolioState` + the day's signals; per-day memory stage/flush. The `commit` node records a
  **full per-day decision trace** — news read, every agent's signal + rationale, the debate
  bull/bear/thesis, the conviction breakdown, and the final decision + reason — to `config.log_dir`
  (this is the data that powers the explainable web report in Step 6; spec §9).
- **Tests:** `tests/test_memory.py` (episode for `t` retrievable only at `t+1+h`; reward =
  drift-demeaned return; long-vs-short ordering preserved), `tests/test_position_manager.py` (full
  transition table + veto), `tests/test_graph.py` (one
  day offline → valid `TradeDecision`, state updates, point-in-time memory). → F07/F09/F10/F11.
- **Acceptance (M3):** one day yields a `TradeDecision`; memory writes/reads are point-in-time.

#### Challenges and Risks
- **Delayed-write correctness.** The trickiest invariant: stage at `t`, index + compute reward only at
  `t+1+h`, retrieve only closed episodes. Off-by-one = silent leakage.
- **Reward definition (corrects spec §7.1).** The memory reward is the **AAPL-drift-demeaned**
  forward return — NOT market-adjusted vs SPY:
  `reward = sign(action) · (forward_return(t,h) − μ)`, where `forward_return(t,h) = P[t+1+h]/P[t+1] − 1`
  and `μ` = AAPL's trailing average `h`-session return computed point-in-time (data ≤ t).
  Centering by `μ` (the mean) removes the "always-long is free in a bull market" bias **without** moving
  the long-vs-short decision boundary away from ≈0, so a profitable long stays rewarded. Subtracting
  **SPY** instead (the spec's wording) is wrong for a single-asset agent: SPY's return is large and can
  flip the sign, perversely rewarding *shorting a stock that rose* just because it lagged the index.
  Config knob `reward_benchmark ∈ {raw, aapl_drift}` (default `aapl_drift`); make it an ablation.
  *Caveat:* `flat` actions get reward 0 (`sign(0)=0`), so memory can't learn from good flat calls —
  an accepted simplification. See [[../DECISIONS.md]] ADR-002.
- **Memory must stay consistent and cheap.** Each day is turned into "meaning coordinates" (an
  embedding) so the store can find similar past days. Use one fixed embedding model (so the same day
  always maps to the same coordinates — comparable and reproducible), and save each day's coordinates
  keyed by `(ticker, date)` so re-runs don't recompute them. Early on, memory is nearly empty — the
  MemoryAgent must handle that calmly (return "no precedents" and let the other agents decide), not
  crash or invent analogs.
- **Get every position-transition right.** For each combination of *current position* × *signal*, there
  is one correct action (hold/open/close/flip) — it's easy to get a case subtly wrong, so test them all.
  And a risk-off veto must be able to overrule even a strong buy/sell signal — decide that order of
  priority explicitly.
- **Wire the day's flow correctly.** Keep the data passed between graph steps small and well-typed. The
  four analysts run at the same time, but the debate must wait until all four finish. And the order of
  memory operations matters: write/retrieve only closed episodes, in the right sequence, so nothing
  leaks future information.

#### Technical Implementation Details
- **Design patterns: Repository** (`MemoryStore` wraps a FAISS `IndexFlatIP` on normalized embeddings +
  parallel `Episode` metadata; consumers never touch FAISS), **State machine / rule engine**
  (`PositionManager.decide` is a pure, deterministic function keyed on `current_position` and calibrated
  conviction vs. τ thresholds, veto checked first — spec §5.6 lightweight option keeps the number
  mathematical), **Pipeline/mediator** (LangGraph nodes: `observe` → `{news,macro,technical,memory}`
  parallel → `debate` → `conviction` → `position_manager` → `commit`).
- Embeddings via `sentence-transformers` (`config.embedding_model`); embedded text = compact news +
  indicators + state. `flush_due` computes reward from the price cache for episodes with
  `t+1+h ≤ current_t`; `retrieve` filters to `outcome_closed_t ≤ obs.t`. Persist index to disk.

  *Worked reward example* (`h=5`, action=long): enter at `t+1` `P=200.00`; five sessions later
  `P[t+1+h]=206.00` → `forward_return = 206/200 − 1 = +3.0%`. Trailing mean 5-session return
  `μ = +0.5%` (from prices ≤ t). `reward = +1 · (3.0% − 0.5%) = +2.5%`. A long that only matches drift
  (`forward ≈ μ`) → reward ≈ 0 (no free credit); shorting this rise → `−2.5%` (correctly penalized).
- Thesis stored/updated on `open`/`flip`; `days_held` increments on `hold`. Cache agent outputs by
  `(ticker, date, agent)`. Feature flags let the graph conditionally bypass nodes (for Step 5).

**Step 3 class & function skeletons** (structure + intent only — bodies filled in during the step):

```python
# src/memory/store.py — episodic memory (FAISS), point-in-time with DELAYED write
@dataclass
class Episode:
    """One trading memory: the situation, the action taken, and (once known) its reward."""
    t: date                     # decision day
    state_text: str             # day's situation rendered for embedding (Observation.to_memory_text())
    action: int                 # -1 short / 0 flat / +1 long taken at t
    reward: float | None        # drift-demeaned forward return; None until the window closes
    outcome_closed_t: date      # = t+1+h; retrievable only on/after this date


class MemoryStore:
    """Wraps a FAISS index + Episode metadata. Append-only and strictly point-in-time."""

    def __init__(self, config: Config) -> None:
        """Load/create the FAISS index + the pinned embedding model; hold a list of pending episodes."""
        ...

    def stage(self, obs: Observation, action: int) -> None:
        """Record a pending episode for day t (reward unknown). NOT searchable until t+1+h."""
        ...

    def flush_due(self, current_t: date, prices) -> None:
        """For each pending episode whose window has closed (t+1+h <= current_t): compute its reward,
        embed its state_text, and add it to the FAISS index so it becomes retrievable."""
        ...

    def retrieve(self, obs: Observation, k: int) -> list[Episode]:
        """Return the k most similar CLOSED episodes (outcome_closed_t <= obs.t). Empty on cold start."""
        ...

    def _embed(self, text: str) -> list[float]:
        """Text -> 'meaning coordinates' via the pinned model; cached by (ticker, date)."""
        ...

    @staticmethod
    def _reward(action: int, prices, t: date, config: Config) -> float:
        """sign(action) * (forward_return(t,h) - mu); mu = trailing AAPL drift (config.reward_benchmark)."""
        ...


# src/agents/position_manager.py — deterministic hysteresis + risk veto (no LLM)
class PositionManager:
    """Turns the debate's recommendation + calibrated conviction into the next position.
    Pure rule engine; all thresholds come from config."""

    def __init__(self, config: Config) -> None: ...

    def decide(self, stance: ResearchStance, state: PortfolioState, macro: MacroSignal,
               conviction: float, realized_vol: float, drawdown: float,
               disagreement: float) -> TradeDecision:
        """Step 1 (veto first): force flat if realized_vol > vol_cap, drawdown < dd_cap,
           regime risk_off / high macro_risk, or strong signal disagreement.
           Step 2 (else hysteresis on conviction):
             flat        -> open  only if conviction >= tau_enter
             in position -> close if thesis invalid or conviction <= tau_exit
             opposite    -> flip  only if conviction >= tau_flip
             otherwise   -> hold
           Returns TradeDecision(new_position, new_thesis, vetoed, reason)."""
        ...


# src/graph/build_graph.py — per-day LangGraph state machine carrying PortfolioState
class GraphState(TypedDict):
    """The shared, typed 'whiteboard' threaded through one day's nodes (kept minimal)."""
    obs: Observation
    portfolio: PortfolioState
    news: NewsSignal
    macro: MacroSignal
    technical: TechnicalSignal
    memory: MemoryContext
    stance: ResearchStance
    conviction: float
    decision: TradeDecision


def build_graph(config: Config, store: MemoryStore):
    """Wire and compile the graph:
       observe -> [news, macro, technical, memory] (parallel) -> debate -> conviction
       -> position_manager -> commit.  Feature flags can bypass nodes (e.g. no-macro). Returns the app."""
    ...


def run_one_day(app, t: date, portfolio: PortfolioState, store: MemoryStore) -> TradeDecision:
    """Run the graph for day t: build the Observation, execute the nodes, update PortfolioState,
       stage today's episode, and flush episodes whose window has closed. Returns the TradeDecision."""
    ...
```

> The four analyst nodes (News/Macro/Technical/Memory) and the Debate node are the LangChain agents
> from Step 2; LangGraph just orchestrates them and threads `GraphState` across the day and `run_one_day`
> across days. `MemoryAgent.run` wraps `MemoryStore.retrieve` + a short LLM "lesson" summary.

---

### Step 4: Walk-Forward Backtest

#### Objective
With one-day decisions working, we step the system through history. The backtester walks day-by-day
across the 2025–2026 test window, carrying `PortfolioState`, executing each day's `new_position` at the
*next* session (`t+1`), and tracking a real **dollar account starting at \$1,000,000**. Position sizing
is **capped notional**: on entry we deploy `min(\$1M, current equity)` — a fixed \$1M when above water
(rest in cash), all-in when underwater — then hold the shares, mark to market daily, and charge a fee
only when the position changes. The equity curve and metrics are computed from this dollar P&L with a
small **custom loop** (vectorbt's default compounds on full equity and would not honor the cap).

#### Why This Step Matters
This is M4 — the deliverable that produces the headline result: a PnL curve, net of fees, to compare
against baselines. The `t+1` execution rule and fee-on-change accounting are what make the number
honest and trading-realistic. Without this step there is no evidence the system works. Every prior step
feeds in here; everything after measures what comes out.

#### Inputs
- Step 3 (`run_one_day` / compiled graph + memory), Step 1 prices.
- `config`: `test_start/end`, `fee_bps`, `allow_short`, `initial_capital` (= 1_000_000),
  `position_sizing` (= `"capped_notional"`, vs `"full_compounding"` as an ablation).
- `src/backtest/run_backtest.py` stub; `vectorbt` (optional — cross-check on standard metrics only).

#### Outputs
- `run_backtest(config) -> dict`: dollar **equity curve** (starts at \$1M) + metrics (total return,
  Sharpe, Sortino, MaxDD, hit rate, **turnover**, **avg holding period**) — all **net of fees** and
  computed on the fixed \$1M base.
- **Performance chart `results/equity_curve.png`** — strategy value over time plotted against
  **buy & hold AAPL** (both starting at \$1M), with a **stats box on the chart** reporting
  **total return, Sharpe, and MaxDD** for each line, so the headline numbers are readable straight off
  the figure. Buy & hold is computed directly from the price cache (`\$1M × P[t]/P[0]`) as the reference
  line here; the full baseline suite (single-agent, AV-sentiment) comes in Step 5.
- Artifacts under `results/` (gitignored): `results/equity_curve.csv`, `results/metrics.json`,
  `results/decisions_log.csv` (per-day signals + rationale + position).
- **`results/trace.json`** — the structured per-day decision trace that powers the Step-6 web report:
  one record per date with `cum_pnl_strategy`, `cum_pnl_buyhold`, `position`, `action`, `conviction`
  (+ its breakdown), the `news` read, each agent's `{signal/regime, rationale}`, the debate
  `{bull_case, bear_case, thesis_still_valid}`, and the final `{new_position, reason}`.
- `python -m src.main --mode backtest` runs the official test. → F12.
- **Acceptance (M4):** equity-curve chart (strategy vs buy & hold, with Sharpe/return/MDD shown) +
  metrics table, PnL net of fees, execution at `t+1`.

#### Challenges and Risks
- **Execution lookahead.** Day-`t` signal must apply to `t+1`'s return — a classic off-by-one that
  inflates results; assert it in a test.
- **Fee accounting.** Charge only on `new_position ≠ current_position` (a flip turns over double
  notional → double fee); turnover must tie out.
- **Sizing / compounding.** Notional is capped at `min(\$1M, equity)`: above water you're only
  *partially* invested (gains don't fully compound); underwater you're all-in (losses compound).
  Intentional — just don't fall back to vectorbt's full-compounding default by accident.
- **Drawdown convention.** MDD divides by **initial capital (\$1M)**, not the running peak — label it
  as such (it reads deeper than the standard `/peak`, e.g. −24% where `/peak` would say −20%).
- **Runtime/cost.** ~18 months × K-sampled debate = thousands of LLM calls; the `(ticker,date,agent)`
  cache makes the second run free. First run uses the live keys (present).
- **NaN-warmup dates** at the test start must be skipped cleanly.

#### Technical Implementation Details
- **Design pattern: Template Method / loop driver.** A `Backtester` owns the walk-forward loop: each
  trading day `t` → `run_one_day(t)` → on a position change deploy `notional = min(initial_capital,
  equity)` and buy/sell `shares = ±notional / P_exec` → mark-to-market → `memory.flush_due` → advance.
- **Custom dollar P&L loop, not vectorbt's compounding default** (the cap must be honored). vectorbt may
  be used only to cross-check the standard metrics on a toy series. Compute avg holding period from
  position run-lengths. Persist artifacts as CSV/JSON for the notebook (Step 6).
- **Chart (`matplotlib`).** Plot strategy equity and buy & hold AAPL (both from \$1M) on one time axis;
  add a text box (or subtitle) annotating each line's total return, Sharpe, and MaxDD; save to
  `results/equity_curve.png`. A thin `plot_equity(strategy, buy_hold, metrics, out_path)` helper keeps
  it reusable by the Step-6 notebook.
- Add `initial_capital` and `position_sizing` to `config.py`; record the sizing + drawdown convention in
  a `DECISIONS.md` ADR when this step is implemented.

**Metrics — dollar accounting** (`C0 = initial_capital = $1,000,000`; all on the test window, net of fees):

```text
Sizing (capped notional, set at entry, held):
  notional = min(C0, equity_at_entry)      # fixed $1M above water (rest in cash); all-in underwater
  shares   = ±notional / P_entry           # sign = position direction; hold until exit

Daily mark-to-market:
  pnl[t] = shares · (P[t] − P[t−1])
  fee[t] = (fee_bps/1e4) · |Δ notional traded|       # only when the position changes (flip = double)
  E[t]   = E[t−1] + pnl[t] − fee[t]                  # E[0] = C0

Returns (fixed $1M base):
  r[t]         = (E[t] − E[t−1]) / C0
  total_return = E[T] / C0 − 1

Max Drawdown (divided by INITIAL CAPITAL, per convention — not /peak):
  peak$[t] = max(E[0..t])
  dd[t]    = (E[t] − peak$[t]) / C0                  # reads deeper than the standard /peak
  MDD      = min(dd[t])

Risk-adjusted (on r[t]; C0 constant ⇒ equals Sharpe on raw $ P&L, but differs from equity-return Sharpe):
  Sharpe  = mean(r) / std(r)            · √252
  Sortino = mean(r) / std(r | r<0)     · √252

Other: turnover = mean|Δposition|;  avg_holding_period = mean run-length of a non-zero position;
       hit_rate = share of days with r[t] > 0.
```

---

### Step 5: Conviction Calibration, Baselines & Ablations

#### Objective
Now we make the results scientific. First we run the pipeline over the 2022–2024 warm-up window to
populate memory and collect `(z, was_the_decision_correct)` pairs, then fit an isotonic (or Platt)
calibrator that maps raw conviction `z` to an empirical probability of being right — validated with a
reliability diagram. Then we build the comparison scaffolding: the baselines the system must beat
(buy & hold, news-only single agent, pure AV-sentiment) and the ablations that isolate each component's
contribution — each just a different `Config`.

#### Why This Step Matters
This closes the §7.3 conviction loop (so `tau_enter = 0.7` truly means "P(correct) ≈ 70%") and
pre-loads the memory the test period retrieves from — while never reporting warm-up PnL (a pillar of
the anti-lookahead story). The baselines and ablations are the scientific core of the write-up: they
directly answer research questions #1–#3 (does debate help? does memory add alpha? does the
state-aware policy cut turnover and improve risk-adjusted return?). Because every variant is a config
toggle over the same engine, the comparison is clean and credible.

#### Inputs
- Steps 3–4 (runnable pipeline + backtest loop), Step 2 conviction engine.
- `config`: `warmup_start/end`, `alpha/beta`, `w1/w2/w3`, `h`; the ablation feature flags from Step 3.
- `src/eval/calibration.py` (`fit_calibrator`, `reliability_diagram`), `src/eval/ablation.py`,
  `scikit-learn`.

#### Outputs
- Fitted calibrator → `results/calibrator.pkl` (loaded by the PositionManager path);
  `results/reliability_diagram.png`, `results/calibration_report.json`; warm-up-populated FAISS index
  on disk.
- `run_ablations(base_config) -> dict` → comparison table across all variants (full metric set) →
  `results/ablation_table.csv` + `results/ablation_table.md`; per-variant curves in `results/curves/`.
- `python -m src.main --mode ablation`. **Tests:** `tests/test_calibration.py` (isotonic monotonicity +
  reliability) → F15; baseline/ablation checks → F13/F14.
- **Acceptance (M5a):** comparison table + reliability diagram produced.

#### Challenges and Risks
- **Defining "correct".** Tie the hit label to the sign of the drift-demeaned forward return vs. the
  action, consistent with the memory reward.
- **Calibration data volume.** ~750 warm-up days may be thin per bucket; isotonic is robust but watch
  overfitting; Platt as fallback. Calibrate only on warm-up; freeze before touching the test.
- **Config-only ablations.** Each variant must be a flag (`use_memory/use_macro/use_debate/
  use_hysteresis/stateless`), not a code fork; all variants share data, fees, and calibrator.
- **Cost.** Reuse the LLM cache across variants so the suite is cheap after the first full run.
- **(Optional)** spec §7.2 reward-based threshold tuning (grid/Bayesian on Sharpe over warm-up) —
  scope as a stretch.

#### Technical Implementation Details
- `sklearn.isotonic.IsotonicRegression` (primary) or `LogisticRegression` (Platt) on `(z, hit)`,
  wrapped in a small `Calibrator` with `fit`/`predict_proba`/`save`/`load`; `reliability_diagram` bins
  predicted vs. empirical hit rate with `matplotlib`. The PositionManager uses
  `calibrator.predict_proba(z)` when present (fallback to raw `z`).
- The graph builder (Step 3) conditionally includes/bypasses nodes by feature flag (e.g.
  `use_macro=False` skips MacroAgent + its veto). Buy & hold and AV-sentiment baselines are simple
  vectorized strategies straight from the caches (no LLM). Aggregate into a tidy DataFrame → CSV + MD.

---

### Step 6: Reporting & Final DoD (+ non-LLM robustness checks)

> **Scope note:** LLM-backbone robustness (the old "swap to GPT-4o-mini" / research-question-#4
> experiment) is **descoped** — the project's budget is all-free (Groq only) and we are not testing
> model-swap robustness now. Robustness is instead demonstrated through **non-LLM** checks (the ablation
> suite from Step 5 plus a forward-window `h` sensitivity sweep), and the step focuses on packaging the
> results.

#### Objective
Finally we tell the story. We assemble `notebooks/results.ipynb` to render the equity curve,
metrics-vs-baseline table, ablation comparison, and reliability diagram from the saved artifacts; build
the **interactive explainability web report** (`results/report.html`) — a cumulative-PnL chart of the
strategy vs buy & hold where **clicking any day's point reveals why the system decided what it did**
(the news it read, each agent's reasoning, the debate, and the final call); run a light **non-LLM
robustness sweep** (`h ∈ {1,5,10,21}`, spec §7.1); and finalize the README. This is the package a
reviewer reads — and the web report is the concrete payoff of the project's explainability claim (§9).

#### Why This Step Matters
This turns months of plumbing into the portfolio piece and satisfies the project Definition of Done
(spec §13.1). The non-LLM robustness checks show the *results* are not a fluke of one parameter setting
(answering research questions #1–#3 about debate, memory, and the state-aware policy) without paying for
a second LLM provider. Honest framing of limitations (spec §11) is part of the credibility.

#### Inputs
- Steps 2–5, all `results/` artifacts (incl. `results/trace.json` + `results/equity_curve.csv` for the
  web report). `config`: `h` (for the sensitivity sweep) and the ablation feature flags from Step 3.
  `notebooks/results.ipynb` skeleton, `README.md`, `PROGRESS.md`, `features.json`.

#### Outputs
- `results/robustness_h.csv` + `.md` — metrics across `h ∈ {1,5,10,21}` (forward-window sensitivity);
  the ablation table from Step 5 is the other robustness artifact. `tests/test_robustness.py` (the sweep
  runs offline and produces a table) → replaces the old F16 model-sensitivity feature.
- **`results/report.html`** — a single, self-contained interactive web page: a **cumulative-PnL line
  chart (strategy vs buy & hold)** whose daily points are clickable; clicking a day opens a side panel
  showing **that day's decision trace** from `trace.json` — the news read, each agent's signal +
  rationale (News/Macro/Technical/Memory), the Debate's bull/bear/thesis, the conviction, and the final
  decision + reason. Open by double-click; no server needed. → new feature **F18** (explainable report).
- Populated `notebooks/results.ipynb` rendering all figures/tables from saved artifacts (no recompute).
- Final `README.md` (results summary, anti-lookahead commitment, pinned **Groq** model, limitations);
  `features.json` relevant features `passing` with evidence; `PROGRESS.md` updated.
- **Acceptance (project DoD §13.1):** one-command end-to-end run; backtest with fees over 2025–2026;
  PnL/equity curve + metrics vs buy & hold; `test_no_lookahead` green.

#### Challenges and Risks
- **Cost of the sweep.** Re-running with each `h` is cheap because the LLM cache (keyed by
  `(ticker, date, agent)`) is reused — only the memory reward window and write-delay change, not the
  agent calls.
- **Reproducible figures.** The notebook reads `results/*` artifacts, not a re-run, so it renders fast
  and deterministically.
- **Over-claiming.** ~18 months = one regime; report Sharpe with the stated caveat. Keep the notebook,
  README, and `features.json` in agreement (use `update-progress` / `doc_agent`).

#### Technical Implementation Details
- The robustness driver loops over `config` variants (different `h`; the Step-5 ablation flags) and
  reuses the entire pipeline + LLM cache — no new provider, no OpenAI.
- Notebook cells load `metrics.json`, `equity_curve.csv`, `ablation_table.csv`,
  `reliability_diagram.png`, `robustness_h.csv` and plot with `matplotlib`.
- **Web report (`src/eval/report.py::build_report_html`)** — read `equity_curve.csv` + `trace.json`,
  embed both inline into one HTML string, and render with **Plotly loaded from a CDN** (no new Python
  dependency, no server). A Plotly `plotly_click` handler reads the clicked day and writes that record's
  reasoning into a side `<div>`. Keep it deliberately plain (one chart + one panel) — explainability is
  the point, not styling. Self-contained so it can be opened from disk or committed as a sample.
- Add a final acceptance test / `make` target asserting all `results/*` artifacts exist and the DoD
  invariants hold (backtest net of fees, `test_no_lookahead` green). Close out via `update-progress` +
  `feature-status` skills.

---

## Execution discipline

- Build steps **in order**; each ends with its acceptance test green and `make check` passing before
  the next begins (spec §13.2). Use the `planner_agent` → `generator_agent` → `reviewer_agent` →
  `verifier_agent` loop per step, and the `check-lookahead` skill on every data/memory/backtest change.
- After each step: update `features.json` (state + evidence), `PROGRESS.md`, and `DECISIONS.md` for any
  non-obvious choice. Commit a small, atomic checkpoint (the pre-commit hook runs `make check`).
- First live run (Steps 4–5) consumes the Alpha Vantage + Groq keys in `.env`; every subsequent rerun
  is cache-backed and free.
