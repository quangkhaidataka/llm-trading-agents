# Architecture

Authoritative spec: [`project_description.md`](../project_description.md) §4. This is the working
summary. Rule form: [`.claude/rules/architecture.md`](../.claude/rules/architecture.md).

## Five layers (spec §4.1)

| Layer | Package | Responsibility |
|---|---|---|
| L5 Evaluation | `src/eval/` | vectorbt metrics, baselines, ablations, conviction calibration |
| L4 Backtest | `src/backtest/` | walk-forward loop, position sizing, transaction cost |
| L3 Orchestration | `src/graph/` | LangGraph state machine, A2A schemas, debate/veto — **core** |
| L2 Agents | `src/agents/` | News, Macro, Technical, Memory, Debate, PositionManager |
| Memory | `src/memory/` | FAISS store with point-in-time write/retrieve |
| L1 Data | `src/data/` | loaders + the single `get_observation` gate |

Import direction is strictly downward. `config.py` and `src/schemas.py` are cross-cutting and may be
imported anywhere.

## Per-day data flow (spec §4.2)

```
get_observation(t)
  ├─ NewsAgent      → NewsSignal        (idiosyncratic / AAPL news)
  ├─ MacroAgent     → MacroSignal       (systematic / macro-by-topic; also → risk veto)
  ├─ TechnicalAgent → TechnicalSignal   (interprets precomputed indicators)
  └─ MemoryAgent    → MemoryContext     (top-k closed FAISS episodes)
        │
        ▼
  DebateAgent (Bull/Bear, state-aware) → ResearchStance (hold/open/close/flip)
        │
        ▼  conviction = calibrate(signals, self-consistency)   (spec §7.3, computed not LLM-reported)
        ▼
  PositionManager (hysteresis + risk veto) → TradeDecision (new_position for t+1)
        │
        ├─ update PortfolioState (store thesis on open/flip)
        └─ MemoryStore.stage(t); flush episodes due at t+1+h
```

## The A2A protocol (spec §4.3) — the contribution

Agents speak only through the Pydantic schemas in `src/schemas.py`: `PortfolioState`, `NewsSignal`,
`MacroSignal`, `TechnicalSignal`, `MemoryContext`, `ResearchStance`, `TradeDecision`. Five properties:
state-aware policy, thesis-persistence, hysteresis, structured debate + risk veto, memory feedback
loop. See [`api-patterns.md`](api-patterns.md) for how each agent is wired.

## Two information channels

- **Idiosyncratic** — NewsAgent reads AAPL-specific news (relevance-filtered).
- **Systematic** — MacroAgent reads macro news fetched **by topic, not ticker** (never relevance-
  filtered) and SPY trend; routes a risk-off veto to the PositionManager.

This mirrors the own-alpha vs market-beta split of factor models and is what lets the system react to
Fed/geopolitical shocks a ticker-only design would miss.

## Single gates

- Data: `src/data/loaders.py::get_observation` (enforces point-in-time).
- LLM: `src/llm.py::make_llm` (provider swap + offline MockLLM).
- Config: `config.py` (all numbers).

## Build order

M0 setup → M1 data → M2 agents → M3 graph+memory → M4 backtest → M5 eval (spec §13.2). Sequential;
each milestone leaves something runnable and keeps `make check` green.
