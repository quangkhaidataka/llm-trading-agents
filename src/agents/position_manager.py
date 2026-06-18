"""PositionManager (spec §5.6) — state-aware + hysteresis + risk veto.

Translates the ResearchStance into a position state transition, applies asymmetric
hysteresis and risk control, makes the final call. Output: TradeDecision.

Hysteresis (on CALIBRATED conviction, spec §7.3):
  - flat        -> open  only when conviction >= tau_enter
  - in position -> close only when thesis_still_valid is False OR conviction <= tau_exit
  - flip        only when opposite signal is very strong (conviction >= tau_flip)

Risk veto -> force flat / reduce size when realized vol > vol_cap, drawdown < dd_cap,
regime == risk_off / high macro_risk, or high signal disagreement.

Spec §5.6 lightweight option: hysteresis + vol cap MAY be a deterministic rule
instead of an LLM and still preserve hold + veto behavior. Defaulting to that
keeps the decision number mathematical (spec §7.3) — the LLM only supplies
direction + reasoning.
"""

from __future__ import annotations

from config import Config
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState, ResearchStance, TradeDecision


class PositionManager:
    def __init__(self, config: Config) -> None:
        self.config = config

    def decide(
        self,
        obs: Observation,
        state: PortfolioState,
        stance: ResearchStance,
        macro: MacroSignal,
        conviction: float,        # calibrated (eval/calibration), NOT the LLM's self-report
        realized_vol: float,
        drawdown: float,
        disagreement: float,
    ) -> TradeDecision:
        raise NotImplementedError("M3: deterministic hysteresis + veto -> TradeDecision")
