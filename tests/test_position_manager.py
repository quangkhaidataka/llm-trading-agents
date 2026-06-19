"""S32 tests — PositionManager deterministic hysteresis + risk veto.

Pure rule engine (no LLM, no randomness). Covers the FULL current_position × signal
transition table and veto-overrides-strong-signal. Thresholds from config:
tau_enter=0.70, tau_exit=0.40, tau_flip=0.80, vol_cap=0.40, dd_cap=-0.15,
macro_risk_cap=0.70, disagreement_cap=0.70.
"""

from __future__ import annotations

from datetime import date

from config import Config
from src.agents.position_manager import PositionManager
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState, ResearchStance, TradeDecision


def _obs() -> Observation:
    return Observation(
        ticker="AAPL", t=date(2024, 6, 5), aapl_news=[], macro_news=[],
        indicators={}, price=100.0, spy_trend=0.0,
    )


def _stance(target: int = 1, valid: bool = True) -> ResearchStance:
    # action is advisory only; the manager decides from target/conviction/thesis.
    return ResearchStance(
        bull_case="bull", bear_case="bear", thesis_still_valid=valid,
        action="hold", target_direction=target, conviction=0.5,
    )


def _macro(regime: str = "neutral", risk: float = 0.3) -> MacroSignal:
    return MacroSignal(rationale="x", regime=regime, macro_risk=risk, drivers=[])


def _decide(
    cfg: Config, state: PortfolioState, stance: ResearchStance, *,
    macro: MacroSignal | None = None, conviction: float = 0.5,
    vol: float = 0.20, dd: float = -0.05, dis: float = 0.10,
) -> TradeDecision:
    return PositionManager(cfg).decide(
        _obs(), state, stance, macro or _macro(), conviction, vol, dd, dis
    )


# ── flat → open / hold ───────────────────────────────────────────────────────
def test_flat_opens_long_at_tau_enter() -> None:
    cfg = Config(offline=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=1), conviction=cfg.tau_enter)
    assert out.new_position == 1 and not out.vetoed and out.new_thesis == "bull"


def test_flat_opens_short_when_allowed() -> None:
    cfg = Config(offline=True, allow_short=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=-1), conviction=0.85)
    assert out.new_position == -1 and out.new_thesis == "bear"


def test_flat_open_short_blocked_when_disallowed() -> None:
    cfg = Config(offline=True, allow_short=False)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=-1), conviction=0.85)
    assert out.new_position == 0 and not out.vetoed and "blocked" in out.reason


def test_flat_holds_below_tau_enter() -> None:
    cfg = Config(offline=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=1), conviction=0.5)
    assert out.new_position == 0 and not out.vetoed


# ── in position → close / flip / hold ────────────────────────────────────────
def test_close_when_thesis_invalidated() -> None:
    cfg = Config(offline=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=3)
    out = _decide(cfg, state, _stance(target=1, valid=False), conviction=0.95)  # high conv, but thesis broken
    assert out.new_position == 0 and out.new_thesis == "" and "thesis" in out.reason


def test_close_when_conviction_decays_to_tau_exit() -> None:
    cfg = Config(offline=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=3)
    out = _decide(cfg, state, _stance(target=1, valid=True), conviction=cfg.tau_exit)
    assert out.new_position == 0 and out.new_thesis == ""


def test_flip_long_to_short_at_tau_flip() -> None:
    cfg = Config(offline=True, allow_short=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=5)
    out = _decide(cfg, state, _stance(target=-1, valid=True), conviction=cfg.tau_flip)
    assert out.new_position == -1 and out.new_thesis == "bear"


def test_opposite_signal_below_tau_flip_holds() -> None:
    cfg = Config(offline=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=5)
    # 0.75: above tau_exit (not a close), opposite direction, but below tau_flip (not a flip) → hold
    out = _decide(cfg, state, _stance(target=-1, valid=True), conviction=0.75)
    assert out.new_position == 1 and out.new_thesis == "launch"


def test_same_direction_in_deadband_holds() -> None:
    cfg = Config(offline=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=5)
    out = _decide(cfg, state, _stance(target=1, valid=True), conviction=0.6)
    assert out.new_position == 1 and out.new_thesis == "launch"


def test_flip_to_short_blocked_closes_to_flat() -> None:
    cfg = Config(offline=True, allow_short=False)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=5)
    out = _decide(cfg, state, _stance(target=-1, valid=True), conviction=0.95)
    assert out.new_position == 0 and not out.vetoed and "blocked" in out.reason


# ── veto overrides even a tau_flip-strength signal ───────────────────────────
def test_veto_high_volatility() -> None:
    cfg = Config(offline=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=1), conviction=0.95, vol=0.50)
    assert out.vetoed and out.new_position == 0


def test_veto_drawdown_breach() -> None:
    cfg = Config(offline=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=1), conviction=0.95, dd=-0.20)
    assert out.vetoed and out.new_position == 0


def test_veto_macro_risk_off() -> None:
    cfg = Config(offline=True)
    out = _decide(
        cfg, PortfolioState(current_position=0), _stance(target=1),
        macro=_macro(regime="risk_off"), conviction=0.95,
    )
    assert out.vetoed and out.new_position == 0


def test_veto_high_macro_risk() -> None:
    cfg = Config(offline=True)
    out = _decide(
        cfg, PortfolioState(current_position=0), _stance(target=1),
        macro=_macro(risk=0.85), conviction=0.95,
    )
    assert out.vetoed and out.new_position == 0


def test_veto_high_disagreement() -> None:
    cfg = Config(offline=True)
    out = _decide(cfg, PortfolioState(current_position=0), _stance(target=1), conviction=0.95, dis=0.90)
    assert out.vetoed and out.new_position == 0


def test_veto_forces_held_position_flat() -> None:
    cfg = Config(offline=True)
    state = PortfolioState(current_position=1, active_thesis="launch", days_held=5)
    out = _decide(cfg, state, _stance(target=1, valid=True), conviction=0.95, vol=0.55)
    assert out.vetoed and out.new_position == 0 and out.new_thesis == ""
