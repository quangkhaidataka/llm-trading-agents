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


@dataclass(frozen=True)
class Observation:
    """Immutable, point-in-time snapshot of everything the system may know on day t.

    Built ONLY by get_observation(ticker, t); every field is guaranteed <= t.
    Agents depend on this contract, not on how data was loaded.
    """

    ticker: str
    t: date
    aapl_news: list[dict]        # [{title, summary, time_published, relevance, av_sentiment}]
    macro_news: list[dict]       # macro news by topic (not ticker-tagged)
    indicators: dict             # {rsi, macd, ma20, ma50, vol20, mom} computed up to t
    price: float                 # close at t (valuation only; execution at t+1)
    spy_trend: float             # SPY trend up to t
    rate_change: float | None = None   # (stretch) Fed funds / treasury change

    def __post_init__(self) -> None:
        """Fail-loud backstop: raise if any news item is dated after `t` (a future
        regression cannot quietly leak tomorrow into today)."""
        for item in self.aapl_news:
            if _to_date(item["time_published"]) > self.t:
                raise ValueError(f"future-dated AAPL news: {item['time_published']} > {self.t}")
        for item in self.macro_news:
            if _to_date(item["time_published"]) > self.t:
                raise ValueError(f"future-dated macro news: {item['time_published']} > {self.t}")

    def render_news(self, max_items: int | None = None) -> str:
        """AAPL news block ('title — summary' per line, newest first, capped) for the
        NewsAgent prompt; aapl_news is already relevance-filtered and newest-first."""
        cap = max_items if max_items is not None else config.max_news_per_day
        lines = [f"{it['title']} — {it['summary']}" for it in self.aapl_news[:cap]]
        return "\n".join(lines) if lines else "(no relevant news)"

    def render_macro(self) -> str:
        """Macro headlines block for the MacroAgent. Macro news is NEVER relevance-
        filtered — channel hygiene (idiosyncratic vs systematic)."""
        lines = [f"{it['title']} — {it['summary']}" for it in self.macro_news]
        return "\n".join(lines) if lines else "(no macro news)"

    def render_indicators(self) -> str:
        """Indicators as labeled text for the TechnicalAgent (interprets, never computes)."""
        i = self.indicators
        return (
            f"RSI={_fmt(i.get('rsi'))} MACD={_fmt(i.get('macd'))} "
            f"MA20={_fmt(i.get('ma20'))} MA50={_fmt(i.get('ma50'))} "
            f"vol20={_fmt(i.get('vol20'))} mom={_fmt(i.get('mom'))}"
        )

    def to_memory_text(self) -> str:
        """Compact text (market state + indicators + news gist) the MemoryStore embeds."""
        return (
            f"date={self.t.isoformat()} price={self.price:.2f} spy_trend={self.spy_trend:+.3f}\n"
            f"indicators: {self.render_indicators()}\n"
            f"news: {self.render_news(3)}"
        )

    def has_news(self) -> bool:
        """True if any AAPL news exists today (agents degrade gracefully on quiet days)."""
        return len(self.aapl_news) > 0

    def to_dict(self) -> dict:
        """JSON-serializable view for the per-day decision log / (ticker, date) cache."""
        return {
            "ticker": self.ticker,
            "t": self.t.isoformat(),
            "price": self.price,
            "spy_trend": self.spy_trend,
            "indicators": self.indicators,
            "aapl_news_count": len(self.aapl_news),
            "macro_news_count": len(self.macro_news),
            "rate_change": self.rate_change,
        }


# ── THE SINGLE GATE (S12) ───────────────────────────────────────────────────
def get_observation(ticker: str, t: date) -> Observation:
    """THE single point-in-time gate — the ONLY function that returns data to the rest
    of the system. Assembles an Observation in which every field is <= t (the loaders
    slice to <= t; compute_indicators runs only on those past rows)."""
    prices = load_prices(ticker, until_t=t)               # sliced <= t
    spy = load_prices(config.benchmark, until_t=t)        # SPY for market context
    indicators = compute_indicators(prices)               # rows <= t only (ta/pandas)
    aapl_news = load_news(ticker, t)                      # relevance-filtered, capped
    macro_news = load_macro_news(config.macro_topics, t)  # by topic, NEVER relevance-filtered
    return Observation(
        ticker=ticker,
        t=t,
        aapl_news=aapl_news,
        macro_news=macro_news,
        indicators=indicators,
        price=float(prices.iloc[-1]["close"]),            # close at t; execution at t+1
        spy_trend=compute_spy_trend(spy),                 # sign/slope of SPY <= t
        rate_change=None,                                 # (stretch) rate move <= t
    )


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
    """RSI, MACD, MA20/50, annualized 20d realized vol, momentum — deterministic (ta + pandas).

    Operates only on the (already <= t) rows passed in. No shift(-1); rolling windows never
    pull future rows. Windows come from config. Warm-up rows yield NaN, surfaced honestly
    (not back-filled). Returns {rsi, macd, ma20, ma50, vol20, mom} as the values at t.
    """
    from ta.momentum import RSIIndicator
    from ta.trend import MACD, SMAIndicator

    close = prices_until_t["close"]
    returns = close.pct_change()
    return {
        "rsi": _last(RSIIndicator(close, window=config.rsi_period).rsi()),
        "macd": _last(MACD(close).macd()),
        "ma20": _last(SMAIndicator(close, window=config.ma_short).sma_indicator()),
        "ma50": _last(SMAIndicator(close, window=config.ma_long).sma_indicator()),
        "vol20": _last(returns.rolling(config.vol_window).std() * (252 ** 0.5)),
        "mom": _last(close.pct_change(config.mom_window)),
    }


def compute_spy_trend(spy) -> float:
    """Market/beta context: SPY's last close relative to its MA20 (>0 uptrend, <0 down),
    using only rows <= t. Returns 0.0 when there is not yet enough history."""
    close = spy["close"]
    ma = close.rolling(config.ma_short).mean()
    last_ma = _last(ma)
    if last_ma != last_ma or last_ma == 0:  # NaN or zero
        return 0.0
    return float((close.iloc[-1] - last_ma) / last_ma)


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


def _last(series) -> float:
    """Value at t (last row) as a float — may be NaN on warm-up (surfaced honestly)."""
    return float(series.iloc[-1]) if len(series) else float("nan")


def _fmt(value: float | None) -> str:
    """Format an indicator value for prompt text; NaN/None -> 'n/a'."""
    if value is None or value != value:  # None or NaN
        return "n/a"
    return f"{value:.2f}"
