# Progress

> Living snapshot for session handoff. Update at session end via the `update-progress` skill.
> Use absolute dates. Mirror `features.json` — never list something Completed below `passing`.

_Last updated: 2026-06-18_

## Current State

Milestone **M1 in progress** — **S11 (data ingestion & caching) done**. The data layer's loaders
(`load_news`/`load_macro_news`/`load_prices`), the AV news adapter + yfinance price adapter, the
`read_or_fetch` Parquet cache, and `--mode download` (prints a point-in-time data snapshot) are
implemented and tested offline. `make check` green (9 unit + e2e); `--mode download --offline` runs.
Next in M1: **S12** (`compute_indicators` + the `Observation`/`get_observation` gate) and **S13**
(no-lookahead tests). M0 (Setup) is complete (scaffold + harness).

## Completed

- M0 · Repo skeleton matching spec §13.4 (`config.py`, `src/`, `fixtures/`, `tests/`, `notebooks/`).
- M0 · A2A Pydantic schemas (`src/schemas.py`) and the `Observation` / `get_observation` contract.
- M0 · Harness: `.claude/rules/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.json`.
- M0 · Docs (`docs/architecture|database-rules|testing-standards|api-patterns.md`), `CLAUDE.md`.
- M0 · `Makefile` (`setup`/`check`/...), `pyproject.toml`, `requirements*.txt`.
- M0 · Passing scaffold tests: `tests/test_smoke.py`, `tests/test_e2e_smoke.py`.
- M0 · Git initialized; clean initial checkpoint committed; Bootstrap Contract checklist passed.
- M1 · **S11 (data layer)**: `src/data/{cache,alpha_vantage,yahoo}.py` + loaders + `download()`;
  `tests/test_loaders.py` green; ADR-003. yfinance prices / AV news.
- M1 · **Live data downloaded** (2026-06-19, AV Premium, ~2 min) → `data/*.parquet` (~7 MB, gitignored):
  AAPL_news 10,904 + macro_news 10,214 + AAPL/SPY prices 1,119 each, 2022-01→2026-06-18. F03 `passing`.

- M1 · **S12 (indicators + Observation gate)**: `compute_indicators` + `compute_spy_trend` + frozen
  `Observation` (render/to_dict/`__post_init__`) + `get_observation`; `tests/test_observation.py` green;
  verified on real cached data (2026-06-18); ADR-004. F02 `active` (→ `passing` in S13).

## In Progress

- M1 · **S13** next — finalize `tests/test_no_lookahead.py` (implement `_as_date`, remove `xfail`,
  parametrize over many `t`), enlarge `fixtures/` to ~40 sessions → flips F02 `passing`.

## Blocked

- _none._

## Known Issues

- Heavy runtime stack (langchain, faiss, vectorbt, ta, sentence-transformers) is NOT installed by
  `make setup`; use `make setup-full`. It is unneeded until M1. (vectorbt + numpy 2.x compatibility
  to be confirmed during M1 — see DECISIONS.)
- `tests/test_no_lookahead.py` is `xfail` until M1 implements `get_observation`.
- `requirements.txt` pins are first-pass; may need adjustment at first `make setup-full`.

## Next Steps (M1 · Data layer)

1. Implement `load_prices` + `compute_indicators` (deterministic `ta`; no `shift(-1)`).
2. Implement `load_news` / `load_macro_news` (AV + Parquet cache; macro NOT relevance-filtered).
3. Implement `get_observation` enforcing the point-in-time invariant; offline branch reads `fixtures/`.
4. Remove the `xfail` from `tests/test_no_lookahead.py` and make it green.
5. `python -m src.main --mode download` caches data; print one day's observation. Update `features.json`.
