# S3.2 — PositionManager: Deterministic Hysteresis + Risk Veto

## Objective
The analysts argue and the debate recommends, but somebody has to actually move the
position — calmly, consistently, and without second-guessing itself into a churn of
trades. That is the `PositionManager`. It is deliberately *not* an LLM: it is a pure,
deterministic rule engine, so the same inputs always yield the same `TradeDecision`
and the decision number stays mathematical. Two ideas drive it. First, **risk veto
comes first**: before any conviction is even considered, if realized volatility blows
past `vol_cap`, drawdown breaches `dd_cap`, the macro regime is `risk_off` (or
`macro_risk` is high), or the analysts violently disagree, we force the position flat
and stop — risk control overrules signal generation, always, no exceptions. Second,
**asymmetric hysteresis**: only if the veto passes do we apply sticky thresholds on
the *calibrated* conviction. It takes a high bar (`tau_enter`) to open a new position,
a fairly low bar (`tau_exit`) — or an invalidated thesis — to close one, and a very
high bar (`tau_flip`) to reverse outright. Everything in between is `hold`. This gap
between entering and exiting is exactly what produces the low-turnover, hold-across-
sessions behavior the project is testing. The full current-position × signal table is
spelled out below so every transition is covered and testable.

## Inputs and Outputs
- **Inputs:**
  - `obs: Observation` — point-in-time context for the day.
  - `state: PortfolioState` — `current_position ∈ {-1,0,1}`, `active_thesis`,
    `entry_price`, `days_held`.
  - `stance: ResearchStance` — debate's `action`, `target_direction`,
    `thesis_still_valid`, plus bull/bear cases.
  - `macro: MacroSignal` — `regime`, `macro_risk` (feeds the veto).
  - `conviction: float` — **calibrated** P(correct) from the conviction engine (NOT the
    LLM self-report).
  - `realized_vol: float`, `drawdown: float`, `disagreement: float` — risk veto inputs.
  - `config` knobs: `tau_enter`, `tau_exit`, `tau_flip`, `vol_cap`, `dd_cap`,
    `allow_short`.
- **Outputs:**
  - **`TradeDecision`** (Pydantic) — `{new_position ∈ {-1,0,1}, new_thesis, vetoed: bool,
    reason: str}`. `new_thesis` is set on `open`/`flip`, preserved on `hold`, cleared on
    `close`/veto. `reason` is a short human string captured into the per-day trace.

## Skeleton Python Code
```python
# src/agents/position_manager.py — deterministic hysteresis + risk veto (no LLM)
from __future__ import annotations

from config import Config
from src.data.loaders import Observation
from src.schemas import MacroSignal, PortfolioState, ResearchStance, TradeDecision


class PositionManager:
    """Turns the debate's recommendation + calibrated conviction into the next position.
    Pure rule engine; all thresholds come from config. Veto is checked BEFORE hysteresis."""

    def __init__(self, config: Config) -> None:
        """Hold config (tau_enter/tau_exit/tau_flip, vol_cap, dd_cap, allow_short)."""
        ...

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
        """Step 1 (VETO FIRST): force flat (vetoed=True) if realized_vol > vol_cap,
           drawdown < dd_cap, macro.regime == 'risk_off' / high macro_risk, or high disagreement.
           Step 2 (else ASYMMETRIC HYSTERESIS on calibrated conviction):
             flat            -> open  only if conviction >= tau_enter (direction = target_direction)
             in position     -> close if thesis_still_valid is False OR conviction <= tau_exit
             opposite signal -> flip  only if conviction >= tau_flip (blocked if not allow_short)
             otherwise       -> hold (preserve thesis, days_held increments downstream)
           Returns TradeDecision(new_position, new_thesis, vetoed, reason)."""
        ...
```

## How It Connects
The graph's `conviction` node hands the `PositionManager` the calibrated conviction
plus the debate stance, the macro regime, and the live risk measurements; the manager
runs its two-stage rule and returns a `TradeDecision` that the `commit` node applies
to `PortfolioState` for execution at `t+1`. Because it is stateless and pure, it reads
the *current* position to decide whether a recommendation means open, hold, close, or
flip — the same `target_direction` produces different transitions depending on where
the portfolio already is, which is precisely what makes the policy stateful across
days. The veto-before-hysteresis ordering means a `risk_off` macro reading or a
volatility spike can overrule even a `tau_flip`-strength buy, cleanly separating the
risk layer from the signal layer that the analysts and memory feed.

### Full transition table (after veto passes)
| current_position | condition | action | new_position | new_thesis |
|---|---|---|---|---|
| 0 (flat) | conviction ≥ `tau_enter`, target_direction = +1 | open long | +1 | set from stance |
| 0 (flat) | conviction ≥ `tau_enter`, target_direction = −1, `allow_short` | open short | −1 | set from stance |
| 0 (flat) | conviction ≥ `tau_enter`, target_direction = −1, not `allow_short` | blocked | 0 | "" |
| 0 (flat) | conviction < `tau_enter` | hold flat | 0 | "" |
| +1 / −1 | `thesis_still_valid` is False | close | 0 | "" (cleared) |
| +1 / −1 | conviction ≤ `tau_exit` | close | 0 | "" (cleared) |
| +1 / −1 | opposite target_direction, conviction ≥ `tau_flip`, allowed | flip | ∓1 | set from stance |
| +1 / −1 | opposite target_direction, conviction < `tau_flip` | hold | unchanged | preserved |
| +1 / −1 | same direction, conviction in (`tau_exit`, `tau_flip`) | hold | unchanged | preserved |
| any | veto triggered | force flat | 0 | "" (vetoed=True) |

## Key Technology, Design Patterns & Packages
- **State machine / rule engine** — `decide` is a pure function keyed on
  `current_position` × signal × calibrated conviction; deterministic, fully unit-testable
  via the transition table (no randomness, no LLM).
- **Guard-clause precedence (veto first)** — risk checks short-circuit before any
  hysteresis branch, encoding "risk control overrules signals" structurally.
- **Asymmetric hysteresis** — distinct enter/exit/flip thresholds from `config` create a
  dead-band that suppresses churn → low turnover, longer holding periods.
- **Pydantic (`TradeDecision`)** — typed, validated output so the contract with the
  commit node and the trace logger is enforced, not hand-parsed.
- **No new packages** — pure Python + stdlib; all numbers live in `config.py`.

## Definition of Done
- [x] **Acceptance command:** `pytest tests/test_position_manager.py -q` → 16 passed. ✅ 2026-06-19
- [x] **Tests:** offline & deterministic (pure rule engine, no LLM/randomness); cover the **FULL
  current-position × signal transition table** — flat→open only at `conviction ≥ tau_enter` (with/without
  `allow_short`), in-position→close on `thesis_still_valid=False` OR `conviction ≤ tau_exit`,
  opposite→flip only at `conviction ≥ tau_flip` (blocked-to-short → close to flat), else hold (thesis
  preserved); and **veto-overrides-strong-signal** — a `tau_flip`-strength buy forced flat (`vetoed=True`)
  on `realized_vol > vol_cap`, `drawdown < dd_cap`, `regime == risk_off`, `macro_risk > macro_risk_cap`,
  or `disagreement > disagreement_cap` (incl. forcing a HELD position flat).
- [x] **Gate:** `make check` green (ruff + mypy 23 files + 59 unit + e2e).
- [x] **features.json:** F09 → `passing` with evidence.
- [x] **Rules:** veto-before-hysteresis enforced via guard clause (`_veto_reason` short-circuits);
  deterministic, no LLM; all numbers (`tau_enter/exit/flip`, `vol_cap`, `dd_cap`, `macro_risk_cap`,
  `disagreement_cap`, `allow_short`) in `config.py`; conviction consumed is the **calibrated** P(correct).
- [x] **Tracking:** PROGRESS.md updated; ADR-010 records the two new veto knobs + flip-blocked→close
  decision; `use_hysteresis` ablation flag deferred to S5 (YAGNI).
