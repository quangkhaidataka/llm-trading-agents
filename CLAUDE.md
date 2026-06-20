# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Milestone **M0 (Setup)** complete: repo scaffold + harness in place, `make check` green, no business
logic (every `src/` function raises `NotImplementedError` tagged with its milestone).
`project_description.md` is the single source of truth; when it conflicts with anything else, follow
it. Sections 12–13 of that file are written directly to Claude Code and are mandatory — read them
before writing code. Status: `PROGRESS.md`; what's built: `features.json`; build roadmap: `PLAN.md`.

## Harness map (read these)

| Topic | Rule (`.claude/rules/`) | Doc (`docs/`) |
|---|---|---|
| Architecture & layers | [architecture.md](.claude/rules/architecture.md) | [architecture.md](docs/architecture.md) |
| Coding style | [coding-style.md](.claude/rules/coding-style.md) | — |
| LLM & prompts | [llm-and-prompts.md](.claude/rules/llm-and-prompts.md) | [api-patterns.md](docs/api-patterns.md) |
| Testing | [testing-rules.md](.claude/rules/testing-rules.md) | [testing-standards.md](docs/testing-standards.md) |
| Security / leakage | [security-rules.md](.claude/rules/security-rules.md) | — |
| Git workflow | [git-workflow.md](.claude/rules/git-workflow.md) | — |
| Data stores | — | [database-rules.md](docs/database-rules.md) |
| Plan & simple fixes | [follow-the-plan.md](.claude/rules/follow-the-plan.md) | `plan/` + `PLAN.md` |

- **Sub-agents** (`.claude/agents/`): `planner_agent` (decompose, never codes), `generator_agent`,
  `reviewer_agent` (pessimistic), `verifier_agent` (`make check`), `test_writer_agent`, `doc_agent`.
- **Skills** (`.claude/skills/`): `implement-substep` (read plan → build → verify DoD), `run-verification`,
  `update-progress`, `feature-status`, `check-lookahead`. **To build a substep, use `implement-substep`.**
- **Tracking:** `PROGRESS.md` (session state), `DECISIONS.md` (ADRs), `features.json` (machine-readable
  feature/verification list).
- **Gate:** `.claude/settings.json` runs `make check` as a pre-commit hook (blocks red commits).

## Commands

`make check` is the **single source of truth** for "is the code OK" (= lint + typecheck + test + e2e).

```bash
make setup        # create .venv + install dev tooling & minimal runtime (enough for make check)
make setup-full   # also install the heavy runtime (langchain, faiss, vectorbt, ...) — needed M1+
make check        # the gate: lint + typecheck + test + e2e
make test         # unit tests only        make e2e        # pipeline/CLI smoke
make lint         # ruff                    make typecheck  # mypy
make clean        # remove caches + generated artifacts (keeps .venv + fixtures)
```

Run the pipeline (after `make setup-full`): `python -m src.main --mode {download,backtest,ablation}`
(add `--offline` for MockLLM + fixtures, no keys/network).

## What this is

A multi-agent LLM system that daily reads AAPL news + technical indicators and **manages a position**
(hold/open/close/flip → target ∈ {−1, 0, 1}). The contribution is the **A2A protocol** + **non-
parametric memory** — NOT training a model: the LLM is frozen, "learning" lives in a FAISS episode bank.

The problem is a **state-aware position-management policy**, not a daily up/down classifier. The
system enters a position and holds it across sessions until the entry *thesis* is invalidated.

## Stack & layout

Stack: LangChain/LangGraph · OpenRouter (or Groq) Llama 3.3 70B · Pydantic (A2A schemas) · FAISS +
sentence-transformers (memory) · `ta`/pandas (indicators) · vectorbt (backtest). Layout (spec §13.4):
`config.py` (all knobs) · `src/{main,llm}.py` · `src/data/loaders.py` (the `get_observation` gate) ·
`src/agents/{news,macro,technical,memory,debate,position_manager}.py` · `src/graph/build_graph.py` ·
`src/memory/store.py` · `src/backtest/` · `src/eval/{ablation,calibration}.py` · `fixtures/` ·
`tests/` · `notebooks/`. Full detail: [docs/architecture.md](docs/architecture.md).

## Architecture: the A2A protocol (the core contribution)

Agents communicate **only through fixed Pydantic schemas**, never free text — this makes the
dialogue testable and ablatable. Data flow (spec §4.2):

```
get_observation(t) ─▶ NewsAgent, MacroAgent, TechnicalAgent, MemoryAgent
                          │ (each emits its schema)
                          ▼
                     DebateAgent (Bull vs Bear, state-aware) ─▶ ResearchStance
                          │
                          ▼
                     PositionManager (hysteresis + risk veto) ─▶ TradeDecision
                          │
        new_position for session t+1 ─▶ update PortfolioState ─▶ (after outcome) write FAISS episode
```

Schemas (spec §4.3): `PortfolioState`, `NewsSignal`, `MacroSignal`, `TechnicalSignal`,
`MemoryContext`, `ResearchStance`, `TradeDecision`.

Five protocol properties that define correct behavior: (1) **state-aware** — decisions are relative to
`current_position` + `active_thesis`, output is an action not a prediction; (2) **thesis-persistence**
— close only when the stored thesis is invalidated, not on noise; (3) **hysteresis** — asymmetric
`tau_enter`(~0.7)/`tau_exit`(~0.4)/`tau_flip`(~0.8) Schmitt band → low turnover; (4) **structured
debate + risk veto** — mandatory Bull/Bear; PositionManager can force-flat on
vol/drawdown/macro-risk-off/disagreement; (5) **memory feedback loop** — `(state→action→outcome)`
episodes written after outcome known, retrieved later (no weight updates).

Two **separate information channels** (a core design point): NewsAgent reads AAPL-specific
(idiosyncratic) news; MacroAgent reads macro news fetched **by topic, not by ticker** (systematic /
beta channel). The relevance filter applies ONLY to the AAPL channel — never filter macro news, or
you lose Fed/geopolitical coverage. MacroSignal also routes to PositionManager as a risk-off veto.

## Conviction is computed, not LLM-reported (spec §7.3)

The number driving thresholds comes from math, not the LLM's self-report: (1) composite of measurable
signals (agreement, mean confidence, memory consistency), (2) self-consistency sampling (DebateAgent
K times at temp>0), (3) isotonic/Platt calibration to empirical P(correct) on 2022–2024 (validated
with a reliability diagram). The LLM only supplies direction + rationale.

## Non-negotiable constraints (spec §12)

- **Anti-lookahead (priority #1).** *Data:* the single `get_observation(ticker, t)` gate returns only
  data ≤ t; nothing else touches the full dataframe; execute at **t+1**; no `shift(-1)`. *Memory:*
  delayed write — a day-t episode enters FAISS only at **t+1+h** (h=5); retrieval pulls only closed
  episodes. *Pretraining:* report PnL only for 2025–2026 (after the Dec-2023 cutoff); never report
  warm-up PnL. `tests/test_no_lookahead.py` enforces the invariant — keep it green.
- **LLM/prompts:** each agent is `prompt | llm.with_structured_output(Schema)` (never hand-parse);
  one `make_llm` factory; `temperature=0` for decision agents. Never call live/external data or MCP
  tools from `src/`. See [.claude/rules/llm-and-prompts.md](.claude/rules/llm-and-prompts.md).
- **Ticker-dynamic:** `config.ticker` is the single source of truth — no hardcoded `"AAPL"`; setting
  it to `"AMZN"` and re-running must work with no other line changed.
- **Config centralization:** all numbers in `config.py`; defaults from domain knowledge, tuned on
  2022–2024; never fabricate numbers inline.
- **Offline mode:** `config.offline=True` → MockLLM + `fixtures/` (no keys/network/cost); agents must
  not know which mode they're in. All core tests run offline & deterministically.
- **YAGNI:** MVP first; no microservices/DB server/web UI/live trading; classes only where they cut
  duplication or define an interface.

## Build order (spec §13.2 — complete sequentially, each leaves a runnable + passing test)

| M | Build | Acceptance |
|---|---|---|
| M0 | skeleton, config, .env, requirements | `pip install` + `python -m src.main --help` |
| M1 | loaders, Parquet cache, `get_observation` | `test_no_lookahead` green; print one observation |
| M2 | the 6 agents (LCEL + schema) | smoke: each returns its Pydantic schema on one day |
| M3 | LangGraph + PortfolioState + FAISS (delayed h) | one day yields a `TradeDecision`; PIT memory |
| M4 | walk-forward 2025–2026, fees, vectorbt | equity curve + metrics, **PnL net of fees** |
| M5 | baselines + ablations + conviction calibration | comparison table + reliability diagram |

Definition of done (§13.1): one-command end-to-end run; backtest with fees over 2025–2026; PnL/equity
curve + metrics (Sharpe, MaxDD, turnover, avg holding period) vs buy & hold; `test_no_lookahead` green.

## Data notes

Sources (download once, cache to Parquet): **news** via Alpha Vantage (free, 25 req/day) — AAPL
(`NEWS_SENTIMENT&tickers=AAPL`) + macro (`NEWS_SENTIMENT&topics=...`); **prices** (AAPL + SPY adjusted
OHLCV) via Yahoo Finance (`yfinance`, no key). Cast AV string numerics to float; pick the AAPL entry in
`ticker_sentiment`. AV `ticker_sentiment_score` is a baseline/cross-check only — **never the primary
signal**; `relevance_score` is a filter (drop < ~0.3), not alpha. Memory reward is the **AAPL-drift-
demeaned** forward return (enter t+1, h=5): `sign(action)·(forward_return(t,h) − μ)` — NOT SPY-adjusted (ADR-002).
See [docs/database-rules.md](docs/database-rules.md).
