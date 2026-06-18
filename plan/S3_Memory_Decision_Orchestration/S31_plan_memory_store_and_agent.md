# S3.1 — Episodic Memory: MemoryStore + MemoryAgent

## Objective
This is where the system grows a memory. Every trading day is a little story —
"this is what the world looked like, this is what I did, and (eventually) here is
how it turned out." We capture each such story as an `Episode` and embed its
*situation* into a vector so that, months later, when a similar day comes around,
the system can ask "have I seen something like this before, and did it work?" The
twist that keeps us honest is **delayed write**: an episode is *staged* on day `t`
but is invisible to retrieval until its outcome window has actually closed at
`t+1+h`. On day `t` we genuinely do not yet know whether the trade worked, so the
memory must not pretend we do. Once the window closes we compute a **drift-demeaned
reward** — the forward return minus AAPL's own trailing drift `μ` — so a long that
merely rides a bull market earns no free credit. On top of the store sits the
`MemoryAgent`, which retrieves the `k` closest *closed* analogs and distills them
into one short, human-readable lesson the debate can lean on. On a cold start there
are simply no precedents, and the agent says so calmly rather than inventing any.

## Inputs and Outputs
- **Inputs:**
  - `Observation` (from `get_observation(ticker, t)`; provides `to_memory_text()`,
    `ticker`, `t`) — the embedded situation key.
  - `action: int ∈ {-1, 0, +1}` — the position taken on day `t`.
  - `price_series` — point-in-time AAPL adjusted-close series (≤ current day) used by
    `flush_due` to compute forward return and trailing drift `μ`.
  - `config` knobs: `h` (forward/delayed-write window), `k` (top-k retrieved),
    `embedding_model` (`all-MiniLM-L6-v2`), `reward_benchmark` (`aapl_drift` | `raw`),
    `reward_drift_window` (trailing sessions for `μ`), `ticker`, `cache_dir`.
- **Outputs:**
  - **FAISS index** — `IndexFlatIP` over L2-normalized embeddings (cosine via inner
    product), persisted to `data/faiss_index/` (gitignored). Parallel in-memory
    `list[Episode]` metadata aligned to index rows.
  - **Embedding cache** — `dict` keyed by `(ticker, date)` so a day's "meaning
    coordinates" are computed once (reproducible across reruns/ablations).
  - **`MemoryContext`** (Pydantic) — `{analogs: list[str], lesson: str}` returned by
    `MemoryAgent.run`, consumed by the DebateAgent and conviction layer.

## Skeleton Python Code
```python
# src/memory/store.py — episodic memory (FAISS), point-in-time with DELAYED write
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config import Config
from src.data.loaders import Observation


@dataclass
class Episode:
    """One trading memory: the situation, the action taken, and (once known) its reward."""

    t: date                   # decision day
    state_text: str           # day's situation rendered for embedding (Observation.to_memory_text())
    action: int               # -1 short / 0 flat / +1 long taken at t
    reward: float | None      # drift-demeaned forward return; None until the window closes
    outcome_closed_t: date    # = t+1+h; retrievable only on/after this date


class MemoryStore:
    """Wraps a FAISS index + Episode metadata. Append-only and strictly point-in-time."""

    def __init__(self, config: Config) -> None:
        """Load/create the FAISS IndexFlatIP + pinned embedding model; hold pending episodes
        and an (ticker, date)->embedding cache. No future data ever enters here."""
        ...

    def stage(self, obs: Observation, action: int) -> None:
        """Record a pending Episode for day t (reward=None, outcome_closed_t=t+1+h).
        NOT embedded and NOT searchable until its window closes — this is the delayed write."""
        ...

    def flush_due(self, current_t: date, price_series) -> None:
        """For each pending episode whose window has closed (outcome_closed_t <= current_t):
        compute its reward, embed state_text, and add it to the FAISS index (now retrievable)."""
        ...

    def retrieve(self, obs: Observation, k: int) -> list[Episode]:
        """Return the k most similar CLOSED episodes (outcome_closed_t <= obs.t). Empty on cold start."""
        ...

    def _embed(self, text: str) -> list[float]:
        """Text -> L2-normalized 'meaning coordinates' via the pinned model; cached by (ticker, date)."""
        ...

    @staticmethod
    def _reward(action: int, price_series, t: date, config: Config) -> float:
        """sign(action) * (forward_return(t,h) - mu), forward_return = P[t+1+h]/P[t+1] - 1;
        mu = trailing AAPL drift over config.reward_drift_window (config.reward_benchmark)."""
        ...


# src/agents/memory.py — MemoryAgent: retrieve closed analogs + summarize a lesson
from src.agents.base import BaseAgent
from src.memory.store import MemoryStore
from src.schemas import MemoryContext, PortfolioState


class MemoryAgent(BaseAgent):
    """Wraps MemoryStore.retrieve + a short LLM 'lesson' summary into a MemoryContext."""

    def __init__(self, config, store: MemoryStore) -> None:
        """Hold the shared MemoryStore; build the lesson-summarizer chain via BaseAgent."""
        ...

    def _build_chain(self):
        """ChatPromptTemplate | llm.with_structured_output(MemoryContext) — summarize analogs into a lesson."""
        ...

    def run(self, obs: Observation, state: PortfolioState) -> MemoryContext:
        """retrieve top-k CLOSED episodes for obs; on empty return 'no precedents' (no hallucinated analogs),
        else render analogs (situation + action + actual reward) and summarize one short lesson."""
        ...
```

## How It Connects
Each day the graph hands the `MemoryAgent` the day's `Observation`; it calls
`MemoryStore.retrieve`, which embeds today's situation and finds the `k` nearest
episodes whose outcome has already closed (`outcome_closed_t ≤ obs.t`) — never a
future-dated one — then folds those analogs and their realized rewards into a
`MemoryContext` lesson that flows into the debate and the memory-consistency term of
conviction. After the day's decision is made, `run_one_day` calls `stage` to record
today's situation+action as a *pending* episode (reward still unknown), and calls
`flush_due`, which sweeps every previously staged episode whose `t+1+h` window has now
closed, computes its drift-demeaned reward from the price cache, embeds it, and only
then adds it to the FAISS index. This is the bridge across days: what we *do* today
becomes retrievable evidence only once the market has actually judged it, so memory
grows from a cold, empty start into a steadily richer, leak-free body of experience.

## Key Technology, Design Patterns & Packages
- **FAISS (`IndexFlatIP`)** — exact inner-product search over L2-normalized vectors
  (= cosine similarity); tiny corpus (~hundreds of days) so a flat index is fastest
  and exact, no training needed.
- **sentence-transformers (`all-MiniLM-L6-v2`)** — one *pinned* embedding model so the
  same day always maps to the same coordinates (reproducible, comparable); embeddings
  cached by `(ticker, date)`.
- **Repository pattern** — `MemoryStore` is the only thing that touches FAISS or
  embeddings; consumers see `Episode`/`MemoryContext`, never index internals (swappable).
- **Point-in-time / delayed-write discipline** — `stage` (t) vs `flush_due` (t+1+h) vs
  `retrieve` (closed only) encode the anti-lookahead invariant in the API itself.
- **Template Method (`BaseAgent`)** — `MemoryAgent` reuses the shared `_build_chain`/`run`
  contract so it plugs into the graph like every other analyst.

## Definition of Done
- [ ] **Acceptance command:** `.venv/bin/python -m pytest tests/test_memory.py -q` green (plus
  `.venv/bin/python -m pytest tests/test_agents.py -k memory -q` for `MemoryAgent`).
- [ ] **Tests:** offline & deterministic (`Config(offline=True)`, `MockLLM` for the lesson summary);
  delayed-write invariant — an episode staged for `t` is retrievable **only at `t+1+h`** (and not at
  `t..t+h`); `retrieve` returns only **closed** episodes (`outcome_closed_t ≤ obs.t`); cold start
  returns "no precedents" (empty analogs, no hallucination); reward sign-ordering — same situation,
  **long reward > short reward**; a long that only matches drift `μ` → reward ≈ 0.
- [ ] **Gate:** `make check` green.
- [ ] **features.json:** F07 (MemoryAgent → MemoryContext) and F11 (delayed point-in-time memory) set
  to `passing` with evidence (command + date).
- [ ] **Artifacts:** FAISS `IndexFlatIP` persisted to `data/faiss_index/` (gitignored, covered by
  `.gitignore`); `(ticker, date)`-keyed embedding cache reproducible across reruns.
- [ ] **Rules:** delayed-write point-in-time memory, no leakage — run the **check-lookahead** audit
  (no `.add(` before `t+1+h`, retrieve filters to closed, reward is drift-demeaned/abnormal not raw);
  numbers only in `config.py` (`h`, `k`, `embedding_model`, `reward_benchmark`, `reward_drift_window`),
  none hardcoded.
- [ ] **Tracking:** PROGRESS.md updated; DECISIONS.md ADR-002 referenced (drift-demeaned reward vs SPE;
  `flat` → reward 0 caveat); note `reward_benchmark ∈ {raw, aapl_drift}` exposed as an ablation flag.
