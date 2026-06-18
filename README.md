# Multi-Agent LLM Trading System for AAPL

A multi-agent system that reads news + charts and makes daily **position-management**
decisions for AAPL (hold / open / close / flip → target ∈ {−1, 0, 1}). The original
contribution is the **Agent-to-Agent (A2A) communication protocol** and the
**non-parametric memory mechanism** — *not* training an LLM. The LLM is frozen;
"learning" happens in an external FAISS episode bank.

See [`project_description.md`](project_description.md) for the full spec and
[`CLAUDE.md`](CLAUDE.md) for the architecture summary and binding constraints.

## Anti-lookahead commitment

The entire test period (**2025–2026**) is after the backbone's **Dec-2023 knowledge
cutoff**, eliminating pretraining lookahead. The model version is pinned
(`config.model_id`). Day `t` sees only news with `time_published ≤ t` and memory
episodes whose outcome has closed (`t+1+h ≤ t`). Execution is at `t+1`. Warm-up
(2022–2024) PnL is **never reported** — it only populates memory + calibrates.

## Setup

```bash
cp .env.example .env                  # then fill in GROQ_API_KEY, ALPHAVANTAGE_API_KEY
pip install -r requirements.txt
```

## Run

```bash
python -m src.main --mode download    # download + cache data once (Parquet)
python -m src.main --mode backtest    # run the 2025–2026 backtest → equity curve
python -m src.main --mode ablation    # baselines + ablations + calibration
pytest tests/                         # no-lookahead invariant
```

Offline mode (no keys / network / cost, deterministic on fixtures):

```bash
python -m src.main --mode backtest --offline
```

## Status

Scaffold only (milestone **M0**). Each module raises `NotImplementedError` with the
milestone where it gets implemented (M1 data → M5 eval). See the milestone roadmap in
`CLAUDE.md` / `project_description.md` §13.2.

## Limitations

Single asset (AAPL); news is `title + summary` only; `relevance_score` is AV's
proprietary model; ~18-month test = one market regime (read Sharpe with caution);
1 debate round.
