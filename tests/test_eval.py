"""S5.2 tests — baselines run through the SAME Step-4 dollar loop, offline & deterministic.

No network, no real LLM: buy & hold and AV-sentiment use only the price/news caches; single-agent
uses MockLLM. Each baseline emits one full metrics row on the fixed $1M base. The full suite is run
ONCE (module-scoped fixture) since each baseline loops `get_observation` over the test window.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from config import Config
from src.eval.ablation import (
    ABLATION_VARIANTS,
    _write_table,
    make_variant_config,
    run_ablations,
)
from src.eval.baselines import (
    _position_from_sentiment,
    run_baselines,
)

_METRIC_KEYS = {
    "total_return", "sharpe", "sortino", "max_drawdown_over_c0",
    "hit_rate", "turnover", "avg_holding_period",
}


@pytest.fixture(scope="module")
def baselines(tmp_path_factory) -> tuple[Config, dict]:
    """Run all three baselines ONCE over the offline test window; reused by every assertion."""
    cfg = Config(offline=True)
    cfg.results_dir = str(tmp_path_factory.mktemp("results"))
    return cfg, run_baselines(cfg)


@pytest.mark.parametrize("name", ["buy_hold", "av_sentiment", "single_agent"])
def test_baseline_emits_full_metrics_on_shared_loop(baselines, name: str) -> None:
    """Each baseline runs through the shared dollar loop and emits the full metric set on the $1M
    base; t+1 execution → session 0 is flat at exactly C0."""
    cfg, out = baselines
    result = out[name]
    assert set(result["metrics"]) >= _METRIC_KEYS
    curve = result["curve"]
    assert list(curve.columns) == ["date", "equity", "position"]
    assert len(curve) > 0
    assert curve["equity"].iloc[0] == pytest.approx(cfg.initial_capital)


def test_run_baselines_emits_three_curves_and_corr(baselines) -> None:
    cfg, out = baselines
    assert set(out) >= {"buy_hold", "av_sentiment", "single_agent", "corr_llm_sentiment_vs_av"}
    assert -1.0 <= out["corr_llm_sentiment_vs_av"] <= 1.0  # diagnostic: NewsAgent ≠ echo of AV
    for fname in ("baseline_buyhold", "baseline_avsentiment", "baseline_newsonly"):
        assert os.path.exists(os.path.join(cfg.results_dir, "curves", f"{fname}.csv"))


def test_position_from_sentiment_sign_mapping() -> None:
    cfg = Config(offline=True)
    assert _position_from_sentiment(0.3, cfg) == 1
    assert _position_from_sentiment(-0.3, cfg) == -1   # allow_short True by default
    assert _position_from_sentiment(0.0, cfg) == 0
    assert _position_from_sentiment(-0.3, Config(offline=True, allow_short=False)) == 0  # short blocked


# ── S5.3 ablations ────────────────────────────────────────────────────────────
def test_ablation_variants_cover_the_five() -> None:
    """The five named ablations + the full system, each a config-toggle (never a code fork)."""
    assert set(ABLATION_VARIANTS) == {
        "full", "stateless", "no_memory", "no_macro", "no_debate", "no_hysteresis",
    }
    assert ABLATION_VARIANTS["full"] == {}  # the reference variant changes nothing


def test_make_variant_config_toggles_only_named_flags() -> None:
    base = Config(offline=True)
    v = make_variant_config(base, {"use_memory": False, "use_macro": False})
    assert v.use_memory is False and v.use_macro is False
    assert v.use_debate is True and v.ticker == base.ticker  # everything else untouched
    assert base.use_memory is True  # base is not mutated (dataclasses.replace copies)


def test_write_table_emits_csv_and_md(tmp_path) -> None:
    rows = [
        {"variant": "full", "total_return": 0.09, "sharpe": 0.47, "n_trades": 80},
        {"variant": "av_sentiment", "total_return": 0.05, "sharpe": 0.30, "n_trades": 120},
    ]
    csv_path, md_path = str(tmp_path / "t.csv"), str(tmp_path / "t.md")
    _write_table(rows, csv_path, md_path)
    assert os.path.exists(csv_path) and os.path.exists(md_path)
    md = open(md_path).read()
    assert "variant" in md and "| full |" in md and "| av_sentiment |" in md


@pytest.fixture(scope="module")
def ablation_run(tmp_path_factory) -> tuple[Config, dict]:
    """Run the FULL ablation suite once over a SHORT window (last few fixture sessions; each
    observation still carries full history ≤ t) so make check stays fast yet exercises every variant."""
    from src.data.loaders import load_prices

    cfg = Config(offline=True)
    cfg.results_dir = str(tmp_path_factory.mktemp("abl"))
    frame = load_prices(cfg.ticker, date.fromisoformat(cfg.test_end))
    dates = [ts.date() for ts in frame.index]
    cfg.test_start = dates[-6].isoformat()  # ~6-session window
    return cfg, run_ablations(cfg)


def test_ablation_table_has_every_variant_and_baseline(ablation_run) -> None:
    cfg, out = ablation_run
    names = {r["variant"] for r in out["table"]}
    assert names >= set(ABLATION_VARIANTS)                       # all 6 variants
    assert {"buy_hold", "av_sentiment", "single_agent"} <= names  # + the 3 baselines
    assert all("total_return" in r and "sharpe" in r for r in out["table"])  # full metric row each


def test_ablation_writes_table_and_per_variant_curves(ablation_run) -> None:
    cfg, _ = ablation_run
    assert os.path.exists(os.path.join(cfg.results_dir, "ablation_table.csv"))
    assert os.path.exists(os.path.join(cfg.results_dir, "ablation_table.md"))
    for name in ABLATION_VARIANTS:
        assert os.path.exists(os.path.join(cfg.results_dir, "curves", f"{name}.csv"))
