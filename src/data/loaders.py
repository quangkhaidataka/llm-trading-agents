"""Data layer — the SINGLE point-in-time gate (spec §13.5, §12.1).

INVARIANT: every field returned by `get_observation(ticker, t)` has timestamp
<= t. No other function/agent in the system may touch the full dataframe — they
depend on the `Observation` contract, not on how loading works. Switching
sources (AV -> WRDS) changes only the internal loaders; agents are untouched.

`tests/test_no_lookahead.py` checks exactly one thing: for every t,
get_observation(t) contains no timestamp > t.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Observation:
    """Point-in-time snapshot for day t. Every field is <= t."""

    ticker: str
    t: date
    aapl_news: list[dict]        # [{title, summary, time_published, relevance, av_sentiment}]
    macro_news: list[dict]       # macro news by topic (not ticker-tagged)
    indicators: dict             # {rsi, macd, ma20, ma50, vol20, mom} computed up to t
    price: float                 # close at t (valuation only; execution at t+1)
    spy_trend: float             # SPY trend up to t
    rate_change: float | None = None   # (stretch) Fed funds / treasury change


# ── THE SINGLE GATE ─────────────────────────────────────────────────────────
def get_observation(ticker: str, t: date) -> Observation:
    """Only this function returns data to the rest of the system.

    Branches on config.offline: fixtures vs Parquet cache. Enforces the
    point-in-time invariant for every field before returning.
    """
    raise NotImplementedError("M1: assemble Observation from the loaders below")


# ── Internal loaders (called ONLY by get_observation) ───────────────────────
def load_news(ticker: str, t: date) -> list[dict]:
    """AAPL-specific news with time_published <= t; relevance-filtered."""
    raise NotImplementedError("M1")


def load_macro_news(topics, t: date) -> list[dict]:
    """Macro news fetched BY TOPIC (not ticker), time_published <= t.

    The relevance filter must NOT be applied here (spec §2.1) — that would drop
    Fed/geopolitical news a ticker-only design misses.
    """
    raise NotImplementedError("M1")


def load_prices(ticker: str, until_t: date):
    """Daily adjusted OHLCV up to and including t. Returns a DataFrame."""
    raise NotImplementedError("M1")


def compute_indicators(prices_until_t) -> dict:
    """RSI(14), MACD, MA20/50, 20d realized vol, momentum — deterministic (ta).

    No shift(-1); rolling functions must not pull future rows (spec §12.1).
    """
    raise NotImplementedError("M1")
