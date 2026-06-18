---
name: check-lookahead
description: Audit code or a diff for look-ahead bias / data leakage — the #1 correctness-and-credibility risk in this backtest. Use before merging any data, agent, memory, or backtest change, or when a result looks too good. Trigger keywords - lookahead, look-ahead, leakage, point-in-time, future data, t+1, delayed write, anti-leak.
---

# Check Look-Ahead

Anti-lookahead is priority #1 (spec §12.1). A leak is both a correctness bug and a credibility
failure for the whole project. Audit against this checklist.

## Data leakage

- All data comes through `get_observation(ticker, t)` — no module reads a full dataframe or hits an
  API directly.
- For every `t`, no returned field has a timestamp `> t`: news `time_published ≤ t`, prices/indicators
  over window `≤ t`, SPY/macro `≤ t`.
- Indicators use no `shift(-1)` and no rolling/`expanding` op that includes future rows.

## Execution leakage

- The day-`t` signal is applied to the **return of session `t+1`**, never `t`.

## Memory leakage (spec §7.1)

- An episode for day `t` is written to FAISS only at `t+1+h` (delayed write).
- Retrieval returns only closed episodes (`outcome_closed_t ≤ current_t`).
- Reward is the **abnormal** forward return (`sign(action) × (fwd − benchmark)`), not raw.

## Phase / pretraining leakage (spec §3)

- Warm-up (2022–2024) PnL is never reported — only the 2025–2026 window.
- The backbone is pinned with a Dec-2023 cutoff; the test window stays after it.

## Channel hygiene

- The macro channel is **never** relevance-filtered (that filter is AAPL-only) — else Fed/geopolitical
  news is silently dropped.
- AV `ticker_sentiment_score` is baseline/cross-check only, never the primary signal.

## How to run the audit

1. `pytest tests/test_no_lookahead.py` must be green.
2. Grep the diff for red flags: `shift(-1)`, direct `read_parquet`/`requests` outside `loaders.py`,
   any `mcp__`/live-SDK call inside `src/` (live data = future data — see security-rules), hardcoded
   dates, memory `.add(`/`.write(` not gated by `t+1+h`.
3. Report each finding as blocker/major/minor with file:line and a fix. If anything is unclear,
   default to "leak" and require proof it is not.
