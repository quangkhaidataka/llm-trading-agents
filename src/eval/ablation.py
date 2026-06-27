"""S5.3 — ablations (why the system works, component by component).

Every variant is a `Config` TOGGLE over the SAME compiled graph + dollar-accounting loop + frozen
calibrator — never a code fork. The LangGraph builder reads the flag and bypasses the corresponding
node (no MacroAgent, no debate, no retrieval) or `run_one_day`/PositionManager change behavior
(stateless re-decide, collapsed hysteresis), so the ONLY thing that differs between two table rows is
the one component under test. The five ablations isolate the headline contributions:

  - stateless     : throw away PortfolioState + hysteresis  → does the state-aware policy help? (RQ3)
  - no_memory     : drop FAISS retrieval + MemoryAgent      → does episodic memory add alpha? (RQ2)
  - no_macro      : remove MacroAgent + its risk-off veto
  - no_debate     : skip Bull/Bear, analysts decide direct  → does adversarial debate help? (RQ1)
  - no_hysteresis : keep state but collapse tau_exit:=tau_enter (no asymmetric dead-band)

All variant rows + the S5.2 baselines are stacked into one comparison table where "beats the
AV-sentiment baseline" is the headline claim.
"""

from __future__ import annotations

from dataclasses import replace

from config import Config

# Each entry: variant name -> the config overrides (feature-flag toggles only).
ABLATION_VARIANTS: dict[str, dict] = {
    "full":           {},
    "stateless":      {"stateless": True, "use_hysteresis": False},
    "no_memory":      {"use_memory": False},
    "no_macro":       {"use_macro": False},
    "no_debate":      {"use_debate": False},
    "no_hysteresis":  {"use_hysteresis": False},  # collapse: tau_exit := tau_enter (PositionManager)
}

# The comparison columns (the full metric set, shared by variants AND baselines).
_TABLE_COLS = [
    "variant", "total_return", "sharpe", "sortino", "max_drawdown_over_c0",
    "hit_rate", "turnover", "avg_holding_period", "n_trades", "total_fees",
]


def make_variant_config(base_config: Config, overrides: dict) -> Config:
    """Return a copy of base_config with only the given feature flags toggled (dataclasses.replace) —
    variants are config toggles, never code forks."""
    return replace(base_config, **overrides)


def run_one_variant(name: str, config: Config) -> dict:
    """Run a single variant over the test window via the SAME engine + dollar-accounting loop (and the
    frozen calibrator, when present) — WITHOUT clobbering the main backtest's results/ artifacts.
    Returns {'curve': list[dict], 'metrics': dict}."""
    from src.backtest.run_backtest import Backtester

    result = Backtester(config).run(write=False)
    return {"curve": result["equity"], "metrics": result["metrics"]}


def _metric_row(name: str, metrics: dict) -> dict:
    """Project a metrics dict onto the comparison columns (missing keys → '')."""
    row = {"variant": name}
    for col in _TABLE_COLS[1:]:
        row[col] = metrics.get(col, "")
    return row


def _fmt(v: object) -> str:
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def _write_table(rows: list[dict], csv_path: str, md_path: str) -> None:
    """Render the aggregated metric rows to ablation_table.csv + a Markdown table for the write-up
    (manual MD so no `tabulate` dependency is added)."""
    import csv

    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_TABLE_COLS)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in _TABLE_COLS})

    with open(md_path, "w") as fh:
        fh.write("| " + " | ".join(_TABLE_COLS) + " |\n")
        fh.write("|" + "|".join(["---"] * len(_TABLE_COLS)) + "|\n")
        for r in rows:
            fh.write("| " + " | ".join(_fmt(r.get(c, "")) for c in _TABLE_COLS) + " |\n")


def _write_curve(path: str, curve: list[dict]) -> None:
    import csv

    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "equity", "cum_pnl_strategy", "cum_pnl_buyhold"])
        for row in curve:
            writer.writerow([row.get("date"), row.get("equity"),
                             row.get("cum_pnl_strategy"), row.get("cum_pnl_buyhold")])


def run_ablations(base_config: Config) -> dict:
    """Run every ABLATION_VARIANTS variant over the same engine (reusing the LLM cache + frozen
    calibrator), add the S5.2 baselines, aggregate all rows into one tidy comparison table
    (results/ablation_table.csv + .md) and per-variant curves under results/curves/. Returns the
    comparison dict."""
    import os

    from src.eval.baselines import run_baselines

    out_dir = base_config.results_dir
    curves_dir = os.path.join(out_dir, "curves")
    os.makedirs(curves_dir, exist_ok=True)

    rows: list[dict] = []
    variants: dict[str, dict] = {}
    for name, overrides in ABLATION_VARIANTS.items():
        cfg = make_variant_config(base_config, overrides)
        result = run_one_variant(name, cfg)
        variants[name] = result
        _write_curve(os.path.join(curves_dir, f"{name}.csv"), result["curve"])
        rows.append(_metric_row(name, result["metrics"]))

    # Stack the S5.2 baselines into the SAME table (the AV-sentiment row is the one to beat).
    baselines = run_baselines(base_config)
    for bname in ("buy_hold", "av_sentiment", "single_agent"):
        rows.append(_metric_row(bname, baselines[bname]["metrics"]))

    _write_table(rows, os.path.join(out_dir, "ablation_table.csv"),
                 os.path.join(out_dir, "ablation_table.md"))
    return {"variants": variants, "baselines": baselines, "table": rows,
            "corr_llm_sentiment_vs_av": baselines["corr_llm_sentiment_vs_av"]}
