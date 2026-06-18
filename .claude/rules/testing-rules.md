# Rule: Testing

Full standards in [`docs/testing-standards.md`](../../docs/testing-standards.md). `make check` is the
single source of truth for "is the code OK".

## The non-negotiable test (spec §12.1, §13.5)

`tests/test_no_lookahead.py` asserts ONE invariant: for every `t`,
`get_observation(ticker, t)` contains no timestamp `> t`. It must run offline on fixtures and stay
green. Anti-lookahead is priority #1 — a failing no-lookahead test blocks everything.

## Offline & deterministic (spec §13.6)

- All core tests run with `Config(offline=True)`: `MockLLM` + `fixtures/`. No API keys, no network,
  no cost, fully reproducible.
- Never call the real LLM or Alpha Vantage in a test. If a test needs a model, it gets `MockLLM`.
- Fixtures live in `fixtures/` and are committed: AAPL news, macro news, prices, canned LLM responses.

## Markers & layout

- `pytest` markers: default = fast unit tests; `@pytest.mark.e2e` = pipeline/CLI smoke (run by
  `make e2e`). Markers are declared in `pyproject.toml`.
- One test file per module under `tests/`. Name tests by behavior, not implementation.
- Use `@pytest.mark.xfail(strict=False)` for a stub whose feature is not built yet, with a reason
  naming the milestone — so `make check` stays green during scaffolding without hiding real failures.

## Per-milestone acceptance (spec §13.2)

Each milestone ships with the test that proves it:
- M1 → `test_no_lookahead` green; can print one observation.
- M2 → smoke: each agent returns its correct Pydantic schema on one day.
- M3 → one day yields a `TradeDecision`; memory writes/reads point-in-time.
- M4 → equity curve + metrics, **PnL net of fees**.
- M5 → comparison table + reliability diagram.

## What to test

- The data gate's point-in-time invariant (above).
- Schema conformance of every agent output.
- Hysteresis transitions: flat→open only at `≥τ_enter`; in-position→close only when thesis invalid
  or `≤τ_exit`; flip only at `≥τ_flip`.
- Delayed memory write: an episode for `t` is retrievable only at `t+1+h`.
- Backtest accounting: fees charged on every position change; execution at `t+1`.
