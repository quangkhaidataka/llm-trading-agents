# Progress

> Living snapshot for session handoff. Update at session end via the `update-progress` skill.
> Use absolute dates. Mirror `features.json` — never list something Completed below `passing`.

_Last updated: 2026-06-19_

## Current State

Milestone **M1 (Data layer) COMPLETE** — S11 (ingestion+cache), S12 (indicators + `Observation`/
`get_observation` gate), and **S13 (anti-lookahead sweep + enlarged fixtures) done**. The single
point-in-time gate is built and proven: `tests/test_no_lookahead.py` sweeps all 41 fixture sessions
asserting no field dated > t (xfail removed). `make check` green (16 unit + e2e); `--mode download
--offline` prints a snapshot. M1 acceptance met. **Next: M2** — the agent brains (Step 2: `make_llm`
factory + MockLLM, then News/Macro/Technical agents, Debate agent, conviction layers 1–2). Needs
`make setup-full` (heavy LLM stack) before M2 code runs.

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
  verified on real cached data (2026-06-18); ADR-004.
- M1 · **S13 (anti-lookahead sweep + fixtures)**: `tests/test_no_lookahead.py` sweeps all 41 fixture
  sessions (`_as_date` reuses `loaders._to_date`, `xfail` removed); fixtures enlarged to 41 sessions
  (last 12 rows kept verbatim) + spread of dated news; S11 loader-test counts recomputed; ADR-005.
  F02 → `passing`. **M1 acceptance met.**

## In Progress

- _M1 complete; M2 (agent brains) not started._

## Blocked

- _none._

## Known Issues

- Heavy runtime stack (langchain, faiss, vectorbt, ta, sentence-transformers) is NOT installed by
  `make setup`; use `make setup-full`. Needed from M2 onward. (vectorbt + numpy 2.x compatibility
  to be confirmed at first `make setup-full` — see DECISIONS.)
- `requirements.txt` pins are first-pass; may need adjustment at first `make setup-full`.

## Next Steps (M2 · Agent brains — Step 2 in PLAN.md)

1. `make setup-full`, then `src/llm.py::make_llm(config)` factory + `MockLLM` (offline parity).
2. News / Macro / Technical agents as `prompt | llm.with_structured_output(Schema)` (LCEL).
3. State-aware DebateAgent (Bull→Bear→thesis-check→action) → `ResearchStance`.
4. Conviction layers 1–2 (composite signals + self-consistency sampling).
5. Smoke test: each agent returns its Pydantic schema on one fixture day (F04–F06, F08).
