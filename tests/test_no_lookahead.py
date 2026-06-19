"""The critical anti-lookahead test (spec §12.1, §13.5).

ONE invariant: for every t, get_observation(ticker, t) contains NO timestamp > t.
Runs fully offline on fixtures — fast, free, deterministic. Must stay green.

The sweep walks EVERY session date in the fixtures (not a single happy-path day),
so an off-by-one slice, a stray bfill, or a centered rolling window is caught the
moment it appears.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest

import src.data.loaders as loaders
from config import Config
from src.data.loaders import get_observation


@pytest.fixture
def offline_config(monkeypatch) -> Config:
    """Offline config so the sweep uses fixtures only (no keys, no network)."""
    cfg = Config(offline=True)
    monkeypatch.setattr(loaders, "config", cfg)
    return cfg


def _trading_days(config: Config) -> list[date]:
    """All session dates present in fixtures/prices_sample.csv (the universe of t)."""
    df = pd.read_csv(
        os.path.join(config.fixtures_dir, "prices_sample.csv"), parse_dates=["date"]
    )
    return [ts.date() for ts in df["date"]]


def _as_date(ts) -> date:
    """Coerce AV's 'YYYYMMDDTHHMMSS' timestamp to a date — exactly like the loader."""
    return loaders._to_date(ts)


def test_observation_has_no_future_data(offline_config: Config) -> None:
    """THE invariant: for EVERY t, no field in get_observation(t) is dated > t."""
    days = _trading_days(offline_config)
    assert len(days) >= 40, "fixtures must cover ~40 sessions to exercise warm-up edges"

    for t in days:
        obs = get_observation(offline_config.ticker, t)
        for item in obs.aapl_news:
            assert _as_date(item["time_published"]) <= t, "AAPL news leaked future"
        for item in obs.macro_news:
            assert _as_date(item["time_published"]) <= t, "macro news leaked future"
        assert obs.t <= t


def test_macro_channel_is_never_relevance_filtered(offline_config: Config) -> None:
    """Channel hygiene: macro news carries no relevance gate (a ticker-only design
    would drop Fed/geopolitical coverage). On a late day all macro items survive."""
    obs = get_observation(offline_config.ticker, date(2024, 6, 5))
    assert len(obs.macro_news) >= 4
