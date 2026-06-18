"""yfinance adapter — PRICES ONLY, no API key (Adapter pattern, S11).

The price tap for AAPL + SPY. Deliberately separated from the news tap so the scarce
Alpha Vantage request budget is spent only on news while prices stay free and key-less.
yfinance is an unofficial scraper, so we pin it and freeze its output to Parquet.
"""

from __future__ import annotations

import pandas as pd

from config import Config


def fetch_prices(symbol: str, config: Config) -> pd.DataFrame:
    """`yfinance.download(symbol, start=warmup_start, end=test_end, auto_adjust=True)`.

    Returns adjusted OHLCV with lowercase columns [date, open, high, low, close, volume].
    """
    import yfinance as yf

    raw = yf.download(
        symbol,
        start=config.warmup_start,
        end=config.test_end,
        auto_adjust=True,
        progress=False,
    )
    # Newer yfinance returns a column MultiIndex even for a single symbol — flatten it.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    raw.columns = [str(c).lower() for c in raw.columns]
    cols = ["date", "open", "high", "low", "close", "volume"]
    return raw[[c for c in cols if c in raw.columns]]
