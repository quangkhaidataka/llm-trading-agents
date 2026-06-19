"""S33 tests — LangGraph one-day orchestration (M3 acceptance).

Offline & deterministic (Config(offline=True) → MockLLM + md5 embedder + fixtures, no
network). One day end-to-end yields a valid TradeDecision; PortfolioState carries across
days; memory side effects fire in order (stage(t) then flush_due(t)) and stay point-in-time;
a per-day decision trace is written; ablation flags bypass their nodes.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

import src.data.loaders as loaders
from config import Config
from src.graph.build_graph import build_graph, run_one_day
from src.memory.store import MemoryStore
from src.schemas import PortfolioState, TradeDecision

MATURE = date(2024, 6, 5)


@pytest.fixture
def offline_config(tmp_path, monkeypatch) -> Config:
    cfg = Config(offline=True, log_dir=str(tmp_path))
    monkeypatch.setattr(loaders, "config", cfg)
    return cfg


def test_run_one_day_yields_tradedecision(offline_config: Config) -> None:
    store = MemoryStore(offline_config)
    app = build_graph(offline_config, store)
    portfolio = PortfolioState()

    decision = run_one_day(app, MATURE, portfolio, store)

    assert isinstance(decision, TradeDecision)
    assert decision.new_position in (-1, 0, 1)
    # PortfolioState carried/updated in place for t+1
    assert portfolio.current_position == decision.new_position


def test_writes_per_day_decision_trace(offline_config: Config) -> None:
    store = MemoryStore(offline_config)
    app = build_graph(offline_config, store)
    run_one_day(app, MATURE, PortfolioState(), store)

    trace = f"{offline_config.log_dir}/AAPL_2024-06-05.json"
    with open(trace) as fh:
        rec = json.load(fh)
    assert rec["date"] == "2024-06-05" and rec["ticker"] == "AAPL"
    # full provenance present (the Step-6 report source)
    assert set(rec["agents"]) == {"news", "macro", "technical", "memory"}
    assert "bull_case" in rec["debate"] and "conviction" in rec
    assert rec["decision"]["new_position"] in (-1, 0, 1)


def test_memory_staged_and_point_in_time(offline_config: Config) -> None:
    store = MemoryStore(offline_config)
    app = build_graph(offline_config, store)
    run_one_day(app, MATURE, PortfolioState(), store)

    # stage(t) fired: one pending episode recorded for today...
    assert len(store.pending) == 1
    assert store.pending[0].t == MATURE
    # ...and it is NOT yet retrievable (window has not closed — point-in-time).
    from src.data.loaders import get_observation

    assert store.retrieve(get_observation("AAPL", MATURE), offline_config.k) == []


def test_portfolio_carries_across_two_days(offline_config: Config) -> None:
    store = MemoryStore(offline_config)
    app = build_graph(offline_config, store)
    portfolio = PortfolioState()

    d1 = run_one_day(app, date(2024, 6, 4), portfolio, store)
    d2 = run_one_day(app, date(2024, 6, 5), portfolio, store)

    assert isinstance(d1, TradeDecision) and isinstance(d2, TradeDecision)
    assert len(store.pending) == 2  # both days staged
    assert portfolio.current_position == d2.new_position  # state threaded into day 2


def test_ablation_flags_bypass_nodes(offline_config) -> None:
    # use_macro / use_memory / use_debate off → nodes are bypassed but the day still
    # produces a valid decision over the SAME graph (one Config toggle, no code fork).
    cfg = Config(offline=True, log_dir=offline_config.log_dir,
                 use_macro=False, use_memory=False, use_debate=False)
    store = MemoryStore(cfg)
    app = build_graph(cfg, store)
    decision = run_one_day(app, MATURE, PortfolioState(), store)
    assert isinstance(decision, TradeDecision)
    assert decision.new_position in (-1, 0, 1)
