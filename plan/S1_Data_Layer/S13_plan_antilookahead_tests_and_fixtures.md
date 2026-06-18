# S1.3 — Anti-Lookahead Tests & Fixtures

## Objective
In this final sub-step we lock the door and prove it stays locked. We write the test that *is* the
project's credibility — `tests/test_no_lookahead.py` — which sweeps **every** trading day `t` in the
fixtures and asserts that `get_observation(ticker, t)` contains no field dated after `t` (no AAPL news,
no macro news, no price, nothing). We add `tests/test_observation.py` to check that the indicators come
out with sane values and, crucially, that warm-up days surface honest `NaN`s instead of back-filled
fakes. To make these tests meaningful we **enlarge the offline fixtures to roughly 40 sessions** of
prices and a matching spread of dated news, so the sweep actually exercises warm-up edges and a real
date range. Everything here runs fully offline (`config.offline=True`) — no keys, no network,
deterministic — and the end state is that both tests are green and **un-`xfail`ed**, flipping
`features.json` F02/F03 to `passing` and satisfying the M1 acceptance criterion.

## Inputs and Outputs
**Inputs**
- The completed gate and loaders from S1.1 + S1.2 (`get_observation`, `compute_indicators`, `load_*`).
- `config` with `offline=True`; `ticker`, `benchmark`, indicator windows, `relevance_cutoff`.
- Existing fixtures and the existing `tests/test_no_lookahead.py` stub (currently `xfail`, with the
  `_as_date` helper raising `NotImplementedError`).

**Outputs (artifacts)**
- Enlarged fixtures (CSV + JSON, in `config.fixtures_dir` = `fixtures/`):
  - `fixtures/prices_sample.csv` — ~40 sessions; columns `date,open,high,low,close,volume,spy_close`.
  - `fixtures/AAPL_news_sample.json` — JSON; dated AAPL items spread across those sessions.
  - `fixtures/macro_news_sample.json` — JSON; dated macro items (not relevance-filtered).
- `tests/test_no_lookahead.py` — implemented `_as_date`, sweep over every `t`, `xfail` removed.
- `tests/test_observation.py` — indicator-value + NaN-warmup assertions (new file).
- M1 acceptance met: `test_no_lookahead` green; one `Observation` prints via `--mode download` offline.

## Skeleton Python Code
```python
# ── tests/test_no_lookahead.py ───────────────────────────────────────────────
from __future__ import annotations

from datetime import date

import pytest

from config import Config
from src.data.loaders import get_observation


@pytest.fixture
def offline_config() -> Config:
    """Offline config so the sweep uses fixtures only (no keys, no network)."""
    return Config(offline=True)


def _trading_days(config: Config) -> list[date]:
    """All session dates present in fixtures/prices_sample.csv (the universe of t)."""
    ...


def _as_date(ts) -> date:
    """Coerce AV's 'YYYYMMDDTHHMMSS' (or ISO) timestamp to a date."""
    ...


def test_observation_has_no_future_data(offline_config: Config) -> None:
    """THE invariant: for EVERY t, no field in get_observation(t) is dated > t."""
    for t in _trading_days(offline_config):
        obs = get_observation(offline_config.ticker, t)
        for item in obs.aapl_news:
            assert _as_date(item["time_published"]) <= t, "AAPL news leaked future"
        for item in obs.macro_news:
            assert _as_date(item["time_published"]) <= t, "macro news leaked future"
        assert obs.t <= t


# ── tests/test_observation.py ────────────────────────────────────────────────
from __future__ import annotations

from datetime import date

import pytest

from config import Config
from src.data.loaders import compute_indicators, get_observation, load_prices


@pytest.fixture
def offline_config() -> Config:
    return Config(offline=True)


def test_indicator_values_in_range(offline_config: Config) -> None:
    """On a late (post-warm-up) day, RSI in [0,100], MA20/MA50 near price, keys present."""
    ...


def test_warmup_indicators_are_nan_not_backfilled(offline_config: Config) -> None:
    """On an early day with too little history, MA50/MACD are NaN (honest), never back-filled."""
    ...


def test_observation_prints_offline(offline_config: Config) -> None:
    """Sanity: get_observation returns a frozen Observation whose render_*/to_dict work."""
    ...
```

## How It Connects
This sub-step is the proof that the doorway built in S1.2 actually holds. The headline test walks the
full set of fixture trading days and, for each one, opens the gate with `get_observation(ticker, t)` and
inspects every field it returns — comparing each news timestamp (parsed by the same `_as_date` logic
that understands AV's `YYYYMMDDTHHMMSS` format) against `t` and demanding that nothing is dated later.
Because it sweeps *every* `t` rather than a single happy-path date, it catches off-by-one slips, a stray
`bfill`, or a centered rolling window the moment they appear. The companion observation test leans on the
enlarged ~40-session fixtures to do two jobs at once: confirm that on a mature day the indicators land in
believable ranges, and confirm that on an early day — where there genuinely isn't enough history for a
50-day average — the values come back as `NaN` rather than a quietly invented number, which would be a
subtle form of look-ahead. All of this runs under `config.offline=True`, so it needs no API keys and no
network and produces the same result every time, which is exactly why it can sit in `make check` as the
permanent guardrail for the rest of the project. When both tests pass with the `xfail` marker removed,
F02/F03 flip to `passing` and the M1 milestone — "`test_no_lookahead` green; one observation prints" — is
met.

## Key Technology, Design Patterns & Packages
- **pytest** — fixtures (`offline_config`) and the per-`t` sweep that encodes the single anti-lookahead
  invariant; `xfail` is removed once the gate is real.
- **pandas** — reads the enlarged `prices_sample.csv` to enumerate the trading-day universe and to check
  indicator/NaN behavior.
- **python-dateutil** — parses the fixture `time_published` strings in `_as_date`, matching the loader
  exactly so the test and production agree on dates.
- **Offline-first / fixtures-as-fakes** — the Repository's offline branch lets the whole suite run
  deterministically with no secrets, the foundation of every step's self-verification.
- **Invariant / property test** — rather than checking one example, the sweep asserts a property ("no
  field > t") across all days, which is the right shape for a leakage guard.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_no_lookahead.py -q` green (M1
      acceptance), with the `xfail` marker removed; one day's `Observation` prints via
      `.venv/bin/python -m src.main --mode download --offline`.
- [ ] **Tests:** `tests/test_no_lookahead.py` sweeps **every** trading day `t` in the fixtures and
      asserts the invariant "for every `t`, `get_observation(t)` has no timestamp `> t`" (AAPL news,
      macro news, `obs.t`); `tests/test_observation.py` green; all run under `Config(offline=True)` —
      deterministic, no keys/network; `_as_date` parses AV `YYYYMMDDTHHMMSS` exactly like the loader.
- [ ] **Gate:** `make check` green (ruff + mypy + pytest unit + e2e); no new lint/type errors.
- [ ] **features.json:** `F02` and `F03` → `passing` with evidence (commit hash / green
      `test_no_lookahead`); M1 milestone acceptance satisfied.
- [ ] **Fixtures:** enlarged to ~40 sessions — `fixtures/prices_sample.csv`
      (`date,open,high,low,close,volume,spy_close`), `fixtures/AAPL_news_sample.json`,
      `fixtures/macro_news_sample.json` (dated, committed) so the sweep exercises warm-up edges.
- [ ] **Rules:** point-in-time `<= t` proven across all `t`; no `shift(-1)`/`bfill`/centered window
      slips caught by the sweep; macro never relevance-filtered; offline parity; ticker-dynamic.
- [ ] **Tracking:** `PROGRESS.md` updated (M1 done); `DECISIONS.md` ADR if a non-obvious fixture or
      test-design choice was made.
