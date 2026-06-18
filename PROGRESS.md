# Progress

> Living snapshot for session handoff. Update at session end via the `update-progress` skill.
> Use absolute dates. Mirror `features.json` — never list something Completed below `passing`.

_Last updated: 2026-06-18_

## Current State

Milestone **M0 (Setup)** complete. Repo scaffold, config, A2A schemas, agent/graph/backtest/eval
stubs, the harness (`.claude/` rules + agents + skills, `docs/`, `Makefile`, `features.json`), and
offline fixtures are in place. `make setup` + `make check` pass on the empty project (smoke + e2e
tests green). No business logic is implemented — every `src/` function raises `NotImplementedError`
tagged with its milestone.

## Completed

- M0 · Repo skeleton matching spec §13.4 (`config.py`, `src/`, `fixtures/`, `tests/`, `notebooks/`).
- M0 · A2A Pydantic schemas (`src/schemas.py`) and the `Observation` / `get_observation` contract.
- M0 · Harness: `.claude/rules/`, `.claude/agents/`, `.claude/skills/`, `.claude/settings.json`.
- M0 · Docs (`docs/architecture|database-rules|testing-standards|api-patterns.md`), `CLAUDE.md`.
- M0 · `Makefile` (`setup`/`check`/...), `pyproject.toml`, `requirements*.txt`.
- M0 · Passing scaffold tests: `tests/test_smoke.py`, `tests/test_e2e_smoke.py`.
- M0 · Git initialized; clean initial checkpoint committed; Bootstrap Contract checklist passed.

## In Progress

- _none_ — M0 closed; awaiting kickoff of M1.

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
