"""Central configuration — the SINGLE place numbers live (spec §13.3).

No magic numbers anywhere else in the codebase. Defaults below are sensible
starting values from domain knowledge; the calibration-set tuning (2022-2024)
overwrites the ones marked "tuned".

`ticker` is a parameter, never hardcoded elsewhere (spec §12.5). Setting
`ticker = "AMZN"` and re-running must work with no other line changed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # ── Asset / dates (single source of truth) ──────────────────────────────
    ticker: str = "AAPL"
    benchmark: str = "SPY"
    warmup_start: str = "2022-01-01"
    warmup_end: str = "2024-12-31"
    test_start: str = "2025-01-01"
    test_end: str = "2026-06-30"

    # ── Data filtering / limiting ───────────────────────────────────────────
    relevance_cutoff: float = 0.3          # drop AAPL news below this relevance
    max_news_per_day: int = 10
    no_news_confidence: float = 0.5        # NewsAgent flat default on a no-news day (rubric "no edge")
    macro_topics: tuple[str, ...] = (
        "economy_monetary",
        "economy_macro",
        "financial_markets",
    )

    # ── Technical indicators (windows; computed deterministically on rows <= t) ─
    rsi_period: int = 14
    ma_short: int = 20                     # MA20 (also SPY-trend reference)
    ma_long: int = 50                      # MA50
    vol_window: int = 20                   # 20d realized vol (annualized)
    mom_window: int = 10                   # momentum lookback (sessions)

    # ── Memory ──────────────────────────────────────────────────────────────
    h: int = 5                             # forward-return / delayed-write window
    k: int = 5                             # top-k episodes retrieved
    embedding_model: str = "all-MiniLM-L6-v2"
    reward_benchmark: str = "aapl_drift"   # reward = sign(action)·(fwd − benchmark); "raw" | "aapl_drift"
    reward_drift_window: int = 60          # trailing sessions for μ (AAPL drift), point-in-time ≤ t

    # ── Hysteresis thresholds (on CALIBRATED conviction; tuned §7.2) ─────────
    tau_enter: float = 0.70
    tau_exit: float = 0.40
    tau_flip: float = 0.80

    # ── Risk veto ───────────────────────────────────────────────────────────
    vol_cap: float = 0.40                  # annualized realized-vol cap
    dd_cap: float = -0.15                  # max drawdown floor
    macro_risk_cap: float = 0.70           # force flat above this systematic-risk level
    disagreement_cap: float = 0.70         # force flat when analysts disagree above this

    # ── Conviction (spec §7.3) ──────────────────────────────────────────────
    K: int = 5                             # self-consistency samples
    w1: float = 0.4                        # weight: agent agreement
    w2: float = 0.3                        # weight: mean confidence
    w3: float = 0.3                        # weight: memory consistency
    alpha: float = 0.5                     # blend: conviction_raw
    beta: float = 0.5                      # blend: conviction_sc

    # ── Backtest ────────────────────────────────────────────────────────────
    fee_bps: float = 7.5                   # cost per position CHANGE
    allow_short: bool = True
    initial_capital: float = 1_000_000.0   # C0 — the brokerage account opened on day 1
    position_sizing: str = "capped_notional"  # "capped_notional" | "full_compounding" (S5 ablation)
    results_dir: str = "results"           # equity_curve.csv / trace.json / metrics.json land here

    # ── LLM (pinned for reproducibility) ────────────────────────────────────
    provider: str = "openrouter"           # "openrouter" | "groq" — single-line backbone swap (§12.2)
    model_id: str = "llama-3.3-70b-versatile"            # Groq model id (Llama 3.3 70B, Dec-2023 cutoff)
    temperature: float = 0.0               # decision agents; debate uses >0 for §7.3
    debate_temperature: float = 0.7        # DebateAgent self-consistency sampling (§7.3, Layer 2)
    groq_requests_per_second: float = 0.1  # client-side throttle to respect Groq free-tier TPM
    groq_max_retries: int = 6              # retry 429 / transient errors with backoff
    # OpenRouter (pay-as-you-go; SAME Llama 3.3 70B → Dec-2023 cutoff preserved, anti-lookahead intact)
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_provider: str = "Groq"  # pin ONE backend (fast: ~1s/call, json mode); "" = auto-route
    openrouter_requests_per_second: float = 3.0  # paid → fast; lower if you hit limits
    openrouter_max_retries: int = 6
    llm_parse_retries: int = 4             # re-ask (with a nudge) when a reply isn't valid schema JSON

    # ── Ablations (Step 5 — one Config toggle over the SAME graph) ───────────
    use_memory: bool = True                # False → MemoryAgent returns empty context
    use_macro: bool = True                 # False → MacroAgent bypassed (neutral regime)
    use_debate: bool = True                # False → stance from deterministic signal aggregation
    use_hysteresis: bool = True            # wired in S5 (no-hysteresis ablation)
    stateless: bool = False                # True → ignore PortfolioState (daily-classifier baseline)

    # ── Runtime ─────────────────────────────────────────────────────────────
    offline: bool = False                  # True → MockLLM + fixtures, no network
    seed: int = 42
    cache_dir: str = "data"
    fixtures_dir: str = "fixtures"
    log_dir: str = "logs"

    # ── Secrets (from .env, never committed) ────────────────────────────────
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    av_api_key: str = field(default_factory=lambda: os.getenv("ALPHAVANTAGE_API_KEY", ""))
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))

    def news_cache_path(self) -> str:
        return os.path.join(self.cache_dir, f"{self.ticker}_news.parquet")

    def macro_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "macro_news.parquet")

    def price_cache_path(self) -> str:
        return os.path.join(self.cache_dir, f"{self.ticker}_prices.parquet")

    def llm_cache_path(self) -> str:
        return os.path.join(self.cache_dir, f"{self.ticker}_llm_cache.json")


# Importable singleton; callers may also build their own Config for ablations.
config = Config()
