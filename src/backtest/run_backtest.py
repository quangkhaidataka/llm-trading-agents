"""Walk-forward backtest (spec §6, §13.1).

Steps sequentially through the 2025-2026 test window carrying PortfolioState.
Each day t: run the graph -> new_position applied to the RETURN OF SESSION t+1
(no execution lookahead). A trade occurs only when new_position != current_position;
charge fee_bps on each change (penalize churn). After each day, stage/flush memory.

vectorbt computes: equity curve, Sharpe, Sortino, MaxDD, turnover, avg holding
period. PnL must be NET OF FEES. Only the 2025-2026 window is reported (warm-up
2022-2024 populates memory + calibration only — never report its PnL, spec §3).
"""

from __future__ import annotations

from config import Config


def run_backtest(config: Config) -> dict:
    """Run the walk-forward loop and return metrics + equity curve."""
    raise NotImplementedError("M4: walk-forward + vectorbt, net of fees")
