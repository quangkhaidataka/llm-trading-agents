"""S11 loader + cache tests — offline, deterministic, fixtures only (no keys/network).

Asserts the point-in-time slice (<= t) in every loader, that macro news is NOT
relevance-filtered, and that read_or_fetch is idempotent (second call hits disk).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import src.data.loaders as loaders
from config import Config
from src.data.cache import read_or_fetch


def _use(cfg: Config, monkeypatch) -> None:
    """Point the loaders' module-level `config` at an offline test config."""
    monkeypatch.setattr(loaders, "config", cfg)


def test_load_news_slices_to_t(monkeypatch) -> None:
    _use(Config(offline=True), monkeypatch)
    # AAPL items <= 2024-06-03 with relevance >= 0.3: 0.92, 0.68, 0.74, 0.81, 0.77, 0.95
    # (the 0.18 and 0.21 items are dropped by the cutoff).
    assert len(loaders.load_news("AAPL", date(2024, 6, 3))) == 6
    # Items <= 2024-06-01 with relevance >= 0.3: 0.74, 0.81, 0.77, 0.95.
    earlier = loaders.load_news("AAPL", date(2024, 6, 1))
    assert len(earlier) == 4
    assert all(loaders._to_date(it["time_published"]) <= date(2024, 6, 1) for it in earlier)


def test_load_news_relevance_filter(monkeypatch) -> None:
    _use(Config(offline=True, relevance_cutoff=0.7), monkeypatch)
    # cutoff 0.7 over items <= 2024-06-03 keeps 0.92 / 0.74 / 0.81 / 0.77 / 0.95, drops 0.68.
    kept = loaders.load_news("AAPL", date(2024, 6, 3))
    assert len(kept) == 5
    assert all(float(it["relevance"]) >= 0.7 for it in kept)


def test_load_macro_no_relevance_filter_and_slice(monkeypatch) -> None:
    _use(Config(offline=True), monkeypatch)
    # Macro items <= 2024-06-02: 2024-06-02/06-01/05-30/05-15/04-26/04-10 — none relevance-dropped.
    assert len(loaders.load_macro_news(("economy_macro",), date(2024, 6, 2))) == 6
    # Items <= 2024-05-31: 2024-05-30/05-15/04-26/04-10.
    assert len(loaders.load_macro_news(("economy_macro",), date(2024, 5, 31))) == 4


def test_load_prices_slices_and_spy_close(monkeypatch) -> None:
    _use(Config(offline=True), monkeypatch)
    aapl = loaders.load_prices("AAPL", date(2024, 5, 24))
    assert aapl.index.max() <= pd.Timestamp(2024, 5, 24)
    # 29 prepended sessions (2024-04-09..05-17) + 5 (05-20..05-24) = 34 rows <= t.
    assert "close" in aapl.columns and len(aapl) == 34
    spy = loaders.load_prices("SPY", date(2024, 5, 24))  # benchmark → rebuilt from spy_close
    assert "close" in spy.columns
    assert spy["close"].iloc[0] == pytest.approx(512.8)  # first session 2024-04-09


def test_read_or_fetch_idempotent(tmp_path) -> None:
    calls = {"n": 0}

    def fetch() -> pd.DataFrame:
        calls["n"] += 1
        return pd.DataFrame({"a": [1, 2], "b": [3, 4]})

    path = str(tmp_path / "x.parquet")
    first = read_or_fetch(path, fetch)
    second = read_or_fetch(path, fetch)  # must read from disk, not call fetch again
    assert calls["n"] == 1
    pd.testing.assert_frame_equal(first, second)
