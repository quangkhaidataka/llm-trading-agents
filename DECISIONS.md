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
