# Progress

> Living snapshot for session handoff. Update at session end via the `update-progress` skill.
> Use absolute dates. Mirror `features.json` — never list something Completed below `passing`.

_Last updated: 2026-06-19_

## Current State

Milestone **M3 (Memory · Decision · Orchestration) in progress** — M2 complete; **S31 (episodic memory)
done**. `MemoryStore` (`src/memory/store.py`) is a real FAISS `IndexFlatIP` with strict point-in-time
delayed write: `stage(t)` records a pending episode, `flush_due(t+1+h)` closes it (drift-demeaned reward,
embed, add to index), `retrieve` returns only closed analogs. FAISS runs in both modes (added to dev
venv); only the embedder is mocked offline (deterministic md5 hash embedder — sentence-transformers/torch
is online-only). `MemoryAgent` wraps retrieve + an LCEL lesson summary → `MemoryContext` (cold start = no
precedent, no hallucination). `tests/test_memory.py` + `-k memory` green; check-lookahead audit clean;
`make check` green (43 unit + e2e). **F07/F11 passing.** **Next in M3: S32** (PositionManager —
hysteresis + risk veto) then **S33** (LangGraph orchestration → one `TradeDecision`). Live run needs
`make setup-full` (langchain-groq + sentence-transformers).

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

- M2 · **S21 (LLM factory + MockLLM)**: Groq-only `make_llm` (OpenAI branch removed); `MockLLM` +
  `_StructuredRunnable` mirror `with_structured_output`; fixture re-keyed by `Schema.__name__` (lists);
  seeded cycling index → deterministic yet varied; `tests/test_llm.py` green; ADR-006. Enables F04–F08.
- M2 · **S22 (analyst agents)**: `src/agents/{prompts,news,macro,technical}.py` — LCEL chains via
  `BaseAgent`; reason-first v2 prompts + `CONFIDENCE_RUBRIC`; no-news short-circuit; analyst schemas
  reordered `rationale`-first; `langchain-core` added to dev venv (ADR-007). `tests/test_agents.py`
  green. **F04/F05/F06 passing.**
- M2 · **S23 (DebateAgent + conviction)**: `src/agents/debate.py` (state-aware Bull/Bear → `ResearchStance`,
  `sample()` for self-consistency, `debate_temperature` knob) + conviction Layers 1-2 in
  `src/eval/calibration.py`; `ResearchStance` reordered reason-first; fixture hold-first; ADR-008.
  `tests/test_calibration.py` + debate tests green. **F08 passing. M2 complete.**
- M3 · **S31 (episodic memory)**: `src/memory/store.py` (FAISS `IndexFlatIP`, `stage`/`flush_due`/
  `retrieve`, drift-demeaned reward, md5 hash embedder offline) + `src/agents/memory.py` (`MemoryAgent`
  → `MemoryContext`); `faiss-cpu` added to dev venv; ADR-009. `tests/test_memory.py` + `-k memory`
  green. **F07/F11 passing.**

## In Progress

- M3 · **S32** next — `PositionManager` (asymmetric hysteresis on conviction z: tau_enter/exit/flip +
  risk veto on vol/drawdown/macro risk-off/disagreement) → `TradeDecision`. Then **S33** (LangGraph).

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
