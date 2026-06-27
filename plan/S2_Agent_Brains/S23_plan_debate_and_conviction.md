# S2.3 — DebateAgent & Conviction Engine

## Objective
This is where the system stops being three voices and becomes a decision. The `DebateAgent`
is state-aware: it knows the current position, the entry thesis, and how long it has been
held, then runs a structured four-step Bull-vs-Bear argument over the four analyst signals
(News, Macro, Technical, Memory) and the `PortfolioState`. Crucially it is framed as a
*position manager*, not a daily classifier — it asks "is the original thesis still valid?"
and is biased to continuity, preferring `hold` unless there is clear contradicting evidence.
It returns a `ResearchStance` with `action ∈ {hold, open, close, flip}`. But its self-reported
`conviction` is *not* trusted — LLMs are overconfident and inconsistent. So the second half
of this sub-step is the conviction engine in `src/eval/calibration.py`, which **computes**
conviction from math, in two layers: Layer 1 (`composite_conviction`) blends measurable
signals — agent agreement, mean confidence, and memory consistency; Layer 2
(`self_consistency_conviction`) samples the DebateAgent K times at `temperature>0` and asks
how often it lands on the majority action. `raw_conviction` combines both into a raw score
`z`. The headline: the LLM supplies direction + reasoning; the decision number comes from
math. (Layer 3 — calibrating `z` into a true probability — is Step 5, since it needs history.)

## Inputs and Outputs
- **Inputs**
  - The four analyst signals (`NewsSignal`, `MacroSignal`, `TechnicalSignal`, `MemoryContext`)
    + `PortfolioState`; `Observation` for `{t}`.
  - `make_llm(config)`; `config` (`K`, `w1/w2/w3`, `alpha/beta`, `ticker`, `temperature` — the
    DebateAgent overrides to `>0` for Layer-2 sampling).
- **Outputs**
  - `src/agents/debate.py` → `DebateAgent.run(...) -> ResearchStance`
    (bull_case, bear_case, thesis_still_valid, action, target_direction, conviction);
    plus a `sample(...)` path that produces the K actions for self-consistency.
  - Conviction engine (`src/eval/calibration.py`):
    - `composite_conviction(signals, memory_consistency, config) -> float` (Layer 1, 0–1).
    - `self_consistency_conviction(actions, K) -> float` (Layer 2, majority frequency).
    - `raw_conviction(conviction_raw, conviction_sc, config) -> float` (combined `z`, 0–1).
  - `tests/test_agents.py` (DebateAgent prefers `hold` when held thesis stays valid) +
    conviction unit tests. Layer-3 `fit_calibrator`/`reliability_diagram` are **Step 5**.

## Skeleton Python Code
```python
"""src/agents/debate.py — state-aware Bull/Bear debate (Template Method)."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.data.loaders import Observation
from src.schemas import (NewsSignal, MacroSignal, TechnicalSignal, MemoryContext,
                         ResearchStance, PortfolioState)

DEBATE_SYSTEM = """You moderate a position-management debate for the asset {ticker}. Current
position {current_position} (-1 short, 0 flat, +1 long); entry thesis: "{active_thesis}";
held {days_held} sessions. Use ONLY the signals provided (no outside/future knowledge). Work in order:
  Step 1 - Bull case: the strongest GENUINE argument that {ticker} will RISE (a reason to be LONG).
  Step 2 - Bear case: the strongest GENUINE argument that {ticker} will FALL (a reason to be SHORT) -
    a real downside thesis, NOT merely "sit out". Steelman both cases; never strawman.
  Step 3 - Thesis check: is the ORIGINAL entry thesis still valid today? (true/false + why).
  Step 4 - Decide target_direction in {{-1, 0, +1}}, then action in {{hold, open, close, flip}}:
      +1 LONG  - the bull case clearly outweighs the bear case;
      -1 SHORT - the bear case clearly outweighs the bull case (you genuinely expect a FALL). A real
                 downside edge is a reason to SHORT; do NOT collapse it into flat out of caution.
       0 FLAT  - ONLY when neither side has an edge (genuine uncertainty) or risk is too high to hold
                 ANY directional position. Flat means "no view", not "mildly bearish".
    SHORT and FLAT are different decisions: choose -1 when you expect a decline, 0 only when you don't
    have a directional view. Then map direction to action given the current position.
Bias to continuity: if a position is held and its thesis still holds, prefer HOLD unless there is
clear, specific contradicting evidence; only flip on strong opposing evidence.
Also return conviction in [0,1] = probability the recommended action is correct over ~5 sessions;
be honest, not strategic - the final decision number is recomputed downstream from math."""  # Gate-A: ADR-016
DEBATE_HUMAN = """Date: {t}
PortfolioState: position={current_position}, thesis="{active_thesis}", days_held={days_held}
NewsSignal: {news}
MacroSignal: {macro}
TechnicalSignal: {technical}
MemoryContext: {memory}"""


class DebateAgent(BaseAgent):
    """State-aware Bull/Bear moderator → ResearchStance. Sampled K times for self-consistency."""

    def _build_chain(self):
        """Return ChatPromptTemplate.from_messages([DEBATE_SYSTEM, DEBATE_HUMAN])
        | self.llm.with_structured_output(ResearchStance)."""
        ...

    def run(self, obs: Observation, state: PortfolioState, news: NewsSignal,
            macro: MacroSignal, technical: TechnicalSignal,
            memory: MemoryContext) -> ResearchStance:
        """Render the four signals + PortfolioState into the prompt and invoke once (temp=0)."""
        ...

    def sample(self, obs: Observation, state: PortfolioState, news: NewsSignal,
               macro: MacroSignal, technical: TechnicalSignal,
               memory: MemoryContext, k: int) -> list[str]:
        """Invoke the chain k times at temperature>0 and return the list of recommended `action`s —
        the input to self_consistency_conviction. (Evidence-order shuffling was rejected — ADR-008.)"""
        ...
```

```python
"""src/eval/calibration.py — conviction engine (Layers 1-2; Layer 3 = Step 5)."""
from __future__ import annotations

from config import Config


def composite_conviction(signals: list[dict], memory_consistency: float, config: Config) -> float:
    """Layer 1 — blend measurable quantities into conviction_raw (0–1), NOT the LLM's self-report.

    `signals` = the directional agent outputs, each {direction: -1|0|+1, confidence: 0..1}.
    Computes: agreement = |Σ sᵢcᵢ| / Σ_{sᵢ≠0} cᵢ  — ABSTENTION-AWARE (Gate-B fix): the denominator sums
              confidence over DIRECTIONAL agents only (sᵢ≠0), so a flat vote neither reinforces nor
              dilutes a confident directional minority → a lone short can clear tau_enter; guard
              no-directional-agent → 0,
              mean_confidence = mean(cᵢ),
              and folds in memory_consistency (share of retrieved analogs that supported the action).
    Returns w1·agreement + w2·mean_confidence + w3·memory_consistency  (weights from config, Σw=1)."""
    ...


def self_consistency_conviction(actions: list[str], K: int) -> float:
    """Layer 2 — turn a fuzzy judgment into a frequency.

    `actions` = the K actions the DebateAgent produced when asked the same question K times at
    temperature>0. Returns (count of the most common action) / K — high = stable/confident,
    low = wavering. Example: ['open','open','open','hold','open'] → 0.8."""
    ...


def raw_conviction(conviction_raw: float, conviction_sc: float, config: Config) -> float:
    """Combine Layers 1 and 2 into the raw score z = alpha·conviction_raw + beta·conviction_sc
    (alpha, beta from config). z is a 0–1 score; it becomes a true probability only after the
    Step-5 calibrator maps it via P(correct | z)."""
    ...
```

## How It Connects
By the time the DebateAgent runs, the three analysts and the memory layer have each emitted
a typed signal; the DebateAgent gathers them plus the `PortfolioState`, renders them into its
four-step prompt, and (through the same `make_llm` brain and `with_structured_output(ResearchStance)`
contract) returns a `ResearchStance` saying hold/open/close/flip. The conviction engine then
ignores the stance's *self-reported* conviction and rebuilds trust from math: it casts the
analyst signals as direction-and-confidence votes into `composite_conviction` for Layer 1,
re-invokes the DebateAgent K times at `temperature>0` and feeds the resulting action list to
`self_consistency_conviction` for Layer 2, and folds the two together via `raw_conviction`
into a single raw score `z`. That `z` is the clean number Step 3's PositionManager will threshold
against the τ knobs — and Step 5 will calibrate into a real probability — which is why the whole
design insists the LLM contributes only direction and reasoning while the decision number is
computed, not confessed.

## Key Technology, Design Patterns & Packages
- **Template Method (`BaseAgent`)** — the DebateAgent reuses the same `_build_chain`/`run`
  lifecycle as the analysts, adding a `sample` path for K-shot self-consistency.
- **Strategy** — the two conviction layers are independent strategies (`composite_conviction`,
  `self_consistency_conviction`) combined by `raw_conviction`; weights/blend live in `config`.
- **LangChain LCEL + `with_structured_output(ResearchStance)`** — structured debate output,
  no hand-parsing; the DebateAgent overrides temperature to `>0` only for Layer-2 sampling.
- **Pure functions over math, not LLM self-report** — conviction is computed; randomness lives
  only in the LLM layer, keeping the conviction functions deterministic and unit-testable.
- **Pydantic (`ResearchStance`)** — typed, validated decision contract carrying both the
  bull/bear narrative (for the explainability trace) and the recommended action.
- **Why:** decouples "what direction" (LLM) from "how sure" (math), so thresholds later mean
  probabilities; Layer 3 (isotonic/Platt calibration) is deferred to Step 5 (needs history).

## Definition of Done
- [x] **Acceptance command:** `pytest tests/test_agents.py -k debate -q` (3 passed → F08) and `pytest tests/test_calibration.py -k conviction -q` (5 passed → Layers 1-2) both green. ✅ 2026-06-19
- [x] **Tests (offline & deterministic):** with `Config(offline=True)`, `DebateAgent.run(...)` fuses the four signals + `PortfolioState` into a valid `ResearchStance` (bull_case, bear_case, thesis_still_valid, `action ∈ {hold, open, close, flip}`, target_direction, conviction).
- [x] **DebateAgent behavior:** "prefers **hold** when a held position's thesis stays valid" passes (continuity bias in the prompt; hold-first fixture); `sample(..., k)` returns K actions for self-consistency.
- [x] **Conviction math unit tests:** `composite_conviction` = w1·agreement + w2·mean_confidence + w3·memory_consistency (Σconf==0 guard → 0); `self_consistency_conviction(['open','open','open','hold','open'],5)` → 0.8; `raw_conviction` = α·raw + β·sc — all pure/deterministic.
- [x] **Gate:** `make check` green (ruff + mypy 23 files + 37 unit + e2e).
- [x] **features.json:** F08 → `passing`; F15 (Layer-3 calibration) stays `not_started` until Step 5.
- [x] **Rules:** LCEL `prompt | llm.with_structured_output(ResearchStance)`; model via `make_llm`; conviction is **MATH, not the LLM self-report** (stance `conviction` is one input only); `temperature=0` for `run`, `config.debate_temperature>0` only in `sample` (config-driven `K`); offline parity; no hardcoded `"AAPL"`; weights/`K`/`alpha`/`beta`/`debate_temperature` in config.
- [x] **Tracking:** `PROGRESS.md` updated; `ResearchStance` reordered reason-first; ADR-008 records sampling-temperature + hold-first-fixture choices.

## Post-completion amendments (first live run: the system never shorted)

The first full live backtest (2025–2026) never opened a short despite `allow_short=True`. Root cause was
two stacked filters in THIS sub-step, fixed here without changing the `ResearchStance` schema:

- [x] **Gate A — debate prompt (ADR-016, done):** `DEBATE_SYSTEM` lumped the bear case as "short/flat", so
  a bearish view collapsed to flat and `target_direction = -1` almost never surfaced. The prompt now makes
  Step 1/2 directional (RISE→LONG vs FALL→SHORT) and Step 4 maps a dominant bear case to `-1`, reserving
  `0` for genuine no-view ("SHORT and FLAT are different decisions"). Skeleton above updated to match the
  shipped prompt. *Behavioral change is **live-only** — MockLLM ignores prompt text — so a 1-day live smoke
  (bearish-consensus day → `-1`) is the verification, not an offline test.*
- [x] **Gate B — abstention-aware `agreement` (ADR-017, done):** the old `agreement = |Σ sᵢcᵢ| / Σ cᵢ`
  let a *flat* (abstaining) agent dilute a confident lone short below `tau_enter`. New formula
  `|Σ sᵢcᵢ| / Σ_{sᵢ≠0} cᵢ` sums confidence over directional agents only — a flat vote neither reinforces
  nor dilutes. Implemented in `composite_conviction`; unit test
  `test_composite_conviction_abstention_does_not_dilute_lone_short` asserts news-flat + technical-short →
  `agreement = 1.0` (was 0.545) and `z ≥ tau_enter`. `make check` green (84 unit + e2e). *The short
  frequency lift is best measured after S5.1 calibration re-scales `z`.*
