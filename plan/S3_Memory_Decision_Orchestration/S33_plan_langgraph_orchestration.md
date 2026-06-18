# S3.3 — LangGraph Orchestration: build_graph + run_one_day

## Objective
This is the step where the separate brains become one organism that lives a day. Using
LangGraph we lay out a small, typed assembly line: the day begins at `observe`, which
fetches the point-in-time `Observation`; then the four analysts — News, Macro,
Technical, and Memory — run **in parallel** because none depends on another; once all
four have spoken, the `debate` node moderates a state-aware Bull-vs-Bear argument into
a `ResearchStance`; the `conviction` node turns that fuzzy judgment into a calibrated
number; the `position_manager` node applies veto-then-hysteresis to produce the final
`TradeDecision`; and `commit` writes everything down and updates the portfolio. The
shared `GraphState` is the whiteboard threaded through these nodes within a day, while
`run_one_day` is what carries `PortfolioState` *across* days and drives the memory's
stage/flush rhythm. The other quietly important job of `commit` is explainability: it
records a **full per-day decision trace** — the news read, every agent's signal and
rationale, the debate's bull/bear/thesis, the conviction breakdown, and the final
decision plus reason — to `log_dir`, which is exactly the data the Step-6 web report
clicks into.

## Inputs and Outputs
- **Inputs:**
  - `config: Config` — wiring + feature flags (`use_memory/use_macro/use_debate/
    use_hysteresis/stateless` for Step-5 ablations), `log_dir`, `k`, `h`.
  - `store: MemoryStore` — shared across days for stage/flush/retrieve.
  - `t: date`, `portfolio: PortfolioState` — the day to run and the state carried in.
  - The Step-2 LangChain agents (News/Macro/Technical/Memory/Debate) + the conviction
    engine + the `PositionManager` (S3.2).
- **Outputs:**
  - Compiled LangGraph **app** from `build_graph`, runnable per day.
  - **`TradeDecision`** from `run_one_day`, with `PortfolioState` mutated for `t+1`.
  - **Per-day trace record** (JSON) written by `commit` to
    `config.log_dir/{ticker}_{t}.json` (one object per date): `{date, news, agents:
    {news, macro, technical, memory rationale}, debate: {bull_case, bear_case,
    thesis_still_valid}, conviction (+breakdown), decision: {new_position, vetoed,
    reason}}` — the source for the Step-6 explainable report (spec §9).
  - Memory side effects: `store.stage(t)` then `store.flush_due(t)` each day.

## Skeleton Python Code
```python
# src/graph/build_graph.py — per-day LangGraph state machine carrying PortfolioState
from __future__ import annotations

from datetime import date
from typing import TypedDict

from config import Config
from src.data.loaders import Observation
from src.memory.store import MemoryStore
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    PortfolioState,
    ResearchStance,
    TechnicalSignal,
    TradeDecision,
)


class GraphState(TypedDict):
    """The shared, typed 'whiteboard' threaded through one day's nodes (kept minimal)."""

    obs: Observation
    portfolio: PortfolioState
    news: NewsSignal
    macro: MacroSignal
    technical: TechnicalSignal
    memory: MemoryContext
    stance: ResearchStance
    conviction: float
    decision: TradeDecision


def build_graph(config: Config, store: MemoryStore):
    """Wire and compile the graph:
       observe -> [news, macro, technical, memory] (parallel) -> debate -> conviction
       -> position_manager -> commit.  The four analysts fan out from observe and the
       debate node joins on all four. Feature flags can bypass nodes (e.g. no-macro/
       no-memory/no-debate). The commit node applies the decision and writes the full
       per-day decision trace to config.log_dir. Returns the compiled app."""
    ...


def run_one_day(app, t: date, portfolio: PortfolioState, store: MemoryStore) -> TradeDecision:
    """Run the graph for day t: build the Observation, execute the nodes, update PortfolioState
       (position/thesis/days_held), stage today's episode (store.stage), and flush episodes whose
       window has closed (store.flush_due). Returns the day's TradeDecision."""
    ...
```

## How It Connects
Within a single day the whiteboard flows downhill: `observe` seeds `GraphState` with
the point-in-time `Observation` and the inbound `PortfolioState`; News, Macro,
Technical, and Memory write their signals in parallel (Memory pulling closed analogs
from the FAISS store); `debate` reads all four to produce a stance; `conviction`
calibrates it; `position_manager` checks the risk veto and then the hysteresis
thresholds against the current position to emit the `TradeDecision`; and `commit`
applies that decision, advances `days_held`/`active_thesis`, and logs the full trace.
Across days, `run_one_day` is the heartbeat: it threads the updated `PortfolioState`
into tomorrow's run, and right after committing it calls `store.stage(t)` to record
today's situation+action as a pending episode and `store.flush_due(t)` to close out and
index any episode whose `t+1+h` window has now elapsed — so memory and the position
both evolve together, leak-free, one day at a time, and the accumulating trace files
become the explainable record the Step-6 web report reads.

## Key Technology, Design Patterns & Packages
- **LangGraph** — declarative node/edge state machine over a `TypedDict` `GraphState`;
  native fan-out/fan-in expresses the parallel analysts joining at the debate.
- **Pipeline / mediator pattern** — the graph mediates between independent agents; nodes
  communicate only via the typed whiteboard, never by calling each other directly.
- **Feature-flag conditional wiring** — flags include/bypass nodes so every Step-5
  ablation is one `Config` toggle over the same graph, not a code fork.
- **Event-sourcing / trace logging** — `commit` persists an append-only per-day JSON
  record (the decision's full provenance) to `log_dir`, decoupling compute from the
  Step-6 report rendering.
- **Shared `MemoryStore` + delayed write** — one store instance threaded through
  `run_one_day` enforces stage(t)/flush(t+1+h)/retrieve(closed) ordering across days.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_graph.py -q` green.
- [ ] **Tests:** offline & deterministic (`Config(offline=True)`, `MockLLM` + fixtures, no network);
  one day end-to-end → a **valid `TradeDecision`** and `PortfolioState` updated for `t+1`
  (`current_position`/`active_thesis`/`days_held` advance, carried across days); the four analysts fan
  out from `observe` and `debate` joins on all four; memory side effects fire in order —
  `store.stage(t)` then `store.flush_due(t)` — and remain **point-in-time** (no future-dated retrieval).
- [ ] **Gate:** `make check` green (graph smoke is the M3 acceptance: one day yields a `TradeDecision`,
  memory writes/reads point-in-time).
- [ ] **features.json:** F10 (LangGraph one-day end-to-end + PortfolioState across days) set to
  `passing` with evidence (command + date).
- [ ] **Artifacts:** per-day decision trace JSON written to `config.log_dir/{ticker}_{t}.json`
  (news + each agent's signal/rationale + debate bull/bear/thesis + conviction breakdown + final
  decision/reason); `log_dir` gitignored.
- [ ] **Rules:** run the **check-lookahead** audit on the orchestration (delayed-write ordering
  stage→flush→retrieve-closed preserved across `run_one_day`; no `mcp__`/live-SDK/`requests` in `src/` —
  data only via `get_observation`); execution at `t+1`, never `t`; numbers only in `config.py`.
- [ ] **Tracking:** PROGRESS.md updated; DECISIONS.md ADR if graph wiring is a non-obvious choice; note
  the ablation feature flags (`use_memory/use_macro/use_debate/use_hysteresis/stateless`) added to
  config here for Step 5, with flag-bypassed nodes covered.
