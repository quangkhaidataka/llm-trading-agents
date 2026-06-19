# Decision Log (ADR)

Architecture/technical decisions, newest first. One entry per non-obvious choice. Append via the
`doc_agent` / in the same commit as the change. Use absolute dates.

Template:

```
## ADR-NNN · <short title>
- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | superseded by ADR-MMM
- **Decision:** what we chose.
- **Reason:** why — the forces that drove it.
- **Rejected alternatives:** what else was considered and why not.
- **Consequences:** follow-on effects, risks, what this commits us to.
```

---

## ADR-009 · S31 memory: real FAISS both modes, embedder mocked offline, delayed-write via price positions
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** `MemoryStore` uses a **real FAISS `IndexFlatIP` in both offline and online modes** —
  `faiss-cpu==1.13.0` added to `requirements-dev.txt` (3.4 MB wheel, no torch, imports in ~0.6 s, numpy
  2.4.4 OK). Only the **embedder** is mode-dependent (a Repository branch on `config.offline`, like the
  loaders — not an agent): online = pinned `sentence-transformers` (`config.embedding_model`, the
  torch-heavy part, function-local import, stays in `requirements.txt`); offline = a deterministic
  dependency-free **hash embedder** (`_hash_embed`, 64-dim bag-of-md5-hashed-tokens, L2-normalized) so
  `make check` stays light + reproducible. md5 is used (NOT Python's salted `hash()`) so the same text →
  same vector across processes. Delayed write is enforced by **trading-day positions in the price
  series**, not calendar math: `flush_due` closes a pending episode only when `idx[pos(t)+1+h]` exists
  and its date ≤ current_t, sets `outcome_closed_t` to that bar's date, computes the reward, then adds
  to FAISS; `retrieve` additionally filters to `outcome_closed_t ≤ obs.t`. `Episode.reward`/
  `outcome_closed_t` are now `| None` (set on flush). Reward is the **drift-demeaned** forward return
  (ADR-002): `sign(action)·(P[t+1+h]/P[t+1]−1 − μ)`, μ = trailing mean h-session AAPL return over
  `reward_drift_window`, computed only from closes ≤ t; `flat`→0. A pytest `filterwarnings` ignore was
  added for faiss's third-party SWIG `DeprecationWarning`.
- **Reason:** The only genuinely heavy memory dep is the embedding model (torch); FAISS itself is light,
  so using it in both modes keeps ONE index/search code path (higher fidelity, less divergence) while
  mocking just the embedder preserves offline determinism + speed (same philosophy as `make_llm`/ADR-007).
  Deciding closure by price-series position (not `t + (1+h)` calendar days) is exact across weekends/
  holidays and matches how forward_return is computed, so the delayed-write test is unambiguous.
- **Rejected alternatives:** numpy-only cosine search instead of FAISS (would drop the plan's stated
  index and duplicate logic — FAISS installs cleanly, so unnecessary); installing sentence-transformers
  in the dev venv (pulls torch, heavy/slow — defeats the light-venv split, ADR-001); calendar-day
  closure (wrong across non-trading days); Python `hash()` for the offline embedder (salted →
  non-reproducible).
- **Consequences:** Dev venv now carries faiss-cpu; a live run still needs `make setup-full` for
  sentence-transformers. Disk persistence (`data/faiss_index/`, already gitignored via `faiss_index/`)
  is a capability to be wired when the backtest needs resume (S33/S4); the store is in-memory per run
  for now. F07 + F11 → `passing`. S32 (PositionManager) + S33 (LangGraph) will call `stage`/`flush_due`/
  `retrieve` in `run_one_day`.

## ADR-008 · S23 DebateAgent + conviction engine: sampling temperature, hold-default fixture
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** The `DebateAgent` reuses the `BaseAgent` LCEL shape (`prompt |
  llm.with_structured_output(ResearchStance)`) and adds a `sample(...)` path for Layer-2
  self-consistency. `run` invokes once at `temperature=0`; `sample` builds a **fresh** chain from a
  config copy (`dataclasses.replace(config, temperature=config.debate_temperature)`, new knob, default
  **0.7**) and invokes K times. Offline the K-action variation comes from the MockLLM's seeded cycling
  (ADR-006), not real temperature; a fresh sampling chain per call keeps that cycling deterministic.
  The conviction engine (`src/eval/calibration.py`) is pure math: `composite_conviction` (Layer 1 =
  `w1·agreement + w2·mean_confidence + w3·memory_consistency`, with a Σconfidence==0 divide-by-zero
  guard), `self_consistency_conviction` (Layer 2 = majority-action frequency), `raw_conviction`
  (`α·raw + β·sc`). Two supporting choices: (1) **PLAN fix #4 applied to `ResearchStance`** — reordered
  so `bull_case, bear_case, thesis_still_valid` precede `action, target_direction, conviction`
  (reason-first generation; the stance's own `conviction` is just one input to the math, never the
  decision number). (2) The fixture's `ResearchStance` list is reordered so the **`hold` stance is
  index 0** — the representative offline debate outcome — so the "prefers hold when a held thesis stays
  valid" check is deterministic and the default canned outcome matches the continuity-bias philosophy.
  The continuity bias itself lives only in the PROMPT, never as a code rule (the deterministic
  hysteresis is the PositionManager's job in S3).
- **Reason:** Self-consistency needs `temperature>0` online but must stay deterministic offline — the
  seeded MockLLM already provides that, so no RNG enters the conviction code (it stays pure/unit-testable).
  Keeping conviction as math, not the LLM's self-report, is the core §7.3 contribution. The hold-first
  fixture makes the continuity check meaningful without a conditional mock.
- **Rejected alternatives:** sampling by shuffling evidence order (adds nondeterminism/complexity;
  temperature is the standard self-consistency lever — the plan's "(varying evidence order)" parenthetical
  is dropped as YAGNI); a code-level "force hold" continuity rule (belongs in the prompt + the
  PositionManager, not the DebateAgent); trusting the LLM's `conviction` field (overconfident/inconsistent
  — the whole reason the engine exists).
- **Consequences:** New `config.debate_temperature`. `ResearchStance` reorder is a protocol change
  (fixtures construct by keyword → unaffected). Conviction Layers 1-2 land now; Layer 3
  (`fit_calibrator`/`reliability_diagram`, F15) stays a Step-5 stub — it needs the 2022-2024 history.
  F08 → `passing`; **M2 (agent brains) complete**. S3 will wire these signals + `raw_conviction` z into
  the PositionManager's τ thresholds.

## ADR-007 · S22 analyst agents: langchain-core in dev venv, MockLLM stays chain-composable
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** The canonical agent chain is `prompt | llm.with_structured_output(Schema)`, which needs
  `ChatPromptTemplate` (from `langchain_core`). Since the offline agent tests build that chain in the
  **dev** `.venv`, **`langchain-core==0.3.79` is added to `requirements-dev.txt`** (pinned to match
  `requirements.txt`). It is lightweight (pydantic/tenacity/langsmith — no torch/faiss); the heavy
  `langchain-groq` backbone stays online-only with a function-local import. `MockLLM` itself remains
  **langchain-free**: `_StructuredRunnable` gained a `__call__` so a LangChain prompt coerces it to a
  `RunnableLambda` on `|` — `src/llm.py` imports no langchain and `test_llm.py` still needs none. The
  `ChatPromptTemplate` import is **function-local** inside each agent's `_build_chain` (coding-style).
  Three smaller choices: (1) **PLAN fix #4** — `NewsSignal`/`MacroSignal`/`TechnicalSignal` reordered so
  `rationale` is the **first** field (schema order = generation order → reason-first). Field is named
  `rationale` (not the plan example's `reasoning`) to match the existing schemas + S21 fixtures. (2) The
  `TechnicalAgent` prompt uses `obs.render_indicators()` (one `{indicators}` slot) rather than hand-listing
  each indicator — the plan's own Inputs say the render helpers feed the prompts, and it avoids
  duplicating the data-layer's NaN-aware formatter. (3) A no-news day **short-circuits** the NewsAgent to
  `NewsSignal(signal=flat, sentiment=0, confidence=config.no_news_confidence=0.5)` without calling the
  LLM — nothing to reason about, and it makes the empty-news case deterministic offline.
- **Reason:** The plan + architecture mandate the LCEL chain shape and offline determinism; the chain
  cannot be built without langchain-core, so it belongs in the test runtime (same pattern as ADR-001/003
  adding pandas/ta). Keeping `MockLLM` langchain-free preserves the S21 seam (ADR-006) and a clean
  `src/llm.py`. The 0.5 default is the rubric's explicit "no edge" point, so it is a definition, not a
  magic number — and it lives in `config.py`.
- **Rejected alternatives:** subclassing `langchain_core.Runnable` in `MockLLM` (couples the offline
  seam to langchain, contradicts ADR-006); installing full `langchain`/`langchain-groq` in the dev venv
  (heavy, unnecessary offline); hand-listing indicators in the prompt (duplicates the formatter);
  asking the LLM about an empty news set (nondeterministic, wasteful).
- **Consequences:** Dev venv now carries langchain-core; `make setup-full` (full stack) still required
  for a live online run. Reordering the analyst schemas is a protocol change — fixtures construct by
  keyword so they are unaffected; no conformance test existed, `tests/test_agents.py` now covers schema
  conformance. F04/F05/F06 → `passing`. S23's DebateAgent will reuse the same BaseAgent + chain shape.

## ADR-006 · S21 MockLLM fixture contract: keyed by Schema.__name__, lists, seeded cycling
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** `fixtures/llm_responses.json` is keyed by **`Schema.__name__`** (`NewsSignal`,
  `MacroSignal`, `TechnicalSignal`, `MemoryContext`, `ResearchStance`) and each value is a **list** of
  response dicts. `MockLLM.with_structured_output(schema)` returns a `_StructuredRunnable` that, on each
  `.invoke()`, picks `pool[(seed + call_count) % len(pool)]` and returns `schema(**data)` — a validated
  Pydantic instance. This makes offline output **deterministic** for a given seed yet **varied across
  repeated calls** (the cycling index), which is exactly what S23's self-consistency sampling needs.
  `ResearchStance` ships **3 entries with distinct actions** (open/hold/close) so a K-sample sweep sees
  >1 action offline. The dict keys use the **actual** schema field names from `src/schemas.py` (e.g.
  `rationale`) — the S21 plan's JSON example used an illustrative `reasoning` key, which does not exist.
  The online path is **Groq-only**: the stub's `ChatOpenAI` branch was removed (the project budget is
  all-free; no OpenAI path — a decision already taken in planning, realized here).
- **Reason:** Lists + a seed counter give the one property the conviction engine requires — reproducible
  variation — without any RNG or network. Keying by schema name keeps `MockLLM` schema-agnostic (it
  never branches per agent). Using real field names means `Schema(**data)` actually validates, turning
  the fixture into a contract check.
- **Rejected alternatives:** the prior shape (keyed by **agent name**, a **single** dict) — gave no
  variation for self-consistency and coupled the mock to agent identities; injecting randomness for
  variation (breaks determinism / reproducibility, spec §12.6); keeping the OpenAI branch (no free
  tier, out of scope).
- **Consequences:** S22/S23 must author any new canned responses in this shape (schema-name key → list
  of field-accurate dicts). `langchain_groq` stays a function-local import, so offline runs/tests need
  it not installed. S21 owns no `features.json` id; it **enables F04–F08** (offline MockLLM parity).

## ADR-005 · S13 anti-lookahead sweep + enlarged fixtures (S11 test counts updated)
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** `tests/test_no_lookahead.py` now sweeps **every** session date in
  `fixtures/prices_sample.csv` (the universe of `t`) rather than one happy-path day, asserting "no field
  dated > t" for AAPL news, macro news, and `obs.t`; the `xfail` marker is removed and `_as_date`
  delegates to `loaders._to_date` so the test parses timestamps **exactly** like the loader. Fixtures
  enlarged to **41 sessions** (2024-04-09..2024-06-05): the last 12 rows are kept **verbatim** (so the
  S12 `tests/test_observation.py` assertions — e.g. close@2024-06-05 = 195.90 — stay valid), with 29
  earlier business days prepended so the sweep exercises warm-up edges. AAPL/macro news fixtures gained
  earlier-dated items (two AAPL items below the 0.3 cutoff, to exercise the relevance filter).
- **Reason:** A property/invariant sweep across all `t` is the correct shape for a leakage guard — it
  catches an off-by-one slice, a stray `bfill`, or a centered window the moment it appears, which a
  single-date test cannot. Reusing `_to_date` guarantees test/production date agreement (DoD).
- **Rejected alternatives:** keeping the single-`t` test (weak guard); adding `python-dateutil` for
  `_as_date` (the loader already parses AV's fixed format with stdlib — ADR-003 — so reuse it);
  regenerating the whole price series (would churn the S12 assertions for no benefit).
- **Consequences:** Enlarging the fixtures changed the offline counts the S11 `tests/test_loaders.py`
  hard-coded, so those assertions were recomputed to the new fixtures (loaders **unchanged**). F02 →
  `passing`; M1 (data layer) acceptance — "`test_no_lookahead` green; one observation prints" — is met.

## ADR-004 · S12 indicator conventions (annualized vol, SPY trend, NaN warm-up)
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** In `compute_indicators` / `compute_spy_trend`: (1) **`vol20` is annualized** — daily
  return std over `vol_window` × √252 — so it matches the semantics of `config.vol_cap` (an annualized
  cap used by the PositionManager). (2) **`spy_trend` = (last_close − MA20) / MA20** (>0 uptrend, <0
  down; 0.0 when history is insufficient). (3) **Warm-up rows surface honest `NaN`** (not back-filled);
  `render_indicators` shows `n/a`. (4) **MACD uses `ta` defaults (12/26/9)** — not a config knob, since
  the plan's tunable windows are only `rsi_period`/`ma_short`/`ma_long`/`vol_window`/`mom_window`.
- **Reason:** Annualized vol is the interpretable, standard form and keeps one consistent vol unit
  across indicators and the risk veto. A simple price-vs-MA20 trend is enough market/beta context for
  the MacroAgent (YAGNI). Surfacing NaN rather than back-filling preserves point-in-time honesty.
- **Rejected alternatives:** raw (non-annualized) daily vol (would mismatch `vol_cap`); MA-slope or
  multi-window SPY trend (more knobs, no clear benefit yet); back-filling warm-up indicators (hides
  insufficient history, a subtle lookahead-flavored distortion).
- **Consequences:** Added indicator-window knobs to `config.py`. `Observation` is now `frozen=True`
  with render/memory/serialize helpers + a fail-loud `__post_init__`. `ta` added to
  `requirements-dev.txt` (offline indicator tests). F02's gate is implemented in S12; the dedicated
  `tests/test_no_lookahead.py` sweep + `F02 -> passing` land in S13.

## ADR-003 · S11 data layer: yfinance prices / AV news, stdlib timestamp parse, loader snapshot
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** Implemented S11 with two adapters — `src/data/yahoo.py` (prices, key-free) and
  `src/data/alpha_vantage.py` (news only) — behind `read_or_fetch` (Parquet cache-aside) and the three
  Repository loaders. Three small choices made during implementation:
  (1) **`--mode download` prints a point-in-time data snapshot** (the inputs an `Observation` is built
  from), not a full rendered `Observation` — because `Observation`/`compute_indicators`/`get_observation`
  belong to **S12**. The full Observation print lands in S12 (avoids a circular dependency).
  (2) **stdlib `datetime.strptime`** parses AV's fixed `YYYYMMDDTHHMMSS` format instead of adding
  `python-dateutil` — one fewer dependency (the plan had listed dateutil).
  (3) **Loaders cap at `config.max_news_per_day`** (newest-first) so a daily decision sees recent
  headlines rather than all news since 2022; `relevance_cutoff` applies to AAPL only, never macro.
  Also: added `pandas/numpy/pyarrow` to `requirements-dev.txt` (the offline data tests need them) and
  `yfinance>=0.2.40,<0.3` to `requirements.txt`; aligned pandas/numpy/pyarrow pins to installable
  versions (2.2.3 / 2.4.4 / 23.0.1).
- **Reason:** Stay within the substep's scope (don't pull S12 forward), keep dependencies minimal
  (`follow-the-plan`), and bound per-day news to something an agent can actually read. A version range
  for yfinance (an unofficial scraper) is more robust than a brittle exact pin.
- **Rejected alternatives:** building a partial `Observation` in S11 (hacky, half-built object);
  `python-dateutil` (unneeded for AV's fixed format); returning all news `<= t` uncapped (unbounded,
  unrealistic for a daily decision).
- **Consequences:** S11 plan doc reconciled to say "data snapshot (full Observation in S12)". F03 →
  `passing` (offline). The live online `--mode download` is pending the user's one-time premium run
  (monthly windows, `sort=LATEST`, `limit=1000`; dense months may truncate at 1000 — acceptable, the
  relevance filter trims overflow). `data/SPY_prices.parquet` path is derived per-symbol.

## ADR-002 · Memory reward = AAPL-drift-demeaned return, not SPY-adjusted (corrects spec §7.1)
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** The episodic-memory reward (the teaching signal stored per episode) is the
  **AAPL-own-drift-demeaned** forward return:
  `reward = sign(action) · (forward_return(t,h) − μ)`, with `forward_return(t,h) = P[t+1+h]/P[t+1] − 1`
  and `μ` = AAPL's trailing average `h`-session return, computed point-in-time (data ≤ t). It is
  **not** market-adjusted against SPY. Exposed as `config.reward_benchmark ∈ {raw, aapl_drift}`
  (default `aapl_drift`) and treated as an ablation. Reported PnL stays raw, net of fees.
- **Reason:** Two failure modes to avoid. (1) *Raw* reward has a positive drift bias → in a bull
  market "always long" earns reward with zero skill. (2) *SPY-adjusted* reward (`forward − SPY_return`,
  the spec §7.1 wording) is wrong for a **single-asset** agent whose action space is AAPL-only
  {long, flat, short}: SPY's realized return is large and can exceed AAPL's, flipping the sign so the
  reward perversely ranks *shorting a stock that rose* (but lagged the index) as the best action.
  Demeaning by `μ` (the mean) removes the drift bias **and** keeps the long-vs-short decision boundary
  at ≈0 (`long ≻ short ⟺ forward > μ ≈ 0`), so the action that actually made money stays best-rewarded.
  Principle: *center out the bias, don't swap in a different (un-actionable) benchmark.* Also note the
  spec's literal "benchmark = buy & hold AAPL" self-cancels to 0, confirming it was an error.
- **Rejected alternatives:** *Raw sign-weighted* (keeps the always-long bias); *SPY / market-adjusted*
  (inverts the reward for a single-asset agent — see above); *vs buy-&-hold AAPL* (long episodes → 0,
  uninformative). "Beat the market" belongs in the **evaluation layer** (baselines + Sharpe), not the
  memory teaching signal.
- **Consequences:** Adds `reward_benchmark` (+ a point-in-time trailing-`μ` window) to `config.py`; the
  reward must compute `μ` without lookahead. `flat` actions get reward 0 (`sign(0)=0`) → memory cannot
  learn from good flat calls (accepted simplification). Benchmark choice becomes a robustness ablation.
  Updated: `PLAN.md` Step 3 + `CLAUDE.md` data note.

## ADR-001 · Project-local `.venv`; split dev vs full runtime
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** `make setup` creates a project-local `.venv` and installs only dev tooling +
  minimal runtime (`requirements-dev.txt`). The heavy stack (langchain, faiss, vectorbt, ta,
  sentence-transformers) lives in `requirements.txt`, installed separately by `make setup-full`.
- **Reason:** The scaffold (M0) imports none of the heavy stack — its imports are function-local — so
  `make check` must not depend on a slow/fragile build. Isolating in `.venv` protects the user's
  existing conda env (`finrl_env`) from accidental dependency downgrades (e.g. numpy).
- **Rejected alternatives:** (a) one `requirements.txt` installed by `make setup` — slow, risks
  breaking the scaffold gate and the user's env; (b) installing into the active conda env — could
  downgrade numpy 2.2 for vectorbt/numba and corrupt unrelated work.
- **Consequences:** Contributors run `make setup-full` before M1+ work that actually executes the
  pipeline. vectorbt ↔ numpy 2.x compatibility must be validated then.

## ADR-000 · `make check` is the single source of truth
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** "Is the code OK?" is answered only by `make check` (= lint + typecheck + test + e2e).
  No other ad-hoc judgement counts; `features.json` evidence and commits cite it.
- **Reason:** A single, executable, reproducible gate removes ambiguity and lets the verifier_agent /
  CI / hooks all agree. Aligns with spec §13's evidence-first DoD.
- **Rejected alternatives:** Per-tool manual checks (drift, inconsistent); trusting agent self-reports
  (not reproducible).
- **Consequences:** Every feature needs an executable verification; the pre-commit hook runs the gate.
