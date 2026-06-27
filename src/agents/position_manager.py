"""PositionManager (spec §5.6) — deterministic hysteresis + risk veto.

NOT an LLM: a pure rule engine, so the same inputs always yield the same TradeDecision
and the decision number stays mathematical. Two ideas drive it:

1. RISK VETO FIRST (guard clause). Before conviction is even considered, force flat if
   realized_vol > vol_cap, drawdown < dd_cap, macro regime == risk_off / macro_risk >
   macro_risk_cap, or disagreement > disagreement_cap. Risk control overrules signals.

2. ASYMMETRIC HYSTERESIS on the CALIBRATED conviction (spec §7.3 — NOT the LLM
   self-report): a high bar to open (tau_enter), a low bar / invalid thesis to close
   (tau_exit), a very high bar to flip (tau_flip); everything else is hold. The enter↔exit
   dead-band is what produces low turnover / hold-across-sessions behavior.

The full current_position × signal transition table is in the substep plan (S3.2).
"""

from __future__ import annotations

from typing import Literal

from config import Config
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState, ResearchStance, TradeDecision

Position = Literal[-1, 0, 1]


class PositionManager:
    """Turns the debate's recommendation + calibrated conviction into the next position.
    Pure rule engine; all thresholds come from config. Veto is checked BEFORE hysteresis."""

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
        # ── Step 1: RISK VETO FIRST — short-circuit before any hysteresis branch ──
        veto = self._veto_reason(macro, realized_vol, drawdown, disagreement)
        if veto is not None:
            return TradeDecision(new_position=0, new_thesis="", vetoed=True, reason=f"VETO: {veto}")

        pos = state.current_position
        target = stance.target_direction

        # ── Step 2: ASYMMETRIC HYSTERESIS on calibrated conviction ──
        if pos == 0:
            return self._from_flat(stance, target, conviction)
        return self._from_position(state, stance, pos, target, conviction)

    # ── veto ──────────────────────────────────────────────────────────────────
    def _veto_reason(
        self, macro: MacroSignal, realized_vol: float, drawdown: float, disagreement: float
    ) -> str | None:
        cfg = self.config
        if realized_vol > cfg.vol_cap:
            return f"realized_vol {realized_vol:.2f} > vol_cap {cfg.vol_cap}"
        if drawdown < cfg.dd_cap:
            return f"drawdown {drawdown:.2f} < dd_cap {cfg.dd_cap}"
        if macro.regime == "risk_off":
            return "macro regime risk_off"
        if macro.macro_risk > cfg.macro_risk_cap:
            return f"macro_risk {macro.macro_risk:.2f} > macro_risk_cap {cfg.macro_risk_cap}"
        if disagreement > cfg.disagreement_cap:
            return f"disagreement {disagreement:.2f} > disagreement_cap {cfg.disagreement_cap}"
        return None

    # ── flat → open / hold ──────────────────────────────────────────────────────
    def _from_flat(self, stance: ResearchStance, target: Position, conviction: float) -> TradeDecision:
        cfg = self.config
        if conviction >= cfg.tau_enter and target != 0:
            if target == -1 and not cfg.allow_short:
                return TradeDecision(
                    new_position=0, new_thesis="", vetoed=False,
                    reason="hold flat (open short blocked: allow_short=False)",
                )
            return TradeDecision(
                new_position=target,
                new_thesis=self._thesis(stance, target),
                vetoed=False,
                reason=f"open {_dir(target)} (conviction {conviction:.2f} >= tau_enter {cfg.tau_enter})",
            )
        return TradeDecision(
            new_position=0, new_thesis="", vetoed=False,
            reason=f"hold flat (conviction {conviction:.2f} < tau_enter {cfg.tau_enter})",
        )

    # ── in position → close / flip / hold ───────────────────────────────────────
    def _from_position(
        self, state: PortfolioState, stance: ResearchStance, pos: Position, target: Position, conviction: float
    ) -> TradeDecision:
        cfg = self.config
        # no-hysteresis ablation (use_hysteresis=False): collapse the dead-band by exiting at the
        # SAME bar as entry (tau_enter), so there is no sticky enter↔exit asymmetry.
        tau_exit = cfg.tau_exit if cfg.use_hysteresis else cfg.tau_enter

        # close conditions take precedence (thesis broken OR conviction decayed)
        if not stance.thesis_still_valid:
            return TradeDecision(
                new_position=0, new_thesis="", vetoed=False, reason="close (thesis invalidated)"
            )
        if conviction <= tau_exit:
            return TradeDecision(
                new_position=0, new_thesis="", vetoed=False,
                reason=f"close (conviction {conviction:.2f} <= tau_exit {tau_exit})",
            )

        # opposite-direction signal → flip only on a very high bar
        if target == -pos:
            if conviction >= cfg.tau_flip:
                if target == -1 and not cfg.allow_short:
                    return TradeDecision(
                        new_position=0, new_thesis="", vetoed=False,
                        reason="close (flip to short blocked: allow_short=False)",
                    )
                return TradeDecision(
                    new_position=target,
                    new_thesis=self._thesis(stance, target),
                    vetoed=False,
                    reason=f"flip to {_dir(target)} (conviction {conviction:.2f} >= tau_flip {cfg.tau_flip})",
                )
            return TradeDecision(
                new_position=pos, new_thesis=state.active_thesis, vetoed=False,
                reason=f"hold (opposite signal but conviction {conviction:.2f} < tau_flip {cfg.tau_flip})",
            )

        # same direction (or target flat) within the dead-band → maintain
        return TradeDecision(
            new_position=pos, new_thesis=state.active_thesis, vetoed=False,
            reason="hold (maintain position; thesis intact, conviction in dead-band)",
        )

    @staticmethod
    def _thesis(stance: ResearchStance, target: int) -> str:
        """Entry rationale captured on open/flip: the bull case for a long, bear case for a short."""
        return stance.bull_case if target == 1 else stance.bear_case


def _dir(target: int) -> str:
    return {1: "long", -1: "short", 0: "flat"}[target]
