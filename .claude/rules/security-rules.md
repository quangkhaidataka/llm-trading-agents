# Rule: Security & Research Integrity

This is a research/backtest project; "security" here is mostly **secrets hygiene** and
**lookahead/leakage integrity** (a leak is a correctness *and* credibility failure).

## Secrets

- API keys (`GROQ_API_KEY`, `ALPHAVANTAGE_API_KEY`) come from `.env` via `python-dotenv`, read once
  in `config.py`. Never hardcode a key, never log one, never put one in a fixture or commit.
- `.env` is gitignored; `.env.example` (empty values) is committed. Verify `.gitignore` covers
  `.env` before any commit.
- Cached data (`data/*.parquet`, `*.json`) and `logs/` are gitignored — they may contain licensed AV
  content; do not commit them.

## No look-ahead / no leakage (spec §12.1) — treat as a security boundary

- Day `t` may see only: news `time_published ≤ t`, prices/indicators over the window `≤ t`, SPY/macro
  `≤ t`, and memory episodes whose outcome has closed (`t+1+h ≤ t`).
- Execute at `t+1`, never `t`. Indicators must not use `shift(-1)` or any future-touching rolling op.
- Memory writes are **delayed** to `t+1+h`; writing earlier is a leak.
- Never report warm-up (2022–2024) PnL — report only the 2025–2026 out-of-sample window.
- The pinned backbone's Dec-2023 cutoff is part of the anti-lookahead claim; do not silently swap to
  a model with a later cutoff for the test period without updating the README commitment.

## Data provenance

- AV `ticker_sentiment_score` is a baseline/cross-check only, never the primary signal — using it as
  the signal launders AV's alpha as ours.
- `relevance_score` filters the AAPL channel only; the macro channel is never relevance-filtered.

## External tools & live data (incl. MCP) — a leakage boundary

- Pipeline code (`src/`) and tests get data **only** through `get_observation`. They must never call
  a live external source: no ad-hoc `requests`, no third-party SDK, and **no MCP tools** (e.g. the
  FMP `quote`/`news`/`statements`, Gmail, Drive tools that may be loaded in the session).
- Live data is *today's* data. Injecting it into a backtest day is catastrophic look-ahead leakage,
  destroys offline/deterministic runs, and bypasses the point-in-time gate and the pinned, cached
  data sources. See [`llm-and-prompts.md`](llm-and-prompts.md) and the `check-lookahead` skill.
- MCP/live tools are acceptable for your own exploration in chat (sanity-checking a figure) — never
  wired into `src/` or used to populate `data/`/`fixtures/` for a backtest.

## Dependencies

- Pin versions in `requirements.txt` / `requirements-dev.txt`. Prefer the chosen stack; justify any
  new heavy dependency in `DECISIONS.md`.
