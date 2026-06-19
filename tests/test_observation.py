"""S12 tests — indicators + the Observation gate (offline, deterministic, fixtures).

Covers: indicators in sane ranges on a mature day; honest NaN on warm-up; the gate's
point-in-time invariant (no news dated > t); the frozen Observation + render/serialize
helpers; and the __post_init__ fail-loud backstop.
"""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError
from datetime import date

import pandas as pd
import pytest

import src.data.loaders as loaders
from config import Config
from src.data.loaders import Observation, compute_indicators, get_observation


def _use(cfg: Config, monkeypatch) -> None:
    monkeypatch.setattr(loaders, "config", cfg)


def _synthetic_prices(n: int) -> pd.DataFrame:
    """Deterministic upward-drifting series with enough history for mature indicators."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series([100.0 + i * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1_000_000},
        index=idx,
    )


def test_compute_indicators_mature_day_is_sane() -> None:
    ind = compute_indicators(_synthetic_prices(60))
    assert 0.0 <= ind["rsi"] <= 100.0
    assert ind["ma20"] > 0 and ind["ma50"] > 0
    assert all(not math.isnan(v) for v in ind.values())


def test_compute_indicators_warmup_is_nan() -> None:
    ind = compute_indicators(_synthetic_prices(5))  # too short for RSI14 / MA20 / MA50
    assert math.isnan(ind["rsi"])
    assert math.isnan(ind["ma50"])


def test_get_observation_offline_contract(monkeypatch) -> None:
    _use(Config(offline=True), monkeypatch)
    t = date(2024, 6, 5)
    obs = get_observation("AAPL", t)

    assert isinstance(obs, Observation)
    # point-in-time invariant: nothing dated after t
    for item in obs.aapl_news + obs.macro_news:
        assert loaders._to_date(item["time_published"]) <= t
    # render + serialize helpers work
    assert isinstance(obs.render_news(), str) and obs.has_news() is True
    assert "RSI=" in obs.render_indicators()
    assert obs.to_dict()["t"] == "2024-06-05"
    assert obs.price == pytest.approx(195.90)


def test_observation_is_frozen(monkeypatch) -> None:
    _use(Config(offline=True), monkeypatch)
    obs = get_observation("AAPL", date(2024, 6, 5))
    with pytest.raises(FrozenInstanceError):
        obs.price = 1.0  # type: ignore[misc]


def test_post_init_rejects_future_news() -> None:
    with pytest.raises(ValueError):
        Observation(
            ticker="AAPL",
            t=date(2024, 6, 1),
            aapl_news=[
                {
                    "title": "x",
                    "summary": "y",
                    "time_published": "20240605T120000",  # after t
                    "relevance": 0.9,
                    "av_sentiment": 0.1,
                }
            ],
            macro_news=[],
            indicators={},
            price=100.0,
            spy_trend=0.0,
        )
