"""S22 tests — the three analyst agents (offline, deterministic, fixtures only).

Each agent's run(obs, state) returns its correct Pydantic schema with valid/in-range
fields on a fixture day; the NewsAgent short-circuits a no-news day to a flat, no-edge
signal. All run under Config(offline=True) → MockLLM + fixtures (no keys/network).
"""

from __future__ import annotations

from datetime import date

import pytest

import src.data.loaders as loaders
from config import Config
from src.agents.macro import MacroAgent
from src.agents.news import NewsAgent
from src.agents.technical import TechnicalAgent
from src.data.loaders import get_observation
from src.schemas import MacroSignal, NewsSignal, PortfolioState, TechnicalSignal

MATURE = date(2024, 6, 5)       # post-warm-up day with AAPL + macro news
NO_NEWS = date(2024, 4, 15)     # only the 0.21-relevance item exists → filtered out → empty


@pytest.fixture
def offline_config(monkeypatch) -> Config:
    cfg = Config(offline=True)
    monkeypatch.setattr(loaders, "config", cfg)
    return cfg


def test_news_agent_returns_newssignal(offline_config: Config) -> None:
    obs = get_observation("AAPL", MATURE)
    out = NewsAgent(offline_config).run(obs, PortfolioState())
    assert isinstance(out, NewsSignal)
    assert out.signal in ("long", "flat", "short")
    assert 0.0 <= out.confidence <= 1.0
    assert -1.0 <= out.sentiment <= 1.0
    assert out.rationale  # reason-first field is populated


def test_news_agent_empty_day_is_flat(offline_config: Config) -> None:
    obs = get_observation("AAPL", NO_NEWS)
    assert not obs.has_news()  # precondition: no qualifying AAPL news <= t
    out = NewsAgent(offline_config).run(obs, PortfolioState())
    assert out.signal == "flat"
    assert abs(out.sentiment) < 1e-9
    assert out.confidence <= 0.5  # no-edge default, not a confident call


def test_macro_agent_returns_macrosignal(offline_config: Config) -> None:
    obs = get_observation("AAPL", MATURE)
    out = MacroAgent(offline_config).run(obs, PortfolioState())
    assert isinstance(out, MacroSignal)
    assert out.regime in ("risk_on", "neutral", "risk_off")
    assert 0.0 <= out.macro_risk <= 1.0
    assert isinstance(out.drivers, list)
    # channel hygiene: MacroSignal carries no per-asset signal field at all
    assert not hasattr(out, "signal")


def test_technical_agent_returns_technicalsignal(offline_config: Config) -> None:
    obs = get_observation("AAPL", MATURE)
    out = TechnicalAgent(offline_config).run(obs, PortfolioState())
    assert isinstance(out, TechnicalSignal)
    assert out.signal in ("long", "flat", "short")
    assert 0.0 <= out.confidence <= 1.0
    assert out.rationale
