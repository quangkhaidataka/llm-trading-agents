"""S31 tests — MemoryStore point-in-time delayed write + drift-demeaned reward.

Offline & deterministic (Config(offline=True) → hash embedder, no torch). FAISS is real.
Asserts the anti-leak invariant: an episode staged for t is retrievable ONLY at t+1+h.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from config import Config
from src.data.loaders import Observation
from src.memory.store import MemoryStore


def _prices(values: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.DataFrame({"close": values}, index=idx)


def _obs(t: date, price: float = 100.0) -> Observation:
    return Observation(
        ticker="AAPL", t=t, aapl_news=[], macro_news=[], indicators={},
        price=price, spy_trend=0.0,
    )


def test_cold_start_returns_empty() -> None:
    store = MemoryStore(Config(offline=True))
    assert store.retrieve(_obs(date(2024, 6, 5)), k=5) == []


def test_delayed_write_retrievable_only_at_t_plus_1_plus_h() -> None:
    cfg = Config(offline=True)
    h = cfg.h
    store = MemoryStore(cfg)
    prices = _prices([100.0 + i for i in range(40)])
    days = [ts.date() for ts in prices.index]
    t0 = days[5]

    store.stage(_obs(t0), action=1)

    # On t0 .. t0+h the window has NOT closed → still pending, nothing retrievable.
    for j in range(h + 1):
        cur = days[5 + j]
        store.flush_due(cur, prices)
        assert store.retrieve(_obs(cur), k=cfg.k) == [], f"leaked before close at offset {j}"

    # At t0+1+h the window closes → exactly now it becomes retrievable.
    close_day = days[5 + 1 + h]
    store.flush_due(close_day, prices)
    got = store.retrieve(_obs(close_day), k=cfg.k)
    assert len(got) == 1
    assert got[0].action == 1
    assert got[0].reward is not None
    assert got[0].outcome_closed_t == close_day


def test_persistence_roundtrip_warms_a_fresh_store(tmp_path) -> None:
    """A2 (ADR-023): save() the warmed FAISS index + episodes, then a FRESH store load()s them and
    can retrieve the same closed episode — i.e. warm-up memory survives into a separate process."""
    cfg = Config(offline=True)
    h = cfg.h
    store = MemoryStore(cfg)
    prices = _prices([100.0 + i for i in range(40)])
    days = [ts.date() for ts in prices.index]

    store.stage(_obs(days[5]), action=1)
    close_day = days[5 + 1 + h]
    store.flush_due(close_day, prices)            # closes + indexes the episode
    assert store.index is not None and store.index.ntotal == 1

    mem_dir = str(tmp_path / "mem")
    store.save(mem_dir)

    warm = MemoryStore(cfg).load(mem_dir)          # a fresh process inherits the warmed memory
    assert warm.index is not None and warm.index.ntotal == 1
    assert len(warm.closed) == 1
    got = warm.retrieve(_obs(close_day), k=cfg.k)
    assert len(got) == 1 and got[0].action == 1 and got[0].outcome_closed_t == close_day


def test_load_is_noop_when_absent() -> None:
    """No persisted memory on disk → load() is a clean no-op (cold start preserved)."""
    store = MemoryStore(Config(offline=True)).load("/nonexistent/path/xyz")
    assert store.index is None and store.closed == []


def test_reward_long_beats_short_same_situation() -> None:
    cfg = Config(offline=True)  # aapl_drift
    # 21 flat sessions (mu ≈ 0) then a rising tail → forward_return > 0 at t = day 20.
    vals = [100.0] * 21 + [100.0 * (1.02 ** i) for i in range(1, 10)]
    prices = _prices(vals)
    t = prices.index[20].date()
    long_reward = MemoryStore._reward(1, prices, t, cfg)
    short_reward = MemoryStore._reward(-1, prices, t, cfg)
    flat_reward = MemoryStore._reward(0, prices, t, cfg)
    assert long_reward > 0 > short_reward
    assert long_reward == pytest.approx(-short_reward)  # symmetric in sign(action)
    assert flat_reward == 0.0  # sign(0) = 0


def test_reward_matching_drift_is_zero() -> None:
    cfg = Config(offline=True)
    # Constant +1%/session: every h-window return equals mu → forward_return - mu = 0.
    vals = [100.0 * (1.01 ** i) for i in range(40)]
    prices = _prices(vals)
    t = prices.index[25].date()
    assert MemoryStore._reward(1, prices, t, cfg) == pytest.approx(0.0, abs=1e-9)
