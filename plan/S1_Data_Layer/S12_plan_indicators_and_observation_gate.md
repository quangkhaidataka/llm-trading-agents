# S1.2 — Indicators & The Observation Gate

## Objective
In this sub-step we build the brain-food and the single doorway that serves it. First we turn raw prices
into a small, deterministic set of **technical indicators** — RSI(14), MACD, MA20, MA50, 20-day realized
volatility, and momentum — computed with the `ta` library and plain pandas, always on rows sliced
`<= t`, and never with a forbidden `shift(-1)` or a centered/forward-looking window. Then we freeze the
**`Observation` dataclass**: an immutable snapshot of *everything the system is allowed to know on day
`t`*, with helper methods that render news/indicators into prompt-ready text, build the memory key, and
serialize for logging — plus a `__post_init__` that re-asserts the point-in-time invariant as a
fail-loud backstop. Finally we assemble the one and only **`get_observation(ticker, t)` gate** that
calls the loaders, computes the indicators, derives the SPY trend, and packs it all into that frozen
`Observation`. This is the single point-in-time doorway: nothing downstream ever touches a dataframe,
an API, or a future row — it only sees the `Observation` this gate returns.

## Inputs and Outputs
**Inputs**
- The loaders from S1.1 (`load_prices`, `load_news`, `load_macro_news`) — already sliced `<= t`.
- `config` knobs: indicator windows `rsi_period=14`, `ma_short=20`, `ma_long=50`, `vol_window=20`,
  `mom_window=10` (added to `config.py` in this sub-step, never inline); plus `ticker`, `benchmark`,
  `macro_topics`, `max_news_per_day`, `relevance_cutoff`.
- `src/data/loaders.py` skeletons (`Observation`, `get_observation`, `compute_indicators`).

**Outputs**
- Implemented `compute_indicators(prices_until_t) -> dict` returning `{rsi, macd, ma20, ma50, vol20,
  mom}` from rows `<= t` only (no in-memory artifact; values flow into the `Observation`).
- The frozen `Observation` dataclass with all render/memory/introspection methods + `__post_init__`.
- A small `compute_spy_trend(spy) -> float` helper (sign/slope of SPY up to `t`).
- The `get_observation(ticker, t) -> Observation` gate — the only public entry. Its serialized form
  (`Observation.to_dict()`) is JSON, written later to the per-day decision log (`config.log_dir`).

## Skeleton Python Code
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config import config


def compute_indicators(prices_until_t) -> dict:
    """RSI(14), MACD, MA20/50, 20d realized vol, momentum — deterministic (ta + pandas).
    Operates ONLY on rows <= t (caller already sliced). No shift(-1); rolling windows
    never pull future rows. Windows come from config. Returns {rsi, macd, ma20, ma50,
    vol20, mom}; warm-up rows yield NaN, surfaced honestly (not back-filled)."""
    ...


def compute_spy_trend(spy) -> float:
    """Market/beta context: the sign/slope of the SPY trend using rows <= t only
    (e.g. last close vs its MA). Pure read of already-sliced data; no future rows."""
    ...


@dataclass(frozen=True)
class Observation:
    """Immutable, point-in-time snapshot of everything the system may know on day t.

    Built ONLY by get_observation(ticker, t); every field is guaranteed <= t.
    Agents depend on this contract, not on how data was loaded."""

    ticker: str                       # asset under management (config.ticker)
    t: date                           # the decision date ("today")
    aapl_news: list[dict]             # idiosyncratic AAPL news {title, summary, time_published, relevance, av_sentiment}
    macro_news: list[dict]            # systematic macro-by-topic news {title, summary, time_published, topics}
    indicators: dict                  # precomputed TA {rsi, macd, ma20, ma50, vol20, mom}
    price: float                      # adjusted close at t (valuation only; execution at t+1)
    spy_trend: float                  # SPY trend signal up to t (market/beta context)
    rate_change: float | None = None  # (stretch) Fed funds / treasury yield change up to t

    def __post_init__(self) -> None:
        """Fail-loud backstop: assert no news item is dated after `t` and required
        fields are present; raise ValueError on any future-dated record."""
        ...

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

    def to_memory_text(self) -> str:
        """Build the compact text (news gist + indicators + market context) that
        MemoryStore embeds as the retrieval key for this day's episode."""
        ...

    def has_news(self) -> bool:
        """True if any AAPL news exists today, so agents can degrade gracefully
        (flat, low confidence) on empty-news days instead of hallucinating."""
        ...

    def to_dict(self) -> dict:
        """JSON-serializable view (t as isoformat, indicator values, price, news
        counts) for the per-day decision log and the (ticker, date) cache."""
        ...


def get_observation(ticker: str, t: date) -> Observation:
    """THE single point-in-time gate — the ONLY function that returns data to the rest
    of the system. Assembles an Observation in which every field is <= t."""
    prices = load_prices(ticker, until_t=t)            # yfinance cache / fixtures, sliced <= t
    spy = load_prices(config.benchmark, until_t=t)     # SPY for market context
    indicators = compute_indicators(prices)            # rows <= t only (ta/pandas)
    aapl_news = load_news(ticker, t)                   # relevance-filtered, capped (idiosyncratic)
    macro_news = load_macro_news(config.macro_topics, t)  # by topic, NEVER relevance-filtered
    spy_trend = compute_spy_trend(spy)                 # sign/slope of SPY <= t
    rate_change = None                                 # (stretch) rate move <= t
    return Observation(
        ticker=ticker,
        t=t,
        aapl_news=aapl_news,
        macro_news=macro_news,
        indicators=indicators,
        price=float(prices.iloc[-1]["close"]),         # close at t; execution at t+1
        spy_trend=spy_trend,
        rate_change=rate_change,
    )
```

## How It Connects
This sub-step is the narrow waist of the whole system: everything wide on the input side funnels through
a single function and comes out as one tidy object. When `get_observation(ticker, t)` is called, it asks
the S1.1 loaders for prices, SPY, AAPL news, and macro news — each already sliced to `<= t` so future
rows are physically absent — then it hands the price frame to `compute_indicators`, which runs RSI, MACD,
the moving averages, realized volatility, and momentum using only those past rows (no `shift(-1)`, no
centered window, so the math itself cannot peek ahead). It derives a simple SPY-trend number for market
context the same way. All of that is packed into the **frozen** `Observation`, whose `__post_init__`
immediately double-checks that not one news item is dated after `t` — a fail-loud guard so that even a
future code regression cannot quietly leak tomorrow into today. From that moment on, the rest of the
system never sees a dataframe or an API again: the analyst agents call `render_news`, `render_macro`, and
`render_indicators` to get prompt-ready text; the memory layer calls `to_memory_text` to build its
retrieval key; the decision log calls `to_dict` to serialize the day; and `has_news` lets agents stay
calm on quiet days instead of inventing signals. One doorway in, one immutable snapshot out — that is the
entire anti-lookahead contract, enforced in one place.

## Key Technology, Design Patterns & Packages
- **ta** (`RSIIndicator`, `MACD`, `SMAIndicator`) — battle-tested indicator math so we don't roll our
  own; windows injected from `config`.
- **pandas** — `rolling(...).std()` for realized vol and `pct_change` for momentum, all on `<= t` slices.
- **Facade pattern** (`get_observation`) — the single public entry point; nothing else touches a full
  frame or a source, so the point-in-time guarantee is inherited for free everywhere.
- **Immutable value object** (`@dataclass(frozen=True)` `Observation`) — a frozen contract agents depend
  on, decoupling consumers from how data was loaded; `__post_init__` is a fail-loud invariant check.
- **Pure functions** (`compute_indicators`, `compute_spy_trend`) — deterministic, side-effect-free, so
  the same `t` always yields the same numbers (reproducible, easy to test).

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_observation.py -q` green, and
      `get_observation(config.ticker, t)` returns a frozen `Observation` whose `render_*`/`to_dict` work.
- [ ] **Tests:** `tests/test_observation.py` green under `Config(offline=True)` (fixtures, no
      keys/network) — indicators in sane ranges on a mature day; warm-up days surface honest `NaN`
      (not back-filled); and the gate upholds the invariant "for every `t`, `get_observation(t)` has no
      timestamp `> t`" (asserted here and re-checked in `Observation.__post_init__`).
- [ ] **Gate:** `make check` green (ruff + mypy + pytest unit + e2e); no new lint/type errors.
- [ ] **features.json:** `F02` (single point-in-time gate) → `passing` with evidence (commit hash /
      passing test); confirmed by `tests/test_no_lookahead.py` in S1.3.
- [ ] **Rules:** indicators computed on rows `<= t` only; **no `shift(-1)`**, no centered/forward
      rolling window; price is valuation-only (execution at `t+1`); macro news never relevance-filtered
      in `render_macro`; indicator windows (`rsi_period`, `ma_short`, `ma_long`, `vol_window`,
      `mom_window`) live in `config.py`, never inline; ticker-dynamic; offline parity.
- [ ] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` ADR if a non-obvious choice (e.g. NaN
      warm-up policy, SPY-trend definition); new indicator-window config knobs recorded.
