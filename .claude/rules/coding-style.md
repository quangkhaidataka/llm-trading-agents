# Rule: Coding Style

Python 3.11. Enforced by `make lint` (ruff) and `make typecheck` (mypy). Match surrounding code.

## Numbers live in config only (spec §13.3)

- Every threshold, weight, window, fee, and limit lives in `config.py`. **No magic numbers** in
  logic — if a function needs `0.7`, it reads `config.tau_enter`.
- Propose defaults from domain knowledge, then tune on the 2022–2024 calibration set. Never fabricate
  a number inline "to make it work".

## Determinism & reproducibility (spec §12.6)

- `temperature=0` for decision agents. The only exception is the self-consistency sampling of the
  DebateAgent (spec §7.3), which is explicit and config-driven (`config.K`).
- Pin the model version (`config.model_id`). Seed anything stochastic (`config.seed`).
- Indicators are computed deterministically with `ta`/pandas in the data layer — the LLM only
  interprets numbers, never produces them.

## Typing & structure

- Type-annotate public functions and all dataclass/Pydantic fields. `from __future__ import
  annotations` at the top of every module.
- Pydantic for A2A messages and validated config; `@dataclass` for plain containers (`Observation`,
  `Episode`).
- Prefer pure functions; keep side effects (I/O, cache writes, logging) at the edges.
- Classes earn their place by removing duplication or defining an interface — not by default.

## Imports & formatting

- ruff handles import sorting and formatting; run `make lint` before declaring work done.
- Import heavy/optional deps (langchain, faiss, vectorbt) **inside the function** that uses them, not
  at module top — keeps the CLI, tests, and offline mode importable without the full stack.
- No wildcard imports. Absolute imports from the `src` package.

## Errors & logging

- Unimplemented scaffold raises `NotImplementedError("Mx: <what>")` naming its milestone.
- Log each day's decision (signals + rationale + new_position) to `config.log_dir` for traceability
  (spec §12.6). Logs are data, not `print`.
- Fail loud on point-in-time violations — never silently drop or clamp a future-dated record.
