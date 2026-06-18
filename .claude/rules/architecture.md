# Rule: Architecture

Applies to all code under `src/`. Full detail in [`docs/architecture.md`](../../docs/architecture.md).

## Layered system (spec §4.1)

```
L5 Evaluation   src/eval/        vectorbt metrics, baselines, ablation, calibration
L4 Backtest     src/backtest/    walk-forward loop, position sizing, fees
L3 Orchestration src/graph/      LangGraph state machine, A2A schemas  ◀ core contribution
L2 Agents       src/agents/      News·Macro·Technical·Memory·Debate·PositionManager
   Memory       src/memory/      FAISS store (point-in-time)
L1 Data         src/data/        loaders + the single get_observation gate
```

A layer may import only from layers **below** it. Never import `backtest` from `agents`.

## The A2A protocol is the product

- Agents communicate **only** through the Pydantic schemas in `src/schemas.py` — never free text,
  never raw dicts across agent boundaries. Adding a field is a protocol change: update the schema,
  not an ad-hoc payload.
- Each agent is an LCEL runnable `prompt | llm.with_structured_output(Schema)`. Never hand-parse
  JSON from the model.
- The decision output is an **action** (hold/open/close/flip) relative to `PortfolioState`, never an
  absolute daily prediction.

## Single gates (do not bypass)

- **Data:** only `src/data/loaders.py::get_observation(ticker, t)` returns data to the system. No
  agent, backtest, or eval module may read a full dataframe or hit an API directly.
- **LLM:** only `src/llm.py::make_llm(config)` constructs a model. Swapping provider or going
  offline happens there in one place.
- **Config:** all numbers live in `config.py`. No magic numbers in logic (see coding-style).

## Ticker-dynamic (spec §12.5)

`config.ticker` is the single source of truth. Setting `config.ticker = "AMZN"` and re-running must
produce results with **no other line changed**. No hardcoded `"AAPL"` anywhere — not in prompts,
cache keys, or file paths.

## Build order (spec §13.2)

Milestones are sequential: M0 setup → M1 data → M2 agents → M3 graph+memory → M4 backtest → M5 eval.
A milestone starts only after the previous one's acceptance test passes. Each leaves something
runnable. Stubs raise `NotImplementedError("Mx: ...")` tagged with their milestone.

## YAGNI (spec §12.3)

MVP first: 1 ticker, 1 debate round, deterministic indicators. Do **not** add microservices, a DB
server, web UI, live trading, or a config framework. Classes only where they cut duplication or
clarify an interface (`BaseAgent`, `MemoryStore`, `Backtester`); trivial helpers stay functions.
