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

## ADR-026 · S6.1 web report: token-replace template, reads artifacts only, ablations skipped for reporting
- **Date:** 2026-06-26
- **Status:** accepted
- **Decision:** `src/eval/report.py::build_report_html(equity_csv, trace_json, out_path)` builds ONE
  self-contained `results/report.html` (F18): a Plotly cumulative-PnL chart (strategy vs buy & hold) whose
  daily points are clickable, with the entire per-day decision trace embedded inline as JSON and a
  `plotly_click` handler that paints the clicked day's reasoning (news read · each analyst signal+rationale ·
  bull/bear/thesis · conviction · final call+reason) into a side panel. Three implementation choices:
  (1) **Token `str.replace` (`__PLOTLY_CDN__`/`__CHART_JSON__`/`__TRACE_JSON__`) instead of `str.format`** —
  the page is mostly JS/CSS, so `.format`'s `{{`/`}}` brace-doubling would be pervasive and error-prone; the
  plan's skeleton named `.format` holes but it is "structure + intent only", and token-replace is the simpler
  faithful realization (same two data holes, same self-contained output). (2) **`_build_chart_figure` prefers
  `cum_pnl_*` columns, falls back to `equity_*`** — matches the Step-4 CSV that exists on disk while honoring
  the plan's "or `cum_pnl_*`" note. (3) **HTML-escape (`esc`) in the browser, not Python** — the trace is
  embedded as JSON (safe) and rendered to HTML client-side, so escaping lives next to the DOM write.
- **Headline-result wiring:** the user fixed the blog/headline result to the **`tau05online`** live run
  (`tau_enter=0.50`) **truncated to ≤ 2026-05-01** (333 of 366 sessions). The committed sample `report.html`
  is built from truncated artifacts derived from the full run — `equity_curve_tau05online_thru01May2026.csv`
  + `trace_tau05online_thru01May2026.json` (the full run minus rows/records dated > 2026-05-01) — so the
  chart and the click-to-explain panel both end exactly at the headline endpoint (no post-cutoff data,
  incl. the May AAPL rally, leaks into the page). `build_report_html` is path-generic, so this is just a
  choice of inputs, not a code change. The user also **decided to stop running the ablation suite** (S53/F14
  code stays, but `--mode ablation` is not re-run) — final reporting (S6.3 notebook/README) leads with the
  headline result, not an ablation table.
- **Reason:** explainability is the deliverable, not styling — one chart + one panel, zero new dependency
  (Plotly via CDN, stdlib + pandas), self-contained so a reviewer double-clicks it. Reading
  `equity_curve.csv` + `trace.json` only (never recomputing) keeps the report a pure view over Step-4
  artifacts, so it can never disagree with the backtest or reintroduce look-ahead.
- **Rejected alternatives:** Flask/Dash/Jinja or a served app (YAGNI; a static file is more portable and
  committable); `str.format` with brace-doubling (noisy/fragile across the JS); recomputing PnL/metrics in
  the report (would duplicate Step-4 and risk divergence); an external `report.json` loaded via `fetch`
  (breaks open-from-disk + adds CORS); wiring a `--mode report` CLI (not in the plan; the `python -c`
  acceptance command + the notebook link suffice).
- **Consequences:** no new `requirements.txt` entry; `results/report.html` gitignored (committable as a
  sample). `tests/test_report.py` (4) + ruff + mypy clean on the new files; full unit suite 112 passed.
  **Repo-wide `make check` is red ONLY on a pre-existing unrelated lint line** (`config.py:56` >120 chars,
  owned by the user) — no S61 code is implicated. F18 → `passing`. S6.3 (notebook/README) links this report
  as the headline explainability demo.

## ADR-025 · Calibration hit-label = target_direction (the debate's VIEW), not the executed action
- **Date:** 2026-06-25
- **Status:** accepted (revises the hit-label choice in ADR-019, for CALIBRATION only)
- **Decision:** The conviction calibrator's hit label now grades the debate's proposed **`target_direction`**
  (was the executed `decision.new_position`), and days where the debate proposed **no view (`target == 0`)
  are EXCLUDED** from the calibration set. The first live warm-up (executed-action label) produced a
  degenerate calibration: 316 flat days were labeled hit=0 (a flat day is "no bet", not a "wrong bet"), the
  calibrated conviction maxed at 0.667, and the hit-rate at low conviction was 34% (BELOW coin flip — the
  pollution signature), so `tau_enter=0.60` would have traded ~3 days in 3 years. `tau_enter` gates the
  ENTRY decision, so the correct calibration target is "given conviction z, is the proposed DIRECTION
  correct?" — independent of whether veto/hysteresis let us act. Implementation: added `target_direction` to
  the per-day trace (`_write_trace`); `collect_warmup_pairs` reads it (`_read_trace_fields`), skips
  `target==0`, and grades it via `_hit_label`; the **memory reward stays executed-action** (different
  purpose — "what happened when we took this action"). Re-run cost **$0** (cache-backed, ADR-020).
- **Result (warm-up 2022-2024, 617 view-day pairs):** the calibration is now **monotonic & meaningful** —
  hit-rate rises with conviction (46.7% base → 49% → 55.6% @0.50 → 66.7% @0.55-0.64 → 72.7% @0.65+);
  calibrated range 0.42-0.73; Brier 0.327→0.245. **Headline finding:** the LLM's raw directional calls have
  ~no aggregate edge (46.7% hit, below coin flip), but the COMPUTED conviction successfully sorts them (high
  conviction → 55-72% hit) — i.e. the spec §7.3 "conviction is math, not the LLM's self-report" contribution
  works. `tau_enter=0.60` is now validated (trades 39 view-days @66.7%), vindicating the ADR-018 prior once
  the label was de-polluted.
- **Reason:** Calibrating P(directional view correct | z) is what the entry threshold actually needs;
  counting "no bet" as a miss conflated abstention with error and made the calibrated scale unusable. The
  re-run is free (cache), so the better label has no cost.
- **Rejected alternatives:** keep the executed-action label + just lower `tau_enter` to ~0.40 (thresholds a
  polluted number; non-monotonic; only 3 days of headroom above 0.50); change the memory reward too
  (different purpose — memory records the action taken, not a hypothetical view); include `target==0` days
  as a third class (no directional outcome to grade).
- **Consequences:** `make check` green (107 unit + e2e). `target_direction` now in the trace (also enriches
  the Step-6 report). The frozen `results/calibrator.pkl` + warmed `data/AAPL_memory/` reflect the new label.
  Open items for the threshold freeze: pick `tau_enter` 0.50 (more active) vs 0.60 (selective); note
  `tau_exit=0.40` is below the calibrated floor (0.42) so conviction-decay exits never fire (thesis-only
  exits). In-sample only — the 2025-2026 test is the generalization check.

## ADR-024 · Backtest fee is COMMISSION-ONLY (fee_bps 7.5 → 1.0); spread/slippage is execution, not strategy
- **Date:** 2026-06-25
- **Status:** accepted (revises the 7.5 default from ADR-012)
- **Decision:** `config.fee_bps` lowered from **7.5 → 1.0 bp** per position change. Rationale: the strategy
  backtest should charge only the **unavoidable commission** (~1 bp institutional equity commission,
  ≈ $0.01–0.02/share on a ~$200 stock). **Bid-ask spread and slippage/market-impact are execution/impact
  effects** — they depend on HOW an order is worked (timing, size, venue), belong in a separate execution
  model, and are not a property of the daily target the strategy emits. Conflating them into the strategy
  fee penalizes the *signal* for an *execution* cost. The fee MECHANISM is unchanged (ADR-012): charged only
  on a position change, `(fee_bps/1e4)·|Δnotional|`, a flip crosses zero → double.
- **Reason:** Clean separation of concerns — the backtest measures the policy's gross edge net of the cost
  it actually controls (commission); execution quality (spread/slippage) is a distinct, separately-modeled
  question. Keeping a small non-zero commission (vs $0 retail) still gives turnover an honest price, so the
  churn signal isn't erased.
- **Rejected alternatives:** keep 7.5 bps (bundles ~6.5 bp of spread/slippage the strategy doesn't control —
  punishes the signal for execution); 0 bps retail commission-free (erases turnover cost entirely — the
  churn problem would look free, which is misleading); 0.5 bp (defensible low-commission, but 1 bp is the
  more standard institutional figure). Spread/slippage are best added later as an explicit **execution
  sensitivity** in S62 (e.g. impact in {0, 5, 10} bp) so their effect is shown, not silently bundled.
- **Consequences:** `make check` green (107 unit + e2e) — the fee test asserts the flip=2×open RATIO, which
  is rate-independent, so nothing broke. The next backtest will show a much smaller fee drag (the first run's
  $59.7k @ 7.5bp → ~$8k @ 1bp on the same 80 trades) — note this REVEALS that the prior "40% of gross eaten
  by fees" was largely a spread/slippage assumption, not commission; the turnover is still worth reducing,
  but its *commission* cost is modest. `fee_bps` remains a config knob; fee/impact sensitivity is a natural
  S62 robustness axis.

## ADR-023 · A2: FAISS memory persistence (warm-up memory now survives into the test)
- **Date:** 2026-06-25
- **Status:** accepted (resolves the ADR-019 deferral)
- **Decision:** `MemoryStore` gained `save(path)` / `load(path)` so the warmed episodic memory survives
  across processes: `save` writes the FAISS index (`faiss.write_index`) + a pickle of the `{closed, pending}`
  Episode lists to `config.memory_path()` (= `data/{ticker}_memory/`, gitignored via `data/*_memory/`);
  `load` restores them (no-op if absent). Wiring: (1) `collect_warmup_pairs` (S5.1) calls `store.save()` at
  the end, so `--mode warmup` persists the memory it warmed over 2022-2024; (2) `Backtester.run` does
  `store.load()` **only when `not config.offline`** — the test warm-starts from disk online, while offline
  stays hermetic (cold start, independent of any `data/{ticker}_memory` on disk — same gating as the
  calibrator, ADR-019). Both `closed` (1:1 with index rows) and `pending` (not-yet-closed) episodes are
  carried, so a window that opened near `warmup_end` can still close point-in-time early in the test.
- **Reason:** Without this, `--mode warmup` and `--mode backtest` are separate processes, so the in-memory
  store (ADR-009) was discarded between them — the test always started memory-cold and the "warm the memory"
  job of the warm-up (1 of its 3 jobs) was never realized. The first live backtest's memory contribution was
  therefore ~nil and the no-memory ablation would have looked unfairly similar to the real system; this
  closes that gap so S5.1's warm-up actually warms something that lasts.
- **Anti-lookahead:** save/load NEVER reset `outcome_closed_t`; `retrieve` still filters
  `outcome_closed_t <= obs.t`. Warm-up episodes are all from 2022-2024 (the past relative to the 2025-2026
  test) so retrieving them in-test is legitimate prior experience, not leakage; carried `pending` episodes
  have `outcome_closed_t=None` → not retrievable until they flush in-test. `test_no_lookahead` +
  `test_delayed_write_retrievable_only_at_t_plus_1_plus_h` stay green; `check-lookahead` clean.
- **Rejected alternatives:** JSON for the episodes (Episodes hold `date` objects → pickle is cleaner, same
  choice as `calibrator.pkl`); persisting only `closed` (would drop boundary `pending` episodes whose window
  closes in the test); a numpy-cosine store to dodge faiss serialization (faiss `write_index`/`read_index`
  is the standard, already a dependency); auto-loading offline too (would make `make check` depend on a
  gitignored artifact — gated to online instead).
- **Consequences:** `make check` green (107 unit + e2e, +2 memory tests: save→fresh-load→retrieve round-trip,
  and load-is-noop-when-absent). The S5.1 warm-up's memory is now real; running `--mode warmup` then
  `--mode backtest` carries the warmed FAISS index into the test. `config.memory_path()` added; `data/*_memory/`
  gitignored. No feature flips (this hardens F07/F11/F15); the S5.1 DoD's "FAISS persistence deferred" note is
  now resolved.

## ADR-022 · S5.3 ablations: config-toggle variants over one engine; use_hysteresis + run(write=) wired
- **Date:** 2026-06-25
- **Status:** accepted
- **Decision:** `src/eval/ablation.py` realizes the five ablations + `full` as a dict of **config-toggle
  overrides** (`ABLATION_VARIANTS`), each applied via `dataclasses.replace` (`make_variant_config`) and run
  through the SAME `Backtester` loop + frozen calibrator — never a code fork. `run_ablations` runs every
  variant, stacks the 6 rows + the 3 S5.2 baselines into one `results/ablation_table.{csv,md}`, and writes
  per-variant curves under `results/curves/`. Three enabling choices: (1) **`use_hysteresis` is now wired**
  into the PositionManager — when False, the exit bar collapses to `tau_enter` (no asymmetric dead-band),
  resolving the deferral from ADR-010/011; `stateless` was already handled in `run_one_day`. (2) **Added
  `Backtester.run(write: bool = True)`** — a variant runs with `write=False` so it reuses the identical
  think→account→metrics path WITHOUT clobbering the main backtest's `results/` artifacts; this is the
  minimal seam that makes the loop reusable (ADR-012 already built `_run_accounting` pure for exactly this).
  (3) The Markdown table is written **manually** (pipe rows) rather than `DataFrame.to_markdown` to avoid
  adding a `tabulate` dependency.
- **Reason:** "ablations are toggles, not forks" is the spec's scientific-rigor rule — one engine, one
  accounting, one flag flipped, so each table row is a clean attribution. Wiring `use_hysteresis` at the
  PositionManager (where hysteresis lives) keeps the flag changing *behavior at the decision point*, like
  the other flags change what nodes produce. `write=False` is a backward-compatible toggle, not a refactor.
- **Rejected alternatives:** collapsing the band via a config transform in `make_variant_config`
  (`tau_exit:=tau_enter`) instead of a PositionManager flag (hides the semantics outside the manager; the
  flag belongs where hysteresis is applied); redirecting each variant's `results_dir` to a temp dir to avoid
  clobber (wasteful — renders 6 throwaway charts; `write=False` is cleaner); adding `tabulate` for one MD
  table (unnecessary heavy dep); running the ablation test over the full ~45-session window (6 variants ×
  full backtest ≈ minutes — used a ~6-session window where each obs still carries full history ≤ t, ~11s).
- **SCOPE (stretch experiments deferred):** the S5.3-amendment experiments — `risk_off` veto
  persistence/size-down, `min_holding_days` / dead-band turnover control, shorts-on/off + warm-up
  short-expectancy — are NOT built here; per the amendment they are stretch rows that must not block F14.
  The config knobs + logic are a follow-up.
- **Consequences:** `make check` green (105 unit + e2e); F14 → `passing`. `--mode ablation` produces the
  comparison table + per-variant curves; the AV-sentiment row is the one to beat. Variants reuse the LLM
  cache (ADR-020) + the frozen calibrator (ADR-019), so the live ablation suite is ~free after the main
  backtest has warmed the cache. S6 reporting reads `ablation_table.*` unchanged.

## ADR-021 · S5.2 baselines: single-agent driven directly, all baselines share the Step-4 loop
- **Date:** 2026-06-25
- **Status:** accepted
- **Decision:** `src/eval/baselines.py` builds the three yardsticks, each reduced to a per-day `targets`
  list pushed through the SAME `Backtester._run_accounting` dollar loop + `compute_metrics` (one shared
  `_run_targets` helper), so only the decision rule varies and any gap is attributable to the protocol, not
  the accounting. Non-obvious choices: (1) **Single-agent (NewsAgent-only) is driven DIRECTLY** — loop the
  days, call `NewsAgent.run(obs, flat)`, trade `sign(news.signal)` — rather than running the LangGraph with
  flags. The plan said "run the engine with macro/technical/memory/debate bypassed", but there is no
  `use_technical` flag and the `use_debate=False` fallback stance aggregates news AND technical, so it could
  not yield a *news-only* decision; driving the agent directly is the faithful, simpler realization (still
  one cached LLM call/day, stateless daily classifier). (2) **Buy & hold also goes through the shared loop**
  (`targets = [+1]*n`), so it is **t+1-executed** (flat session 0, one entry fee) — it differs from the
  Step-4 chart's day-0 `C0·P[t]/P[0]` reference line by a 1-session lag + one fee, ON PURPOSE: same t+1
  treatment as the strategy makes the table comparison fair (the chart keeps its own reference line). (3)
  **AV-sentiment** = mean `av_sentiment` over the gate's relevance-filtered AAPL news ≤ t → `sign` → target
  (`-1` only if `allow_short`); the AV score is the **baseline-to-beat, never the system's signal**
  (security-rules). (4) `run_baselines` emits the **corr(LLM_sentiment, AV_score)** diagnostic (evidence the
  NewsAgent is not echoing AV). (5) Reusing the "protected" `_run_accounting` is the intended reuse — ADR-012
  built it as a pure function precisely so baselines/ablations share the exact accounting.
- **Reason:** Sharing one accounting path is the whole point of a fair baseline; direct NewsAgent drive
  avoids inventing a `use_technical` flag the plan never specified (YAGNI) while delivering the exact
  "news-only" semantics the baseline needs.
- **Rejected alternatives:** adding a `use_technical` flag + routing single-agent through the graph (more
  surface, not needed); buy&hold as the fee-free `C0·P[t]/P[0]` line in the table (inconsistent t+1 vs the
  strategy — kept only as the chart reference); using AV score as a system input (launders AV's alpha);
  per-baseline standalone tests (3× redundant `get_observation` loops → 150s suite; a module-scoped
  `run_baselines` fixture computes them once → ~67s).
- **Consequences:** `make check` green (99 unit + e2e); F13 → `passing`. `results/curves/baseline_*.csv`
  written; the metric rows + the corr diagnostic are folded into the S5.3 `ablation_table`. The baselines
  reuse the LLM cache (ADR-020), so the live single-agent baseline is ~free after the main backtest has run
  the same NewsAgent prompts/dates. Suite is ~30s slower (the `get_observation` gate over the window); a
  gate-level memoization is a possible future perf win, out of scope here.

## ADR-020 · Persistent LLM cache (prompt-hash keyed) — reruns/ablations cost no API calls
- **Date:** 2026-06-25
- **Status:** accepted
- **Decision:** The spec/plan assumed an LLM cache ("reruns are free, cached by (ticker, date, agent)")
  but it was **never implemented** — `config.llm_cache_path()` was defined and referenced nowhere, so
  every live run (warm-up, backtest, each ablation, the h-sweep) paid full API price and took ~1h. Built it
  at the single model seam so no agent changes: `make_llm` now wraps the online backbone (both OpenRouter
  and Groq branches) in `_CachingLLM` when `config.use_llm_cache` (default True; offline/MockLLM is
  untouched). **Key = sha256(rendered prompt messages + schema name + temperature).** Keying on the *exact
  rendered prompt* is the crux: it already encodes ticker/date/news/upstream-signals AND the prompt
  template text, so (a) a hit can only return the response for that identical point-in-time input (no
  leakage — the cache rule in llm-and-prompts.md), and (b) changing a prompt — e.g. this session's Gate-A
  debate prompt (ADR-016) — produces a different hash and MISSES, never replaying a stale answer.
  Temperature is in the key so the DebateAgent's `run()` (temp 0) and `sample()` (temp>0) don't collide.
  Per key we store an **ordered list** replayed in call order, so the K self-consistency samples (same
  prompt, K varied draws) are cached and reproduced faithfully — making conviction reproducible AND free on
  reruns. Storage is **append-only JSONL** at `data/{ticker}_llm_cache.jsonl` (O(1) writes, crash-safe,
  gitignored); a fresh process loads it and replays. Added `config.use_llm_cache`; `llm_cache_path()` →
  `.jsonl`; `.gitignore` gains `data/*.jsonl`.
- **Reason:** The dollar amounts are small (~$8 total across M5/M6) but each live run is ~1 hour and the
  multi-run steps (S53 = 5 ablations, the h-sweep = 4 runs, plus every re-tune iteration) re-pay and
  re-wait without a cache. Keying by the full prompt is more robust than a literal (ticker, date, agent)
  tuple: it is automatically per-agent, point-in-time, AND prompt-versioned, so correctness (no stale
  debate output after the prompt fix) falls out of the key design rather than needing manual invalidation.
- **Why not reuse the existing `logs/` traces (the user's question):** the per-day traces store agent
  *outputs* but not the *input prompt*, are keyed by date for one whole-pipeline config, omit
  `target_direction` + the K debate samples, and were written with the OLD prompt/thresholds — so they
  can't be a safe read-before-call cache. They validated the idea (we already persist agent outputs); the
  cache productionizes it with proper keying.
- **Rejected alternatives:** a literal `(ticker, date, agent)` key (misses the prompt-version safety — a
  changed prompt would replay stale output); caching inside `_StructuredJSON` (entangles cache with the
  JSON-coercion retry logic); a LangChain global `set_llm_cache` (not prompt+temperature aware, wouldn't
  handle K-sample ordering); full-file JSON rewrite per call (O(n²) I/O over thousands of calls); within-run
  dedup of identical prompts (would collapse the K debate samples to one draw — the ordered-list-per-key
  design is what keeps them distinct). Bootstrapping the cache from `logs/` (skipped — the logs lack the
  input prompt to rebuild the hash; cache simply populates on the next run).
- **Consequences:** `make check` green (94 unit + e2e, +5 cache tests covering cold→warm replay, K-sample
  ordering, prompt-change miss, temperature separation, opt-out flag) — all offline via a fake backbone, no
  network. The first warm-up (~$1.20) populates 2022-2024 once; the first backtest (~$0.60) populates
  2025-2026 once; **every subsequent ablation / h-sweep / re-run on those windows is ~free and ~instant.**
  The previously-aspirational "reruns are free" claims in PLAN.md / spec §6 are now TRUE. Caveat: the cache
  only helps a window AFTER it has been run once; a NEW window (or a NEW model/prompt) pays full price the
  first time, as intended.

## ADR-019 · S5.1 conviction calibrator (Layer 3): hit=reward>0, hermetic wiring, FAISS persistence deferred
- **Date:** 2026-06-23
- **Status:** accepted
- **Decision:** Implemented Layer 3 (z → P(correct)) in `src/eval/calibration.py`: a `Calibrator` adapter
  (sklearn `IsotonicRegression` primary; `LogisticRegression`/Platt fallback when n <
  `config.calibration_min_isotonic=200`, to avoid isotonic overfitting), `fit_calibrator`,
  `reliability_diagram` (+ shared `_reliability_stats` → Brier & ECE over `config.calibration_bins`),
  `WarmupPair`, `collect_warmup_pairs`, `run_warmup_calibration`, and `--mode warmup`. Four non-obvious
  choices: (1) **`_hit_label` reuses `MemoryStore._reward > 0`** — since reward = sign(action)·(forward−μ),
  `reward > 0` ⟺ the action's direction agrees with the drift-demeaned forward return, so the hit label is
  *provably identical* to the memory reward rule (DoD requirement) with zero duplicated math; a flat action
  (sign 0) → reward 0 → hit 0. (2) **The label uses the executed `decision.new_position`** (same quantity
  the memory episode stores), not the debate's `target_direction` — keeping "correct" defined one way
  across memory and calibration. (3) **Calibrator wiring is hermetic:** `build_graph(config, store,
  calibrator=_AUTOLOAD)` auto-loads `results/calibrator.pkl` ONLY when `not config.offline` and the file
  exists; offline always uses raw z, so `make check` never depends on a gitignored artifact; warm-up calls
  `build_graph(..., calibrator=None)` so the (z, hit) pairs are the RAW z the calibrator is fit on. (4) An
  **unfitted/one-class Calibrator is the identity** (`predict_proba(z)=z`), so the PositionManager degrades
  gracefully to raw conviction before any calibrator is frozen. `config` gains `calibration_min_isotonic`,
  `calibration_bins`, and a `calibrator_path()`.
- **SCOPE DEVIATION (warm-up FAISS persistence deferred):** the S51 plan Outputs list "warm-up-populated
  FAISS index persisted on disk". This is **not** implemented here — `MemoryStore` is in-memory per process
  (ADR-009 already deferred disk persistence). Consequence: running `--mode warmup` then a separate
  `--mode backtest` does NOT carry the warmed memory into the test (the test starts cold). The calibrator
  IS frozen to disk and carried over (that is F15). To get warm memory into the test, either implement
  FAISS persistence (faiss.write_index + Episode pickle) as a follow-up, or run warm-up + backtest in one
  process. Recorded here per follow-the-plan; S51 plan doc + PLAN.md annotated.
- **Reason:** Reusing `_reward` for the hit label is the DRY-est way to satisfy "identical rule to the
  memory reward". Hermetic, explicit calibrator wiring keeps offline determinism (the project's test
  contract) while letting the live backtest auto-use the frozen artifact. Deferring FAISS persistence keeps
  the substep focused on F15 (the calibrator) — the mapped feature — rather than expanding into a
  store-persistence feature ADR-009 already scoped out (YAGNI for this substep).
- **Rejected alternatives:** duplicating the forward-return/μ math in `_hit_label` (divergence risk vs the
  memory reward); labelling by `target_direction` (two different "correct" definitions); a `use_calibrator`
  config flag (the `_AUTOLOAD`/None/instance sentinel is more explicit and testable); auto-loading the
  calibrator offline (would make `make check` depend on a gitignored file); implementing FAISS disk
  persistence now (out of scope for F15; deferred with this note).
- **Consequences:** `make check` green (89 unit + e2e, +5 calibration tests); check-lookahead clean (the
  forward-looking `_hit_label` is the frozen training label, never a day-t input). F15 → `passing`. The
  LIVE `--mode warmup` over real 2022-2024 data produces `results/{calibrator.pkl, reliability_diagram.png,
  calibration_report.json, warmup_pairs.csv}`; the next backtest auto-applies the frozen calibrator so
  `tau_enter=0.60` finally means P(correct)≈0.60. The re-tuned thresholds (ADR-018) should be validated on
  this same warm-up before the next test run.

## ADR-018 · Re-tuned hysteresis/veto threshold PRIORS (under-investment fix)
- **Date:** 2026-06-23
- **Status:** accepted
- **Decision:** The first full live backtest was **flat 65% of days** (238/366: 152 blocked by the entry
  bar, 86 by the veto) and underperformed buy & hold (+9.1% vs +23.0%). Diagnosis attributed the flatness
  to two binding knobs, which are re-tuned in `config.py`: **`tau_enter 0.70 → 0.60`** (only 115/366 days
  cleared 0.70; the entry bar was the single biggest flatness driver at 152 days), **`tau_flip 0.80 →
  0.70`** (make long↔short flips reachable now that shorts can be proposed — ADR-016/017), and **`vol_cap
  0.40 → 0.50`** (0.40 bound on ordinary AAPL vol ~0.30 and forced flat on 24 days, exactly when a short
  might be wanted). **Kept unchanged:** `tau_exit 0.40`, `macro_risk_cap 0.70` (~never binds — 1 day ever —
  and is redundant with the `risk_off` regime veto), `disagreement_cap 0.70` (only 10 veto days). Ordering
  invariant preserved: `tau_exit 0.40 < tau_enter 0.60 < tau_flip 0.70`. Two PositionManager tests that
  hard-coded conviction/vol values tied to the OLD thresholds were made **config-relative** (derive from
  `cfg.tau_exit/tau_flip/vol_cap`) so they test behavior, not a number.
- **Reason:** The system was "too hard to get into, too easy to shake out of, and flattened on ordinary
  volatility" — a defensive degeneration that traded ~14pp of return for ~20pp less drawdown in a bull
  market. Lowering `tau_enter` + `tau_flip` together (band 0.20) and raising `vol_cap` directly target the
  measured flatness drivers while preserving the asymmetric Schmitt-trigger hysteresis.
- **Rejected alternatives:** lowering `tau_exit` too (would widen the dead-band further but the user chose
  to keep 0.40); tuning the categorical `risk_off` veto here (it is not a number — deferred to an S5.3
  persistence/size-down experiment); lowering `macro_risk_cap` (would duplicate the risk_off veto and force
  MORE flat); leaving thresholds at the spec defaults (the first live run is evidence they were too strict).
- **Consequences — IMPORTANT (these are PRIORS, not fitted values):** the numbers were set from
  *diagnosing which knob was binding on the 2025–2026 TEST window* (legitimate debugging), NOT by fitting
  the test curve. They **must be confirmed and frozen on the 2022–2024 warm-up** (S5.1) alongside the
  calibrator before the next test run; tuning a threshold to improve the test curve would be look-ahead on
  the eval set (spec §12.1). Also note `conviction` remains **raw z (uncalibrated)** until S5.1, so these
  bars do not yet mean true probabilities. `make check` green throughout. PLAN.md Step 5 + S32/S51
  amendments record the same priors + the freeze-on-warmup discipline.

## ADR-017 · Gate-B: abstention-aware agreement (a flat agent no longer dilutes a lone short)
- **Date:** 2026-06-23
- **Status:** accepted
- **Decision:** Second half of the never-shorts fix (after the ADR-016 prompt change, "Gate A"). The
  Layer-1 conviction `agreement` was direction-blind AND diluted by abstainers: `agreement = |Σ sᵢcᵢ| /
  Σ cᵢ` summed confidence over ALL agents in the denominator, so a *flat* agent (`sᵢ=0`, which contributes
  nothing to the numerator) still inflated the denominator and pushed `agreement` down. Effect: when the
  TechnicalAgent was confidently short but the NewsAgent abstained (flat), the lone short's `z` was
  suppressed below `tau_enter` and never opened. Fix (one-line, in `composite_conviction`,
  `src/eval/calibration.py`): sum the denominator over **directional agents only** —
  `agreement = |Σ sᵢcᵢ| / Σ_{sᵢ≠0} cᵢ` (guard: no directional agent → 0). A flat vote is now an
  **abstention** — it neither reinforces nor dilutes. `mean_confidence` is left over ALL agents (the mild
  abstainer dampening there is intentional and conservative). The numerator is unchanged (flat agents were
  already 0 there). New unit test: news-flat + technical-short(0.6) now gives `agreement = 1.0` (was
  0.6/1.1 = 0.545), and with a self-consistent short debate `z ≥ tau_enter`.
- **Reason:** The dilution was an accidental property of putting abstainers in the denominator, not a
  deliberate design — an agent with "no view" should not veto a confident peer's directional conviction.
  This is the structural other half of the short fix: ADR-016 lets the debate *propose* `-1`, ADR-017 lets
  that `-1` *clear the conviction bar* when it's a genuine minority view. Both are needed for the system to
  short. Keeping it in the conviction math (not a PositionManager special-case) preserves "direction from
  the debate, magnitude from math" (spec §7.3).
- **Rejected alternatives:** weighting agreement by directional *coverage* (`× Σ_{≠0}c / Σc`) — reintroduces
  the dilution we are removing; making a lone signal auto-max conviction via `mean_confidence` too (drops
  the conservative dampener with no benefit); lowering `tau_enter` further to force shorts (treats the
  symptom — the minority view should clear the bar on merit, not by lowering the bar for everything);
  a PositionManager rule that converts a strong-bearish aggregate into a short (moves the directional
  decision out of the debate/conviction layer).
- **Consequences:** `composite_conviction` denominator change only; `make check` green (84 unit + e2e, +1
  test). The existing all-directional test is unaffected (its denominator was already all-directional). The
  behavioral lift to short *frequency* is best measured after S5.1 calibration re-scales `z`; the
  threshold/short-expectancy validation stays a warm-up-only step (S5.1/S5.3). PLAN.md Step 2 + S23 already
  describe this formula; this ADR records the rationale.

## ADR-016 · Debate prompt decouples SHORT from FLAT (fix the never-shorts degeneration)
- **Date:** 2026-06-23
- **Status:** accepted
- **Decision:** The first full live backtest never opened a short (0 / 366 days) despite
  `allow_short=True` and a PositionManager that fully supports shorting — the short direction was dying
  upstream in the DebateAgent. Root cause was the **prompt**, not the code: `DEBATE_SYSTEM` Step 2 framed
  the bear case as the argument to be "**short/flat**", lumping the two into one bucket, and Step 4 gave no
  rule for mapping a bearish view onto `target_direction`. Given the LLM's long/flat behavioral prior plus
  the prompt's continuity bias, every bearish view collapsed to **flat** (close/stay out), never **short**.
  Fix (prompt-only, no schema change): (1) **Step 1/2 reframed directionally** — Step 1 = "the argument
  that {ticker} will RISE (be LONG)", Step 2 = "the argument that {ticker} will FALL (be SHORT) — a real
  downside thesis, NOT merely 'sit out'". (2) **Step 4 now carries an explicit direction-mapping**: `+1`
  when the bull case dominates, `-1` when the bear case dominates ("a real downside edge is a reason to
  SHORT; do NOT collapse it into flat out of caution"), `0` ONLY for genuine no-view/too-risky-to-hold —
  with the line "SHORT and FLAT are different decisions". The continuity/HOLD bias and the
  `flip-only-on-strong-evidence` rule are unchanged.
- **Reason:** This is the smallest change that addresses the user's long/short/flat requirement. The
  never-shorts behavior was ~entirely linguistic (short conflated with flat), so it belongs in the prompt
  — the A2A contribution is the prompt protocol. The `ResearchStance` schema already exposed
  `target_direction ∈ {-1,0,1}`; no schema/code change was needed.
- **Rejected alternatives:** lowering `tau_flip`/`tau_enter` to force shorts (treats a symptom — the model
  still wasn't *proposing* -1); a code rule that converts a strong-bearish-signal aggregate into a short
  (moves the directional decision out of the debate, violating "debate decides direction, PositionManager
  decides sizing/hysteresis"); changing the schema (unnecessary — the field already existed).
- **Consequences:** Behavioral change is **live-only** — offline `MockLLM` ignores prompt text and cycles
  canned responses, so `make check` (83 unit + e2e) is green but does NOT exercise the new instruction; a
  1-day live smoke on a bearish-consensus session is needed to confirm a `-1` now surfaces. Items #2–#4
  from the diagnosis (directional/undiluted conviction for the minority view, `tau_flip` re-tuning) are
  deferred and best measured AFTER S5.1 calibration re-scales `z`. The offline fixture still has no short
  `ResearchStance`, so the offline backtest remains long/flat — to exercise a short end-to-end offline,
  add a `target_direction:-1` entry to `fixtures/llm_responses.json` (separate task).

## ADR-015 · OpenRouter backbone (Groq free tier blocked the full run)
- **Date:** 2026-06-20
- **Status:** accepted (supersedes the "Groq-only" narrowing in S21/ADR-006)
- **Decision:** Groq's Dev tier is unavailable and its free tier can't complete the backtest (ADR-014), so
  **OpenRouter is added as a second online backbone** — exactly the swappable-backbone the architecture
  was built for (spec §12.2 / RQ4 / F16), so the change is confined to the single seam `make_llm` plus
  config. Specifics: (1) `_StructuredGroq` generalized to **`_StructuredJSON`** (provider-agnostic JSON-mode
  + client-side `PydanticOutputParser` coercion) and used by BOTH the groq and openrouter branches;
  `_groq_rate_limiter` generalized to `_shared_rate_limiter(rps)`. (2) New `make_llm` branch
  `provider=="openrouter"` uses `ChatOpenAI` against `base_url=https://openrouter.ai/api/v1`, the SAME
  Llama 3.3 70B (`meta-llama/llama-3.3-70b-instruct`, Dec-2023 cutoff → **anti-lookahead claim intact**),
  with optional single-provider pin via `extra_body={"provider":{"order":[...],"allow_fallbacks":false}}`
  for reproducibility (`config.openrouter_provider`; "" = auto-route). (3) `config.provider` default flipped
  to `"openrouter"`; the **Groq branch is kept unchanged** so switching back is one config line. (4) Added a
  `field_validator(mode="before")` on **`ResearchStance.target_direction`** to coerce a string `"1"` →
  `1`: Pydantic coerces str→float/bool but NOT str→`Literal[int]`, and OpenRouter's provider stringifies
  it. Config gains `openrouter_model/base_url/provider/requests_per_second/max_retries` + `openrouter_api_key`
  (from `.env`); `requirements.txt` re-adds `langchain-openai==0.3.35`.
- **Reason:** OpenRouter is pay-as-you-go (no Dev-tier waitlist), cheaper (~$0.10/$0.32 per M tok → full
  backtest ~$0.60), has no 100k-tokens/day cap, and serves the identical model so the research claims hold.
  Keeping both backbones behind `config.provider` is the design's whole point and advances F16.
- **Rejected alternatives:** Groq Dev tier (unavailable); a direct provider like DeepInfra/Together (fine
  and even more reproducible, but OpenRouter is more flexible and a provider pin recovers reproducibility);
  loosening the `Literal` field type (the before-validator is the sanctioned schema hardening).
- **Consequences:** dev venv now has `langchain-openai`; `make check` green (83 unit + e2e), offline
  unaffected (MockLLM). The full live 2025-2026 backtest is now runnable for ~$0.60. For strict
  reproducibility set `openrouter_provider` to one backend. S21 plan doc updated.

## ADR-014 · Live-run hardening (Groq json_mode, OpenMP, rate-limit) + free-tier finding
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** The first real online run surfaced three issues invisible offline (MockLLM); all three are
  fixed at the LLM/memory seam without changing the agent/Schema contract:
  (1) **Groq structured-output coercion.** Llama-3.3 tool-calling emits numeric/boolean fields as STRINGS
  (`"conviction":"0.6"`, `"target_direction":"1"`, `"thesis_still_valid":"false"`) and Groq's server-side
  tool validation rejects them. `make_llm` now wraps ChatGroq in `_StructuredGroq`, whose
  `with_structured_output` uses **JSON mode + a client-side PydanticOutputParser** (which coerces those
  strings) and appends the parser's format instructions to the prompt. `method="json_schema"` is
  unsupported by this model; `function_calling` is flaky on complex prompts.
  (2) **OpenMP crash.** faiss and torch (sentence-transformers, the online embedder) each bundle libomp;
  loading both aborts on macOS ("OMP: Error #15"). `src/memory/store.py` sets
  `KMP_DUPLICATE_LIB_OK=TRUE` before either loads.
  (3) **Rate-limit resilience.** A live run must survive Groq's caps: `make_llm` adds `max_retries`
  (`config.groq_max_retries=6`) and a **process-wide shared** `InMemoryRateLimiter`
  (`config.groq_requests_per_second=0.1`) so all agents throttle against one global budget.
  Also: fixed the bad `requirements.txt` pin `langchain-groq==0.3.10` (nonexistent) → `0.3.8`, and dropped
  `langchain-openai` (Groq-only since S21). The heavy online deps (`langchain-groq`, `sentence-transformers`/
  torch) live in `requirements.txt` (`make setup-full`), NOT the dev venv; **note `make setup-full`
  installs `vectorbt` which pins numpy<2 and would break the numpy-2.4.4 dev venv — install only
  `langchain-groq` + `sentence-transformers` for a live run (vectorbt is unused, ADR-012).**
- **FINDING (Groq free tier blocks the full backtest):** the live pipeline works end-to-end (verified:
  5 real sessions Jan 2025 — open long @ conviction 0.88, close on thesis-invalidation, macro risk_off
  VETO; strategy +0.58% vs buy&hold -0.47%, net of fees). But the **free tier caps at ~12k tokens/min
  AND 100k tokens/DAY**; at ~12.5k tokens/backtest-day the full 366-session run needs ~4.6M tokens
  (~46 days of free quota). The full 2025-2026 run therefore requires a **paid Groq tier** (the 429 says
  "Upgrade to Dev Tier"). The offline pipeline remains fully deterministic + free for `make check`.
- **Reason:** these are real-world integration robustness fixes; they belong at the single model seam
  (`make_llm`) and the memory module, leaving every agent's `prompt | llm.with_structured_output(Schema)`
  untouched. The free-tier finding is an external constraint, documented so the live run is reproducible.
- **Rejected alternatives:** loosening Schema field types to accept strings (pollutes the A2A contract);
  per-agent rate limiters (collectively exceed the global TPM); `make setup-full` for the live run
  (vectorbt breaks numpy 2.x).
- **Consequences:** `config` gains `groq_requests_per_second`/`groq_max_retries`. `make check` stays green
  (82 unit + e2e) — offline is unaffected. The full live backtest is gated on a paid Groq tier or a
  multi-day throttled run; the short-window live result is captured in `logs/`.

## ADR-013 · S42 metrics: /C0 drawdown convention, fixed-base returns, matplotlib in dev venv
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** `src/backtest/metrics.py` computes every metric on the **fixed base C0 = initial_capital**,
  net of fees — never a moving equity denominator. Daily return is `r[t] = ΔE / C0`, so Sharpe/Sortino on
  `r[t]` equal the Sharpe of the raw dollar P&L (annualized √252). **Max drawdown uses the non-standard
  `/ INITIAL CAPITAL` convention**: `dd[t] = (E[t] - peak$[t]) / C0`, exposed as the key
  **`max_drawdown_over_c0`** (explicitly labeled) because it reads DEEPER than the conventional `/peak`
  (e.g. -20% where /peak says -18%). `compute_metrics` bundles total_return, sharpe, sortino,
  max_drawdown_over_c0, hit_rate, turnover (mean |Δposition| with a prepended flat so an open counts and a
  flip = 2), avg_holding_period (one-sided run length), plus the same headline trio for buy & hold
  (`C0·P[t]/P[0]`). `plot_equity` draws strategy vs buy & hold from the shared $1M origin with an on-figure
  stats box → `results/equity_curve.png`. **`matplotlib==3.10.7` added to the dev venv** (Agg/headless) so
  the chart is written + tested in `make check`. The metric functions are pure (Series in → number out),
  reused unchanged by the backtest, the S5 ablations, and the S6 notebook. vectorbt is NOT used (its /peak
  drawdown + full-compounding differ from our conventions) — optional toy cross-check only.
- **Reason:** Computing on the fixed $1M base (not moving equity) and the labeled `/C0` drawdown keep the
  scorecard internally consistent with the capped-notional account (ADR-012) and honest about reading
  deeper than `/peak`. Pure functions keep the same scorecard logic shared across milestones.
- **Rejected alternatives:** `/peak` drawdown (standard but understates risk relative to the capped $1M
  base — and inconsistent with the account); returns on moving equity (would double-count the cap);
  vectorbt `Portfolio.stats()` as source of record (different conventions); generating the chart lazily
  outside `make check` (then the PNG path/format would go untested).
- **Consequences:** matplotlib in the dev venv; `results/equity_curve.png` + the enriched `metrics.json`
  (Sharpe/Sortino/MaxDD/hit_rate/turnover/avg_holding + buy&hold trio) are written every backtest. F12
  evidence updated; **M4 (walk-forward backtest) complete**. S5 baselines/ablations and the S6 report
  reuse these metric functions and the chart unchanged.

## ADR-012 · S41 backtester: own dollar loop (capped notional, t+1), offline 2025 fixture slice
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** The `Backtester` owns a **custom dollar P&L loop** (NOT vectorbt's full-compounding
  default): C0 = `config.initial_capital` ($1M), **capped-notional** sizing set once at entry
  (`notional = min(C0, equity)`), `shares = ±notional/P_exec`, mark-to-market `pnl = shares·(P[t]-P[t-1])`,
  and a fee charged **only on a position change** (`(fee_bps/1e4)·|Δnotional|`; a flip crosses zero →
  double fee). Execution is **t+1**: the loop is split into a forward THINK pass (`run_one_day` per
  session, data ≤ t, staging/flushing memory) and a pure `_run_accounting(dates, prices, targets)` pass
  where `targets[k-1]` executes at session k — making the off-by-one invariant and the fee/sizing math
  unit-testable WITHOUT the graph (which returns hold-flat offline and never trades). Added
  `initial_capital`, `position_sizing="capped_notional"`, `results_dir` to config; `results/` gitignored.
  The full per-day **trace** is reused from the S33 commit node: the backtester reads
  `log_dir/{ticker}_{t}.json` and folds it (plus cum-pnl) into `results/trace.json`. **Offline fixtures
  were extended with ~45 business-day 2025 sessions** (appended after the locked 2024 block, starting near
  the 2024 close to keep the calendar-gap return small) so the default 2025-2026 window has offline data
  for `make dev` / `--mode backtest --offline`. Risk metrics (Sharpe/MaxDD/turnover/avg-holding) are a
  minimal stub here; the real metrics module + equity chart are S42 (the run writes a basic metrics.json).
- **Reason:** vectorbt compounds on full equity, silently breaking the capped-notional rule, so we must
  own the loop to honor the cap, the one-session execution lag, and fee-on-change exactly — the
  difference between a trading-realistic result and an inflated one. Splitting think/account keeps the
  anti-lookahead ordering in one auditable place and lets the dollar math be tested deterministically.
  Appending 2025 fixtures (vs shifting the 2024 block) keeps every existing 2024-dated test valid.
- **Rejected alternatives:** vectorbt as the engine of record (full-compounding cap violation; kept only
  as an optional toy cross-check); same-day (t) execution (lookahead); re-sizing notional while held
  (the cap is an entry decision); shifting fixtures to 2025 (breaks the 2024-dated tests).
- **Consequences:** `initial_capital`/`position_sizing`/`results_dir` in config; `results/` artifacts
  feed the Step-6 report. F12 → `passing`. S42 enriches metrics.json + adds the equity chart; S5's
  `full_compounding` sizing + `use_hysteresis` ablations build on this loop.

## ADR-011 · S33 LangGraph orchestration: fixed topology + flag-driven nodes, langgraph in dev venv
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** `build_graph` compiles a **fixed-topology** LangGraph: `observe → [news, macro, technical,
  memory] (parallel fan-out) → debate → conviction → position_manager → commit`. The parallel analysts
  write **distinct** `GraphState` keys so LangGraph's default merge needs no reducer. **Ablation flags
  change what nodes PRODUCE, not the graph shape** (`use_macro=False` → neutral MacroSignal;
  `use_memory=False` → empty MemoryContext; `use_debate=False` → deterministic `_fallback_stance` from
  news+technical aggregation) — one Config toggle over the same graph, never a code fork.
  `langgraph==0.6.10` added to the dev venv (pure-python on langchain-core, no torch). Several
  S33-specific wiring choices: (1) the conviction node passes the **raw score z** (composite +
  self-consistency) to the PositionManager as `conviction`; the Step-5 Layer-3 calibrator (z→P) slots in
  front later. (2) **memory_consistency** = share of retrieved closed analogs with reward>0 (0.5 if
  none); **disagreement** = directional disagreement of the non-flat news/technical votes
  (1=opposed, 0=aligned); **realized_vol** = `obs.indicators['vol20']` (NaN→0). (3) **drawdown is passed
  as 0.0** in S33 — the equity-curve drawdown veto is wired by the backtest (S4). (4) `observe` is a
  fan-out anchor; `run_one_day` performs the single `get_observation` (it also needs obs to stage), seeds
  the graph, mutates `PortfolioState` in place for t+1 (unless `stateless`), then `stage(t)`→`flush_due(t)`.
  `commit` writes a full per-day trace JSON to `config.log_dir/{ticker}_{t}.json` (Step-6 report source).
- **Reason:** Fixed topology + node-level flags keep the ablations as the spec wants (one toggle, same
  graph) and the wiring testable; using `run_one_day` for the single observation avoids fetching it twice
  and threading `t` through `GraphState`. langgraph is light, so it belongs in the test runtime (same
  pattern as langchain-core/faiss, ADR-007/009).
- **Rejected alternatives:** conditional edges / multiple compiled graphs per ablation (a code fork — the
  thing the flag design avoids); computing the calibrated P here (needs 2022-2024 history — Step 5);
  tracking equity/drawdown in the graph (that is the backtest's job — keeps the graph stateless per day).
  `use_hysteresis` ablation behavior is deferred to S5 (flag defined; PositionManager threshold handling
  designed alongside the ablation harness).
- **Consequences:** Dev venv now carries langgraph; a live run still needs `make setup-full`. Ablation
  flags `use_memory/use_macro/use_debate/use_hysteresis/stateless` added to `config.py`. F10 → `passing`;
  **M3 complete** (one day → TradeDecision; PortfolioState across days; point-in-time memory). S4 will
  loop `run_one_day` over 2025-2026 with fees, real drawdown, and t+1 execution.

## ADR-010 · S32 PositionManager: two new veto knobs + flip-blocked-closes-to-flat
- **Date:** 2026-06-19
- **Status:** accepted
- **Decision:** The `PositionManager` is a pure deterministic rule engine (no LLM): **veto first**
  (guard clause short-circuits before any hysteresis branch), then **asymmetric hysteresis** on the
  calibrated conviction. The plan referenced "high macro_risk" and "high disagreement" as veto triggers
  but config had no thresholds for them, so two knobs were added: **`macro_risk_cap = 0.70`** (force
  flat when `MacroSignal.macro_risk` exceeds it — a numeric trigger alongside the categorical
  `regime == risk_off`) and **`disagreement_cap = 0.70`** (force flat when analyst disagreement exceeds
  it; the disagreement metric itself is computed in S33). Two transition cells the plan table left
  implicit are resolved: when shorting is disallowed (`allow_short=False`), (a) **flat + strong short
  signal → stay flat** ("open short blocked"), and (b) **long + tau_flip-strength short signal → close
  to flat** (not hold) — a strong opposite signal means the long is wrong, so exiting is the risk-correct
  move even though we can't reverse. `new_thesis` is the stance's bull_case on a long open/flip, bear_case
  on a short; preserved on hold; cleared on close/veto.
- **Reason:** Keeping every number in config (coding-style) requires explicit caps for the two extra veto
  triggers; 0.70 mirrors the conviction `tau_enter` "strong" bar and is tunable on the 2022-2024 set.
  Closing (not holding) a long under a blocked-flip is the conservative reading of "risk control overrules
  signals" — you should not sit in a position the evidence strongly contradicts just because you can't flip.
- **Rejected alternatives:** hardcoding the macro/disagreement thresholds inline (violates config
  centralization); holding the long when a flip-to-short is blocked (leaves capital in a strongly-opposed
  position); letting the debate's `stance.action` drive the transition (the manager must be the
  deterministic authority keyed on current_position × target × calibrated conviction, so `stance.action`
  is advisory only). The `use_hysteresis` ablation flag is deferred to S5 (YAGNI now).
- **Consequences:** Adds `macro_risk_cap`, `disagreement_cap` to `config.py`. F09 → `passing`. S33 will
  compute `realized_vol`/`drawdown`/`disagreement` and pass the calibrated conviction `z` into `decide`,
  then apply the `TradeDecision` to `PortfolioState` for t+1 execution.

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
