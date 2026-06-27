# Progress

> Living snapshot for session handoff. Update at session end via the `update-progress` skill.
> Use absolute dates. Mirror `features.json` — never list something Completed below `passing`.

_Last updated: 2026-06-26_

## Current State

Milestone **M4 (Walk-forward backtest) COMPLETE** — M3 done; **S41 (backtester + dollar accounting) and
S42 (metrics + equity chart) done**. `src/backtest/run_backtest.py` owns a custom dollar P&L loop (C0=$1M,
**capped-notional** sizing, **t+1 execution**, fee on change with flip=double, mark-to-market vs buy&hold).
`src/backtest/metrics.py` computes total_return/sharpe/sortino/**max_drawdown (/C0 convention)**/hit_rate/
turnover/avg_holding_period on the fixed $1M base net of fees + the buy&hold trio, and `plot_equity` writes
`results/equity_curve.png` (strategy vs buy&hold from $1M, on-chart stats box). A backtest writes
`results/{equity_curve.csv,trace.json,decisions_log.csv,metrics.json,equity_curve.png}`. `matplotlib`
added to dev venv. `tests/test_backtest.py` + `tests/test_metrics.py` green; `make check` green (82 unit +
e2e). **F12 passing — M4 acceptance met (equity curve + metrics, PnL net of fees).** **Next: M5 / Step 5**
— calibration (conviction Layer 3), baselines (buy&hold / single-agent / AV-sentiment), and the ablation
suite. Live run needs `make setup-full`.

**Update (2026-06-23):** a short-fix + threshold re-tuning pass landed between M4 and M5 (see the
2026-06-23 entry below + ADR-016/017/018). The first live run never shorted and was flat 65% of the time;
the system now *can* short (Gate A debate-prompt + Gate B abstention-aware conviction) and the
hysteresis/veto priors are re-tuned (`tau_enter 0.60`, `tau_flip 0.70`, `vol_cap 0.50`). These are PRIORS —
they (and the calibrator) must be **validated and frozen on the 2022-2024 warm-up in S51** before the next
test run; conviction is still **raw z** until then.

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
- M3 · **S32 (PositionManager)**: `src/agents/position_manager.py` — deterministic veto-first +
  asymmetric hysteresis → `TradeDecision`; added `macro_risk_cap`/`disagreement_cap`; ADR-010.
  `tests/test_position_manager.py` (full transition table + veto) 16 passed. **F09 passing.**
- M3 · **S33 (LangGraph orchestration)**: `src/graph/build_graph.py` (`build_graph` + `run_one_day`) —
  parallel analysts → debate → conviction(z) → PositionManager → commit; per-day trace JSON;
  stage/flush memory rhythm; ablation flags added to config; `langgraph` in dev venv; ADR-011.
  `tests/test_graph.py` 5 passed. **F10 passing. M3 complete.**
- M4 · **S41 (backtester + dollar accounting)**: `src/backtest/run_backtest.py` (`Backtester`,
  `run_backtest`) — capped-notional, t+1 execution, fee-on-change (flip=double), equity vs buy&hold;
  `results/` artifacts; offline 2025 fixture slice; `initial_capital`/`position_sizing`/`results_dir`
  in config; ADR-012. `tests/test_backtest.py` 6 passed. **F12 passing.**
- M4 · **S42 (metrics + equity chart)**: `src/backtest/metrics.py` — fixed-$1M-base returns, Sharpe/
  Sortino/**MaxDD (/C0)**/hit_rate/turnover/avg_holding + buy&hold trio; `plot_equity` → equity_curve.png;
  `matplotlib` in dev venv; ADR-013. `tests/test_metrics.py` 12 passed. **F12 passing. M4 complete.**

- **Live-run hardening (ADR-014)**: first real online run surfaced + fixed 3 issues — Groq json_mode
  string-coercion (`_StructuredGroq` in `src/llm.py`), faiss+torch OpenMP crash (`KMP_DUPLICATE_LIB_OK`
  in `store.py`), and rate-limit resilience (shared `InMemoryRateLimiter` + `max_retries`,
  `groq_requests_per_second`/`groq_max_retries` knobs). Fixed bad `langchain-groq` pin (0.3.10→0.3.8),
  dropped `langchain-openai`. Verified live: 5 real Jan-2025 sessions (open@0.88 conviction, thesis-close,
  macro risk_off VETO; strategy +0.58% vs buy&hold -0.47%, net of fees). **Full 2025-2026 live run is
  blocked by the Groq FREE tier (12k TPM + 100k tokens/day → full run ≈ 4.6M tokens ≈ 46 days of quota);
  it needs a paid Groq Dev tier.** Offline `make check` stays green (82 unit + e2e).

- **FIRST FULL LIVE BACKTEST (2026-06-20)** — 366 sessions (2025-01-02→2026-06-18), live Llama 3.3 70B
  via Groq/OpenRouter (DeepInfra→Groq re-pin for speed), ~50 min, 0 crashes, resilient wrapper held.
  **Result ($1M base, net of fees): strategy +9.1% (Sharpe 0.47, MaxDD −10.7%, 80 trades, $59.7k fees,
  avg hold 3.2d, 128 long / 238 flat / 0 short) vs buy&hold +23.0% (Sharpe 0.57, MaxDD −30.7%).** Honest
  read: defensive — sidestepped the H1-2025 −29% AAPL drawdown (cut MaxDD ~2/3) but underperformed
  absolute return in a bull market; heavy churn/fees. Artifacts in `results/` (gitignored). NOTE:
  conviction is still **raw z (uncalibrated)** — S51 (isotonic calibration) + threshold tuning are the
  next levers to improve entries and cut turnover.

- **SHORT-FIX + THRESHOLD RE-TUNING (2026-06-23)** — diagnosed why the first live run underperformed +
  **never shorted** (flat 65%: 152 days blocked by the entry bar, 86 by the veto; 0 shorts despite
  `allow_short=True`). Two stacked causes, both fixed:
  - **Gate A (ADR-016):** the debate prompt lumped the bear case as "short/flat", so a bearish view
    collapsed to flat. `DEBATE_SYSTEM` now makes Step 1/2 directional (RISE→LONG / FALL→SHORT) and Step 4
    maps a dominant bear case to `target_direction=-1` ("SHORT and FLAT are different decisions").
  - **Gate B (ADR-017):** `composite_conviction` agreement is now **abstention-aware**
    (`|Σsᵢcᵢ| / Σ_{sᵢ≠0}cᵢ`) — a flat agent no longer dilutes a confident lone short below `tau_enter`.
    +unit test (news-flat + tech-short → agreement 1.0, z≥tau_enter). `make check` green (84 unit + e2e).
  - **Threshold priors re-tuned (ADR-018):** `tau_enter 0.70→0.60`, `tau_flip 0.80→0.70`, `vol_cap
    0.40→0.50` (kept `tau_exit 0.40`, `macro_risk_cap`/`disagreement_cap 0.70`); PositionManager tests made
    config-relative.
  - **Docs reconciled:** PLAN.md (Gate-B formula, debate prompt, Step-5 "first-live-run fixes" subsection)
    and substeps **S23/S32/S53/S51** updated to describe the fixed design + the freeze-on-warmup discipline.
  - **CAVEATS:** short behavior is **live-only** (MockLLM ignores prompt text — no offline proof yet); the
    re-tuned values are **PRIORS to validate+freeze on the 2022-2024 warm-up** (S51), not test-fitted.

- M5 · **S51 (warm-up & conviction calibration) — DONE (2026-06-23, ADR-019). F15 → passing.**
  `src/eval/calibration.py` Layer 3: `Calibrator` (sklearn isotonic primary, Platt fallback below
  `calibration_min_isotonic=200`), `fit_calibrator`, `reliability_diagram` (+`_reliability_stats` → Brier &
  ECE over `calibration_bins`), `_hit_label` (= `MemoryStore._reward > 0`, provably identical to the memory
  reward), `WarmupPair`/`collect_warmup_pairs`/`run_warmup_calibration`. `--mode warmup` fits + freezes
  `results/{calibrator.pkl, reliability_diagram.png, calibration_report.json, warmup_pairs.csv}` over real
  2022-2024 (no PnL). `build_graph(..., calibrator=_AUTOLOAD)` applies the frozen z→P(correct) in the
  conviction node when present (raw z offline/before warm-up — hermetic; warm-up uses `calibrator=None`).
  `tests/test_calibration.py` 11 passed (isotonic monotonicity; mis-scaled z bent toward diagonal w/ Brier+
  ECE improving; hit-label sign; identity fallback; PNG). `make check` green (89 unit + e2e);
  check-lookahead clean. (FAISS disk persistence, deferred here as ADR-019, was **resolved by A2/ADR-023**
  below — warm-up memory now carries into the test.)

- **LLM CACHE built (2026-06-25, ADR-020).** The spec/plan assumed "reruns are free, cached by
  (ticker,date,agent)" but it was **never implemented** (`llm_cache_path()` referenced nowhere → every live
  run paid full price). Now `make_llm` wraps the online backbone (OpenRouter + Groq) in `_CachingLLM`
  (`config.use_llm_cache`, default True; offline/MockLLM untouched). **Key = sha256(rendered prompt +
  schema + temperature)** → automatically per-agent, point-in-time, and **prompt-versioned** (the Gate-A
  debate-prompt change MISSES instead of replaying stale output). Ordered list per key replays the K
  debate samples faithfully; append-only JSONL at `data/{ticker}_llm_cache.jsonl` (gitignored). `make check`
  green (94 unit + e2e, +5 cache tests: cold→warm replay, K-sample order, prompt-change miss, temperature
  separation, opt-out). **Effect:** first warm-up (~$1.20) + first backtest (~$0.60) populate their windows
  once; every ablation / h-sweep / re-run on those windows is then ~free and ~instant. (The existing
  `logs/` traces couldn't be reused as a cache — they lack the input prompt, are date-keyed for one config,
  and were stale; the cache productionizes the idea with proper keying.)

- M5 · **S52 (baselines) — DONE (2026-06-25, ADR-021). F13 → passing.** `src/eval/baselines.py`:
  buy&hold (always long), `av_sentiment` (sign of per-day AV `ticker_sentiment_score` — the
  **baseline-to-beat**, never the system's signal), and `single_agent` (NewsAgent signal only, driven
  directly — no `use_technical` flag exists, so the graph couldn't give news-only). All three pushed
  through the SAME `Backtester._run_accounting` dollar loop + `compute_metrics` ($1M base, t+1, fee-on-
  change) → `results/curves/baseline_*.csv`, plus a `corr(LLM_sentiment, AV_score)` diagnostic.
  `tests/test_eval.py` 5 passed (module-scoped fixture runs the suite once → ~67s). `make check` green
  (99 unit + e2e); check-lookahead clean. Metric rows fold into the S5.3 comparison table.

- M5 · **S53 (ablations) — DONE (2026-06-25, ADR-022). F14 → passing.** `src/eval/ablation.py`:
  `ABLATION_VARIANTS` (full / stateless / no_memory / no_macro / no_debate / no_hysteresis) each a
  `dataclasses.replace` config toggle over the SAME engine; `run_ablations` stacks the 6 variant rows + the
  3 S52 baselines into `results/ablation_table.{csv,md}` + per-variant curves. Wired **`use_hysteresis`**
  into the PositionManager (collapse `tau_exit:=tau_enter`; resolves the ADR-010/011 deferral) and added
  **`Backtester.run(write=False)`** so variants reuse the loop without clobbering `results/`. Manual MD
  table (no `tabulate` dep). `tests/test_eval.py -k ablation` 3 passed + unit tests (short ~6-session window
  → ~11s). `make check` green (105 unit + e2e); check-lookahead clean. **STRETCH DEFERRED:** risk_off
  persistence/size-down, `min_holding_days`, short-expectancy (don't block F14).

- M3/M5 · **A2 — FAISS memory persistence — DONE (2026-06-25, ADR-023).** `MemoryStore.save()/load()`
  (`faiss.write_index` + pickle of `{closed, pending}` Episodes → `data/{ticker}_memory/`, gitignored).
  `collect_warmup_pairs` saves the warmed memory; `Backtester.run` warm-starts via `store.load()` **online
  only** (offline stays cold/hermetic). Resolves the ADR-019 deferral → the warm-up's "warm the memory" job
  is now real (running `--mode warmup` then `--mode backtest` carries the 2022-2024 FAISS index into the
  test). Delayed-write intact (save/load never reset `outcome_closed_t`; retrieve still filters ≤ obs.t).
  `tests/test_memory.py` +2 (round-trip + noop-when-absent); `make check` green (107 unit + e2e);
  check-lookahead clean.

- **Fee → COMMISSION-ONLY (2026-06-25, ADR-024).** `config.fee_bps 7.5 → 1.0` bp/change: the strategy
  backtest charges only the unavoidable ~1bp commission; bid-ask spread + slippage are execution/impact
  effects (separately modeled, a future S62 sensitivity axis), not charged to the signal. Mechanism
  unchanged (on-change, flip=double). `make check` green (the fee test is a rate-independent ratio). Implies
  the prior "fees ate 40% of gross" was mostly a spread/slippage assumption; turnover still worth cutting
  but its *commission* cost is small (~$8k vs $59.7k on the same 80 trades).

- **LIVE WARM-UP CALIBRATION COMPLETE (2026-06-25).** `--mode warmup` ran the full 2022-2024 pipeline live
  (OpenRouter Llama 3.3 70B) → frozen `results/calibrator.pkl` + reliability diagram + `warmup_pairs.csv` +
  warmed `data/AAPL_memory/` (index.faiss + episodes.pkl). **Shorts fire live** (warm-up executed 420 long /
  316 flat / 17 short — Gate A/B work on the real LLM). **Hit-label fixed to `target_direction` (ADR-025)**
  after the first calibration came out degenerate (flat days polluted it): re-run ($0, cached) gave a clean
  MONOTONIC calibration on 617 view-day pairs — hit-rate 46.7% base → 55.6% @0.50 → 66.7% @0.55-0.64 →
  72.7% @0.65+; calibrated range 0.42-0.73; Brier 0.327→0.245. Key finding: raw LLM directional calls have
  ~no edge (46.7%), but the computed conviction sorts them (§7.3 works). `tau_enter=0.60` now validated (39
  view-days @66.7%). **PENDING DECISION before the test run:** freeze `tau_enter` 0.50 vs 0.60; `tau_exit
  0.40` is below the 0.42 calibrated floor → conviction-decay exits never fire (thesis-only exits).

- M6 · **S61 (interactive explainability web report) — DONE (2026-06-26, ADR-026). F18 → passing.**
  `src/eval/report.py::build_report_html(equity_csv, trace_json, out_path)` reads `results/equity_curve.csv`
  + `results/trace.json` ONLY (never recomputes) → ONE self-contained `results/report.html`: a Plotly (CDN)
  cumulative-PnL chart (strategy vs buy & hold) with clickable daily points + the full per-day trace
  embedded inline; a `plotly_click` handler paints the clicked day's news read · each analyst
  signal+rationale · bull/bear/thesis · conviction · final call+reason into a side panel. No server, no
  `fetch`, stdlib + pandas only, no new `requirements.txt` entry. Token `str.replace` template (not
  `.format`) to keep the JS/CSS braces literal; figure builder prefers `cum_pnl_*` cols, falls back to
  `equity_*`. The committed sample was built from the **headline `tau05online`** run
  (`equity_curve_tau05online.csv` + `trace_tau05online.json`, 1.5MB, opens off disk). `tests/test_report.py`
  4 passed; ruff + mypy clean on the new files; full suite 112 passed. **Caveat:** repo-wide `make check` is
  red ONLY on a pre-existing unrelated lint line (`config.py:56` >120 chars, user-owned), not on S61 code.

- **USER DECISIONS (2026-06-26):** (1) the **blog/headline result is the `tau05online` live run**
  (`tau_enter=0.50`, the `equity_curve_tau05online_thru01May2026` framing: +21.3% / Sharpe 1.16 / MaxDD
  −14.0% vs buy&hold +15.5% / 0.42 / −30.7% over 2025-01-02..2026-05-01); (2) the **ablation suite will not
  be re-run** (too costly) — S53/F14 code stays in the repo but `--mode ablation` is not re-run, and final
  reporting (S63 notebook/README) leads with the headline result, not an ablation table.

## In Progress

- M6 · **Offline build remaining (Phase A):** S62 robustness sweep (F16), S63 notebook/README/DoD; + A1
  short fixture; + the S5.3 stretch experiments (risk_off persistence/size-down, `min_holding_days`,
  short-expectancy — don't block F14). S51/S52/S53/S61/A2 + the LLM cache are DONE offline.
  **Note (per user decision):** the live ablation suite is NOT to be re-run.
- **Still open (live, deferred to the end):** run the LIVE `--mode warmup` once → fit calibrator + warm the
  (now-persisted, A2) FAISS memory; **validate + freeze the threshold priors** (ADR-018) on that warm-up;
  then `--mode backtest` (warm-starts memory + applies the frozen calibrator); re-measure the **Gate-B
  short-frequency lift** once `z` is calibrated.
- **OpenRouter backbone added (ADR-015)** — Groq Dev tier unavailable + free tier can't finish the run,
  so `make_llm` gained a `provider="openrouter"` branch (ChatOpenAI → OpenRouter, SAME Llama 3.3 70B /
  Dec-2023 cutoff). Generalized `_StructuredJSON` wrapper used by both backbones; added
  `ResearchStance.target_direction` str→int coercion; `config.provider` default = `"openrouter"` (Groq
  kept for one-line switch-back). Verified live: 1-day OpenRouter smoke opened long @ 0.86 conviction.
  `make check` green (83 unit + e2e). **The full 2025-2026 live backtest is now runnable (~$0.60); just
  run `python -m src.main --mode backtest`.** For reproducibility, set `config.openrouter_provider`.

## Blocked

- _none._ (The earlier OpenRouter key-limit block was resolved with a fresh key; the live warm-up completed
  2026-06-25 — see below. LLM cache fully warmed: 7,523 calls over all 753 days, so all future
  warm-up/calibration/threshold iterations are $0.)

## Known Issues

- **Config-threading inconsistency (data layer reads the GLOBAL `config` singleton) — found 2026-06-25.**
  `src/data/loaders.py` does `from config import config` (the singleton) and reads `config.offline`,
  `config.fixtures_dir`, `config.relevance_cutoff`, etc. from it — so passing a LOCAL `Config(offline=True)`
  to a caller does NOT make the data layer offline (only `make_llm`/`build_graph`/`Backtester`, which take
  the config as a param, honor it). Effects: (1) unit tests that pass `Config(offline=True)` (baselines,
  ablations, backtest) silently read the REAL `data/*.parquet` on a machine where it exists (so the S52
  baselines test runs ~360 real sessions, not the 45-row fixture — hence its slowness); (2) on a fresh clone
  with no `data/`, those offline unit tests would hit the yfinance NETWORK via `read_or_fetch` → `make check`
  is only truly hermetic through the e2e subprocess (which goes via `main.py`, the one place that sets the
  global `config.offline`). **Does NOT affect live runs** (`python -m src.main` mutates the one global
  singleton, so all layers agree). **Fix (follow-up, moderate):** thread `config` through the data layer —
  `get_observation(config, ticker, t)` / `load_prices(config, ticker, t)` — instead of the global; would
  also make `make check` genuinely hermetic + faster. Pre-existing (S11 design), not a calibration blocker.
- Heavy runtime stack (langchain, faiss, vectorbt, ta, sentence-transformers) is NOT installed by
  `make setup`; use `make setup-full`. Needed from M2 onward. (vectorbt + numpy 2.x compatibility
  to be confirmed at first `make setup-full` — see DECISIONS.)
- `requirements.txt` pins are first-pass; may need adjustment at first `make setup-full`.

## Next Steps (M5 · Step 5 — S52/S53 in PLAN.md)

1. **LIVE `--mode warmup`** over real 2022-2024 → fit + freeze the calibrator (S51 code is ready); confirm
   the reliability diagram bends toward the diagonal. **Validate + freeze the threshold priors** (ADR-018:
   `tau_enter 0.60`, `tau_flip 0.70`, `vol_cap 0.50`) on this warm-up — **never on the test curve**.
2. ~~**S52 — baselines** → F13~~ ✅ DONE (2026-06-25, ADR-021).
3. ~~**S53 — ablations** (the 5 config-toggle variants) → F14~~ ✅ DONE (2026-06-25, ADR-022). Stretch
   experiments (risk_off persistence/size-down, turnover control, shorts on/off + short-expectancy) deferred.
4. **Verify the short fix:** a live 1-day smoke (bearish-consensus day → `target_direction=-1`) and a
   `target_direction:-1` fixture so the offline backtest can exercise a short end-to-end.
5. ~~warm-up FAISS persistence~~ ✅ DONE (A2, ADR-023) — warm-up memory now carries into the test.
6. **Offline still to build:** S61 web report (F18), S62 robustness sweep (F16), S63 notebook/README/DoD;
   + A1 short fixture; + the S5.3 stretch experiments.
7. Re-run the full 2025-2026 backtest **once** with calibrated `z` + frozen thresholds + warm memory; report
   short-trade contribution vs the +9.1% / buy&hold +23% baseline.
