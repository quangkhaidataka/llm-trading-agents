"""The critical anti-lookahead test (spec §12.1, §13.5).

ONE invariant: for every t, get_observation(ticker, t) contains NO timestamp > t.
Runs fully offline on fixtures — fast, free, deterministic. Must stay green.
"""

from __future__ import annotations

from datetime import date

import pytest

from config import Config
from src.data.loaders import get_observation


@pytest.fixture
def offline_config() -> Config:
    return Config(offline=True)


@pytest.mark.xfail(reason="M1 not implemented yet", strict=False)
def test_observation_has_no_future_data(offline_config: Config) -> None:
    t = date(2024, 6, 3)
    obs = get_observation(offline_config.ticker, t)

    for item in obs.aapl_news:
        assert _as_date(item["time_published"]) <= t, "AAPL news leaked future"
    for item in obs.macro_news:
        assert _as_date(item["time_published"]) <= t, "macro news leaked future"
    assert obs.t <= t


def _as_date(ts) -> date:
    """Coerce AV's 'YYYYMMDDTHHMMSS' (or ISO) to a date."""
    raise NotImplementedError("M1: parse time_published")
