# Data Store Rules

This project has **no database** (YAGNI, spec §12.3). Persistence is files only. This doc covers the
storage conventions that play the role a DB would.

## Stores

| Store | Location | Format | Committed? |
|---|---|---|---|
| AAPL news cache | `data/{ticker}_news.parquet` | Parquet | No (gitignored) |
| Macro news cache | `data/macro_news.parquet` | Parquet | No |
| Price cache | `data/{ticker}_prices.parquet` | Parquet | No |
| LLM response cache | `data/{ticker}_llm_cache.json` | JSON | No |
| FAISS memory index | `faiss_index/` (or `data/`) | FAISS | No |
| Offline fixtures | `fixtures/` | JSON/CSV | **Yes** (small, fixed) |

All paths derive from `config.ticker` — never hardcode `"AAPL"` in a path.

## Caching rules (spec §6, §12.6)

- Download AV data once (free tier: 25 req/day) and cache to Parquet; the backtest reads the cache.
- Cache LLM output keyed by `(ticker, date, agent)` and embeddings by `(ticker, date)` so re-running
  ablations costs no new API calls.
- Cache is a performance layer, not a source of truth — deleting `data/` and re-running must
  reproduce results (given the same upstream data).

## Point-in-time discipline (the critical rule)

- Caches store the **full history**, but no consumer reads them directly — everything goes through
  `get_observation(ticker, t)`, which filters to `≤ t`. A cache hit must never leak a future row.
- The FAISS index is append-only with **delayed writes**: an episode for day `t` enters the index
  only at `t+1+h`; retrieval filters to episodes whose outcome has closed. See
  [`.claude/skills/check-lookahead`](../.claude/skills/check-lookahead/SKILL.md).

## Hygiene

- `data/`, `logs/`, and FAISS files are gitignored — they may contain licensed AV content and are
  reproducible. Never commit them.
- Parquet via `pyarrow`; cast AV's string numerics to `float` at load time (spec §2.1).
