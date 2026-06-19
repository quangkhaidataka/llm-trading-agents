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
from src.agents.debate import DebateAgent
from src.agents.macro import MacroAgent
from src.agents.news import NewsAgent
from src.agents.technical import TechnicalAgent
from src.data.loaders import get_observation
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    PortfolioState,
    ResearchStance,
    TechnicalSignal,
)

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


# ── DebateAgent (S23) ────────────────────────────────────────────────────────
def _four_signals(cfg: Config):
    """The four analyst signals + a MemoryContext for one fixture day."""
    obs = get_observation("AAPL", MATURE)
    news = NewsAgent(cfg).run(obs, PortfolioState())
    macro = MacroAgent(cfg).run(obs, PortfolioState())
    technical = TechnicalAgent(cfg).run(obs, PortfolioState())
    memory = MemoryContext(
        analogs=["2023-09 launch run-up -> +2.1% abnormal"],
        lesson="Launch-driven optimism has historically held for ~1 week.",
    )
    return obs, news, macro, technical, memory


def test_debate_agent_returns_researchstance(offline_config: Config) -> None:
    obs, news, macro, technical, memory = _four_signals(offline_config)
    out = DebateAgent(offline_config).run(
        obs, PortfolioState(current_position=0), news, macro, technical, memory
    )
    assert isinstance(out, ResearchStance)
    assert out.action in ("hold", "open", "close", "flip")
    assert out.target_direction in (-1, 0, 1)
    assert 0.0 <= out.conviction <= 1.0
    assert out.bull_case and out.bear_case


def test_debate_agent_prefers_hold_when_thesis_valid(offline_config: Config) -> None:
    obs, news, macro, technical, memory = _four_signals(offline_config)
    held = PortfolioState(current_position=1, active_thesis="Launch-driven demand", days_held=3)
    out = DebateAgent(offline_config).run(obs, held, news, macro, technical, memory)
    assert out.action == "hold"
    assert out.thesis_still_valid is True


def test_debate_agent_sample_returns_k_actions(offline_config: Config) -> None:
    obs, news, macro, technical, memory = _four_signals(offline_config)
    state = PortfolioState(current_position=1, active_thesis="x", days_held=2)
    actions = DebateAgent(offline_config).sample(
        obs, state, news, macro, technical, memory, k=offline_config.K
    )
    assert len(actions) == offline_config.K
    assert all(a in ("hold", "open", "close", "flip") for a in actions)
