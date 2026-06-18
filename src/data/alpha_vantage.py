"""Alpha Vantage adapter — NEWS ONLY (Adapter pattern, S11).

Wraps the messy `NEWS_SENTIMENT` REST endpoint behind clean `fetch_*` signatures:
AV's `YYYYMMDDTHHMMSS` timestamps, string-encoded numbers, and the fact that one
article can mention several tickers (so we dig the {ticker} entry out of
`ticker_sentiment`). News only — prices come key-free from yfinance (see yahoo.py).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from config import Config

_AV_URL = "https://www.alphavantage.co/query"


def fetch_news(ticker: str, config: Config) -> pd.DataFrame:
    """Windowed `NEWS_SENTIMENT&tickers={ticker}` across warmup_start..test_end.

    Columns [title, summary, time_published, relevance, av_sentiment]; the per-item
    {ticker} entry is picked from `ticker_sentiment`; string numerics cast to float.
    """
    rows: list[dict] = []
    for time_from, time_to in _monthly_windows(config.warmup_start, config.test_end):
        data = _get_with_backoff(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "time_from": time_from,
                "time_to": time_to,
                "sort": "LATEST",
                "limit": "1000",
            },
            config,
        )
        for item in data.get("feed", []):
            entry = _ticker_entry(item.get("ticker_sentiment", []), ticker)
            if entry is None:
                continue
            rows.append(
                {
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "time_published": item.get("time_published", ""),
                    "relevance": float(entry.get("relevance_score", 0.0)),
                    "av_sentiment": float(entry.get("ticker_sentiment_score", 0.0)),
                }
            )
    cols = ["title", "summary", "time_published", "relevance", "av_sentiment"]
    df = pd.DataFrame(rows, columns=cols)
    return df.drop_duplicates(subset=["title", "time_published"]).reset_index(drop=True)


def fetch_macro_news(topics: tuple[str, ...], config: Config) -> pd.DataFrame:
    """Windowed `NEWS_SENTIMENT&topics={topics}` (systematic channel).

    Columns [title, summary, time_published, topics]; NEVER relevance-filtered.
    """
    rows: list[dict] = []
    topics_param = ",".join(topics)
    for time_from, time_to in _monthly_windows(config.warmup_start, config.test_end):
        data = _get_with_backoff(
            {
                "function": "NEWS_SENTIMENT",
                "topics": topics_param,
                "time_from": time_from,
                "time_to": time_to,
                "sort": "LATEST",
                "limit": "1000",
            },
            config,
        )
        for item in data.get("feed", []):
            rows.append(
                {
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "time_published": item.get("time_published", ""),
                    "topics": [t.get("topic", "") for t in item.get("topics", [])],
                }
            )
    cols = ["title", "summary", "time_published", "topics"]
    df = pd.DataFrame(rows, columns=cols)
    return df.drop_duplicates(subset=["title", "time_published"]).reset_index(drop=True)


def _ticker_entry(ticker_sentiment: list[dict], ticker: str) -> dict | None:
    """Pick the {ticker} entry out of an item's `ticker_sentiment` array (or None)."""
    for entry in ticker_sentiment:
        if entry.get("ticker") == ticker:
            return entry
    return None


def _monthly_windows(start: str, end: str) -> list[tuple[str, str]]:
    """Month-by-month (time_from, time_to) AV-format windows covering [start, end].

    One request per window keeps the design simple; very dense months may truncate at
    the 1000-item cap (low-relevance overflow we'd drop anyway). start/end are ISO dates.
    """
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    windows: list[tuple[str, str]] = []
    year, month = s.year, s.month
    while (year, month) <= (e.year, e.month):
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        last_day = (date(next_year, next_month, 1) - timedelta(days=1)).day
        windows.append((f"{year:04d}{month:02d}01T0000", f"{year:04d}{month:02d}{last_day:02d}T2359"))
        year, month = next_year, next_month
    return windows


def _get_with_backoff(params: dict, config: Config) -> dict:
    """Single AV GET with retry/backoff against rate limits (free ~25/day, premium 75/min).

    AV signals throttling via a `Note`/`Information` key instead of an HTTP error, so we
    sleep and retry on those. Returns the parsed JSON ({} if it never succeeds).
    """
    import time

    import requests

    query = {**params, "apikey": config.av_api_key}
    delay = 2.0
    for _ in range(5):
        resp = requests.get(_AV_URL, params=query, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "Note" in data or "Information" in data:  # rate-limited / throttled
            time.sleep(delay)
            delay *= 2
            continue
        return data
    return {}
