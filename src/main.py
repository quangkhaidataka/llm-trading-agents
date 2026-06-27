"""Entrypoint (spec §13.4).

    python -m src.main --mode download    # download + cache data once to Parquet
    python -m src.main --mode warmup      # replay 2022-2024 -> fit + freeze the conviction calibrator
    python -m src.main --mode backtest    # run the 2025-2026 backtest -> equity curve
    python -m src.main --mode ablation    # baselines + ablations + calibration
"""

from __future__ import annotations

import argparse

from config import config


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-agent LLM trading system")
    parser.add_argument(
        "--mode",
        choices=["download", "warmup", "backtest", "ablation"],
        required=True,
        help="download: cache data | warmup: fit calibrator | backtest: run test | ablation: eval suite",
    )
    parser.add_argument("--ticker", default=config.ticker, help="override config.ticker")
    parser.add_argument("--offline", action="store_true", help="MockLLM + fixtures, no network")
    args = parser.parse_args()

    config.ticker = args.ticker
    if args.offline:
        config.offline = True

    if args.mode == "download":
        from src.data.loaders import download

        download()
    elif args.mode == "warmup":
        from src.eval.calibration import run_warmup_calibration

        run_warmup_calibration(config)
    elif args.mode == "backtest":
        from src.backtest.run_backtest import run_backtest

        run_backtest(config)
    elif args.mode == "ablation":
        from src.eval.ablation import run_ablations

        run_ablations(config)


if __name__ == "__main__":
    main()
