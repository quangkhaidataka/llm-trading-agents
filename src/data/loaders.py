"""Data layer — the SINGLE point-in-time gate (spec §13.5, §12.1).

INVARIANT: every field returned by `get_observation(ticker, t)` has timestamp
<= t. No other function/agent in the system may touch the full dataframe — they
depend on the `Observation` contract, not on how loading works. Switching
sources (AV -> WRDS) changes only the internal loaders; agents are untouched.

`tests/test_no_lookahead.py` checks exactly one thing: for every t,
get_observation(t) contains no timestamp > t.

S11 implements the three loaders (`load_news`, `load_macro_news`, `load_prices`)
and the `download()` flow. `get_observation` / `compute_indicators` land in S12.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime

from config import config


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


# ── THE SINGLE GATE (S12) ───────────────────────────────────────────────────
def get_observation(ticker: str, t: date) -> Observation:
    """Only this function returns data to the rest of the system.

    Branches on config.offline: fixtures vs Parquet cache. Enforces the
    point-in-time invariant for every field before returning.
    """
    raise NotImplementedError("M1/S12: assemble Observation from the loaders below")


# ── Internal loaders (S11) — called only by get_observation / download ───────
def load_news(ticker: str, t: date) -> list[dict]:
    """AAPL-specific news with time_published <= t, relevance-filtered to
    config.relevance_cutoff, newest first, capped at config.max_news_per_day.

    Online: read_or_fetch(news cache, fetch_news); offline: AAPL_news_sample.json.
    """
    import json

    if config.offline:
        with open(os.path.join(config.fixtures_dir, "AAPL_news_sample.json")) as fh:
            items = json.load(fh)
    else:
        from src.data.alpha_vantage import fetch_news
        from src.data.cache import read_or_fetch

        df = read_or_fetch(config.news_cache_path(), lambda: fetch_news(ticker, config))
        items = df.to_dict("records")

    kept = [
        it
        for it in items
        if _to_date(it["time_published"]) <= t
        and float(it.get("relevance", 0.0)) >= config.relevance_cutoff
    ]
    kept.sort(key=lambda it: it["time_published"], reverse=True)
    return kept[: config.max_news_per_day]


def load_macro_news(topics, t: date) -> list[dict]:
    """Macro news fetched BY TOPIC, time_published <= t, newest first, capped at
    config.max_news_per_day. The relevance filter is NOT applied here (spec §2.1) —
    that would drop Fed/geopolitical news a ticker-only design misses.

    Online: read_or_fetch(macro cache, fetch_macro_news); offline: macro_news_sample.json.
    """
    import json

    if config.offline:
        with open(os.path.join(config.fixtures_dir, "macro_news_sample.json")) as fh:
            items = json.load(fh)
    else:
        from src.data.alpha_vantage import fetch_macro_news
        from src.data.cache import read_or_fetch

        df = read_or_fetch(config.macro_cache_path(), lambda: fetch_macro_news(tuple(topics), config))
        items = df.to_dict("records")

    kept = [it for it in items if _to_date(it["time_published"]) <= t]
    kept.sort(key=lambda it: it["time_published"], reverse=True)
    return kept[: config.max_news_per_day]


def load_prices(ticker: str, until_t: date):
    """Daily adjusted OHLCV up to and including t (DataFrame indexed by date).

    Online: read_or_fetch(data/{symbol}_prices.parquet, fetch_prices); offline:
    fixtures/prices_sample.csv (SPY rebuilt from its spy_close column). The frame is
    sliced to rows <= t BEFORE it is returned (no future rows ever leave this layer).
    """
    import pandas as pd

    if config.offline:
        df = pd.read_csv(os.path.join(config.fixtures_dir, "prices_sample.csv"), parse_dates=["date"])
        if ticker == config.benchmark:
            df = df[["date", "spy_close"]].rename(columns={"spy_close": "close"})
        else:
            df = df[["date", "open", "high", "low", "close", "volume"]]
    else:
        from src.data.cache import read_or_fetch
        from src.data.yahoo import fetch_prices

        path = os.path.join(config.cache_dir, f"{ticker}_prices.parquet")
        df = read_or_fetch(path, lambda: fetch_prices(ticker, config))
        df["date"] = pd.to_datetime(df["date"])

    df = df.set_index("date").sort_index()
    return df.loc[: pd.Timestamp(until_t)]


def compute_indicators(prices_until_t) -> dict:
    """RSI(14), MACD, MA20/50, 20d realized vol, momentum — deterministic (ta).

    No shift(-1); rolling functions must not pull future rows (spec §12.1).
    """
    raise NotImplementedError("M1/S12")


# ── Download flow (S11) — warm caches once, print a point-in-time snapshot ────
def download() -> None:
    """Warm all four caches (online) or read fixtures (offline) via the loaders, then
    print a point-in-time DATA SNAPSHOT for a sample date as proof of life.

    NOTE: this prints the *inputs* an Observation is built from (news/macro/price); the
    full rendered Observation (with indicators) prints in S12 once get_observation exists.
    """
    test_end = date.fromisoformat(config.test_end)
    prices = load_prices(config.ticker, test_end)          # warms AAPL price cache
    load_prices(config.benchmark, test_end)                # warms SPY price cache
    sample_t = prices.index.max().date()
    news = load_news(config.ticker, sample_t)              # warms news cache
    macro = load_macro_news(config.macro_topics, sample_t)  # warms macro cache
    close_at_t = float(prices["close"].iloc[-1])

    mode = "offline (fixtures)" if config.offline else "online (live → Parquet cache)"
    print(f"[download] mode={mode}  ticker={config.ticker}")
    print(f"[download] S11 data snapshot (Observation inputs; full Observation in S12)")
    print(f"[download] sample date t={sample_t}  price rows <= t: {len(prices)}  close@t: {close_at_t:.2f}")
    print(f"[download] AAPL news (relevance>= {config.relevance_cutoff}, <= t): {len(news)} item(s)")
    for it in news[:3]:
        print(f"    - {it['time_published']}  rel={float(it['relevance']):.2f}  {it['title']}")
    print(f"[download] macro news (by topic, never relevance-filtered, <= t): {len(macro)} item(s)")
    for it in macro[:3]:
        print(f"    - {it['time_published']}  {it['title']}")


def _to_date(time_published: str) -> date:
    """Parse AV / fixture `YYYYMMDDTHHMMSS` to a date (day granularity for the gate)."""
    return datetime.strptime(time_published[:8], "%Y%m%d").date()
