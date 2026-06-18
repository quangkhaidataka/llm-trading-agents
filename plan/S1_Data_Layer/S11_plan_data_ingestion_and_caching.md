# S1.1 — Data Ingestion & Caching

## Objective
In this sub-step we open the two taps that feed the whole system and we make sure each one only ever
pours once. We build a thin **Alpha Vantage adapter** that fetches *news* (AAPL-specific headlines and
macro-by-topic headlines — and *only* news, because the free tier gives us a scarce 25 requests/day that
we will not waste on prices), and a thin **yfinance adapter** that fetches *prices* (AAPL + SPY adjusted
OHLCV, no API key required). On top of those we put a tiny **cache helper** (`read_or_fetch`) that writes
the result to Parquet exactly once and reads from disk forever after. Finally we implement the three
**Repository loaders** (`load_news`, `load_macro_news`, `load_prices`) that decide — based on
`config.offline` — whether to call the live adapters or read the bundled fixtures, and we wire the
`python -m src.main --mode download` flow that triggers the one-time live download and prints a single
rendered `Observation` as proof of life. After this sub-step, every byte the system will ever reason
about lives on disk in a clean, point-in-time-sliceable shape.

## Inputs and Outputs
**Inputs**
- `ALPHAVANTAGE_API_KEY` from `.env` (news only) — read via `config.av_api_key`.
- `config` knobs: `ticker`, `benchmark`, `warmup_start`, `test_end`, `macro_topics`,
  `relevance_cutoff`, `max_news_per_day`, `cache_dir`, `fixtures_dir`, `offline`.
- AV REST endpoints (news): `NEWS_SENTIMENT&tickers={ticker}` and `NEWS_SENTIMENT&topics={topics}`.
- yfinance: `yfinance.download(symbol, start, end, auto_adjust=True)` for AAPL and SPY.
- Offline fixtures: `fixtures/AAPL_news_sample.json`, `fixtures/macro_news_sample.json`,
  `fixtures/prices_sample.csv` (columns `date,open,high,low,close,volume,spy_close`).
- New dependency: `yfinance==0.2.x` (pinned) + `python-dateutil` added to `requirements.txt`.

**Outputs (artifacts — all under `config.cache_dir` = `data/`, all gitignored)**
- `data/{ticker}_news.parquet` — Parquet; columns `title, summary, time_published, relevance,
  av_sentiment` (string numerics cast to float; the AAPL entry picked out of each item's
  `ticker_sentiment`).
- `data/macro_news.parquet` — Parquet; columns `title, summary, time_published, topics`
  (**never relevance-filtered**).
- `data/{ticker}_prices.parquet` and `data/SPY_prices.parquet` — Parquet; adjusted OHLCV with
  lowercase columns `date, open, high, low, close, volume`.
- New modules: `src/data/alpha_vantage.py`, `src/data/yahoo.py`, `src/data/cache.py`.
- Implemented loaders in `src/data/loaders.py` (`load_news`, `load_macro_news`, `load_prices`).
- `python -m src.main --mode download` writes all four caches and prints one rendered `Observation`.

## Skeleton Python Code
```python
# ── src/data/cache.py ───────────────────────────────────────────────────────
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd


def read_or_fetch(path: str, fetch_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Idempotent cache: return the Parquet at `path` if it exists, else call
    `fetch_fn()`, write the result to Parquet (pyarrow), and return it."""
    ...


# ── src/data/alpha_vantage.py  (Adapter over AV REST — NEWS ONLY) ────────────
from __future__ import annotations

import pandas as pd

from config import Config


def fetch_news(ticker: str, config: Config) -> pd.DataFrame:
    """Windowed NEWS_SENTIMENT&tickers={ticker} pulls across warmup_start..test_end.
    Returns columns [title, summary, time_published, relevance, av_sentiment]; the
    per-item AAPL entry is picked from `ticker_sentiment`; string numerics -> float."""
    ...


def fetch_macro_news(topics: tuple[str, ...], config: Config) -> pd.DataFrame:
    """Windowed NEWS_SENTIMENT&topics={topics} pulls (systematic channel).
    Returns [title, summary, time_published, topics]; NEVER relevance-filtered."""
    ...


def _get_with_backoff(params: dict, config: Config) -> dict:
    """Single AV GET with retry/backoff against rate limits (free tier ~25/day)."""
    ...


# ── src/data/yahoo.py  (Adapter over yfinance — PRICES ONLY, no key) ─────────
from __future__ import annotations

import pandas as pd

from config import Config


def fetch_prices(symbol: str, config: Config) -> pd.DataFrame:
    """yfinance.download(symbol, start=warmup_start, end=test_end, auto_adjust=True).
    Returns adjusted OHLCV with lowercase columns [date, open, high, low, close, volume]."""
    ...


# ── src/data/loaders.py  (Repository: online adapter vs offline fixtures) ────
def load_news(ticker: str, t: date) -> list[dict]:
    """AAPL-specific news with time_published <= t; relevance-filtered to
    config.relevance_cutoff. Online: read_or_fetch(news_cache_path, fetch_news);
    offline: read fixtures/AAPL_news_sample.json. Slice <= t BEFORE returning."""
    ...


def load_macro_news(topics, t: date) -> list[dict]:
    """Macro news fetched BY TOPIC, time_published <= t. Online: read_or_fetch(
    macro_cache_path, fetch_macro_news); offline: fixtures/macro_news_sample.json.
    The relevance filter is NOT applied here (spec §2.1)."""
    ...


def load_prices(ticker: str, until_t: date):
    """Daily adjusted OHLCV up to and including t (DataFrame). Online: read_or_fetch(
    price_cache_path / SPY cache, fetch_prices); offline: fixtures/prices_sample.csv
    (SPY rebuilt from its spy_close column). Slice prices.loc[:t] BEFORE any compute."""
    ...
```

## How It Connects
The story flows in one direction, from the outside world to disk and never back. When someone runs
`python -m src.main --mode download`, the entrypoint asks the two **adapters** to pull raw data — but it
asks them through the **cache helper** `read_or_fetch`, which is the gatekeeper that guarantees each
expensive pull happens at most once: if the Parquet file already sits in `data/`, it is read straight
off disk and the network is never touched; otherwise the adapter runs, the clean frame is written to
Parquet, and that file becomes the single source of truth from then on. The Alpha Vantage adapter is the
*news* tap (it knows about AV's quirky `YYYYMMDDTHHMMSS` timestamps, its string-encoded numbers, and the
fact that one article can mention several tickers so we must dig the AAPL entry out of `ticker_sentiment`),
and the yfinance adapter is the *prices* tap for AAPL and SPY — deliberately separated so the scarce AV
request budget is spent only on the heavy news download while prices stay free and key-less. Sitting
above both adapters are the three **Repository loaders**: they are the only callers that know whether we
are online or offline. Online they go through `read_or_fetch`; offline (`config.offline=True`) they read
the bundled fixtures instead, so the entire pipeline runs with no keys and no network. Every loader does
the same final, non-negotiable thing before handing anything back — it slices to rows dated `<= t` — so
that the next sub-step's `get_observation` never even sees a future row. The macro loader is the one
deliberate exception to filtering: it never applies the relevance cutoff, keeping the systematic
(Fed/geopolitical) channel intact and separate from the idiosyncratic AAPL channel.

## Key Technology, Design Patterns & Packages
- **yfinance** (pinned `0.2.x`) — key-free adjusted OHLCV for AAPL + SPY; an unofficial scraper, so we
  pin it and freeze its output to Parquet.
- **requests** — minimal HTTP client for the AV `NEWS_SENTIMENT` endpoints with backoff.
- **pandas + pyarrow** — in-memory frames and the Parquet read/write that backs the cache.
- **python-dateutil** — robust parsing of AV's `YYYYMMDDTHHMMSS` timestamps (US/Eastern → date).
- **Adapter pattern** (`alpha_vantage.py`, `yahoo.py`) — each wraps one messy external source behind a
  clean `fetch_*` signature, so swapping a source (AV → WRDS) never touches a consumer.
- **Repository pattern** (`load_news/load_macro_news/load_prices`) — the single layer that chooses
  online-adapter vs offline-fixture and returns clean, point-in-time records.
- **Cache-aside / idempotency** (`read_or_fetch`) — pull once, read forever; makes reruns free and
  deterministic.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m src.main --mode download --offline` runs clean and
      prints one rendered `Observation`; `make test` green.
- [ ] **Tests:** loader tests for `load_news` / `load_macro_news` / `load_prices` and `read_or_fetch`
      pass under `Config(offline=True)` (fixtures only, no keys/network); each loader slices `<= t`
      before returning; `read_or_fetch` is idempotent (second call hits disk, never the adapter).
- [ ] **Gate:** `make check` green (ruff + mypy + pytest unit + e2e); no new lint/type errors.
- [ ] **features.json:** `F03` → `passing` with evidence (commit hash / passing
      `--mode download --offline` run).
- [ ] **Artifacts:** online run writes `data/{ticker}_news.parquet`, `data/macro_news.parquet`,
      `data/{ticker}_prices.parquet`, `data/SPY_prices.parquet` (Parquet, lowercase OHLCV cols).
- [ ] **Rules:** point-in-time slice `<= t` in every loader; macro news **never** relevance-filtered;
      AV used for news only (price stays key-free yfinance); ticker-dynamic (no hardcoded `AAPL`);
      all knobs (`relevance_cutoff`, `max_news_per_day`, `cache_dir`, ...) in `config.py`, not inline;
      offline parity (online cache and offline fixtures yield the same shape).
- [ ] **Tracking:** `PROGRESS.md` updated; `DECISIONS.md` ADR for the AV-news / yfinance-prices split;
      any new config knobs (e.g. `cache_dir`, `fixtures_dir`) recorded.
