"""Scaffold smoke tests (M0) — prove config + schemas import and behave.

These do NOT test business logic (none exists yet); they verify the harness is
wired: config loads, schemas validate, and the ticker-dynamic invariant holds.
"""

from __future__ import annotations

from config import Config
from src.schemas import NewsSignal, PortfolioState, TradeDecision


def test_config_defaults() -> None:
    c = Config()
    assert c.ticker == "AAPL"
    assert c.benchmark == "SPY"
    assert 0.0 <= c.tau_exit < c.tau_enter < c.tau_flip <= 1.0  # hysteresis ordering


def test_ticker_is_dynamic() -> None:
    """Cache paths derive from config.ticker — no hardcoded 'AAPL' (spec §12.5)."""
    amzn = Config(ticker="AMZN")
    assert "AMZN" in amzn.news_cache_path()
    assert "AAPL" not in amzn.news_cache_path()


def test_portfolio_state_defaults_to_flat() -> None:
    s = PortfolioState()
    assert s.current_position == 0
    assert s.active_thesis == ""
    assert s.days_held == 0


def test_schema_validation_round_trips() -> None:
    sig = NewsSignal(signal="long", confidence=0.6, sentiment=0.2, rationale="ok")
    assert sig.signal == "long"
    decision = TradeDecision(new_position=1, new_thesis="t", vetoed=False, reason="r")
    assert decision.new_position == 1
