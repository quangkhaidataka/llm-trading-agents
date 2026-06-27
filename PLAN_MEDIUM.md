# PLAN_MEDIUM.md — Outline for the Medium article

> **Goal:** a Medium article for **practitioners** (ML/agent engineers, quant-curious devs) that explains
> *what* the system is and, above all, *why it is designed the way it is* — so the reader comes away
> understanding the **intelligence of the design**, not just the result. Tone: clear, concrete, no hype,
> easy to follow. Emphasize the good parts. Report the result **through 2026-05-01** (Jan 2025 → 1 May 2026,
> 333 sessions).
>
> **The through-line (repeat it):** *the LLM only supplies a direction and a reason; every number that moves
> money is computed.* That single idea is what makes an LLM trustworthy enough to manage a position.

---

## Section map

### 0. Title + one-line hook
- Working title: **"I Gave Six LLM Agents $1M and a Strict Rule: You Only Get to Argue, the Math Decides."**
- Subtitle: a frozen Llama-3.3-70B reading AAPL news that beat buy-&-hold with **half the drawdown** —
  and can tell you *why* it did every single trade.
- **Message:** intrigue + the core design idea in one breath.

### 1. The reframe: this is position management, not price prediction
- Most "LLM trading" demos ask "will it go up tomorrow?" — a daily coin-flip classifier. That's the wrong
  problem: it churns, it has no memory of *why* it's in a trade, and it can't be held accountable.
- Our problem: **manage a position.** Output is an *action* — hold / open / close / flip → target ∈ {−1,0,+1}
  — relative to what you already hold and the thesis you entered on. You stay in a trade until the **thesis**
  that put you there is invalidated.
- **Why it matters to a practitioner:** state-aware = low turnover, explainable, testable.

### 2. Why naive LLM trading fails (the three traps we designed against)
- **Overconfidence:** ask an LLM "how sure are you?" and the number is noise. → we *compute* conviction.
- **Free text is untestable:** if agents chat in prose, you can't unit-test or ablate the reasoning.
  → a **typed protocol** (Pydantic schemas) between agents.
- **Look-ahead leakage:** the silent killer of every backtest. → one point-in-time data gate + a model with a
  **Dec-2023 knowledge cutoff** testing on 2025–2026.
- **Message:** the design is a list of answers to concrete failure modes.

### 3. The architecture — an org chart of specialists (the A2A protocol)
- Diagram in words: `get_observation(t)` → News / Macro / Technical / Memory analysts → Debate (Bull vs Bear)
  → PositionManager → TradeDecision → (5 days later) write a memory.
- **Agents speak only through fixed schemas, never free text** — this is the core contribution. A message is
  a `NewsSignal`, a `ResearchStance`, a `TradeDecision`. Show one tiny schema.
- **Two separate news channels** (a deliberate design point): idiosyncratic AAPL news (relevance-filtered)
  vs. macro-by-topic (never filtered, routes to the risk veto). Explain *why* mixing them is a mistake.
- **Why it's intelligent:** typed messages make the whole debate **inspectable, testable, and ablatable** —
  you can delete one agent and measure the damage.

### 4. The cleverest part: conviction is computed, not confessed
- The naive way (ask the model) vs. our 3-layer pipeline:
  1. **Composite** of measurable signals: agreement (abstention-aware), mean confidence, memory consistency.
  2. **Self-consistency:** run the debate K times at temperature > 0; conviction = how often it agrees with
     itself.
  3. **Calibration:** map the raw score to a real probability with isotonic regression fit on 2022–2024.
- **The money chart / finding:** raw LLM direction calls are a **coin flip (~47% right)**, but the *computed*
  conviction **sorts** them — 0.64 conviction → 64% right, 0.73 → 73% (monotonic; Brier 0.327 → 0.245).
  Reliability diagram. **This is the headline intellectual result:** the edge isn't in the LLM's opinion,
  it's in *knowing when to believe it*.

### 5. Memory: learning without training
- A FAISS bank of `(situation → action → outcome)` episodes. The LLM is **frozen** — "learning" lives in the
  retrieved experience, not in weights. RQ: can a non-parametric memory add alpha without fine-tuning?
- **Delayed write (the subtle anti-leak):** an episode for day *t* only becomes searchable at *t+1+h* (h=5),
  once its outcome is known. Writing earlier = leaking the future into the past.
- Reward = **drift-demeaned** forward return (why not SPY-adjusted — one sentence).
- **Why it's intelligent:** the system accumulates experience cheaply and point-in-time-correctly.

### 6. Turning an opinion into a position: hysteresis + a risk veto
- The PositionManager is **deterministic on purpose** — the LLM decides *direction*, math decides *sizing and
  timing*. Clean separation = no LLM hallucinating position sizes.
- **Asymmetric hysteresis (a Schmitt trigger):** enter only at high conviction (τ_enter), exit only when it
  decays past a *lower* bar (τ_exit), flip only at a *higher* bar (τ_flip). The dead-band is what kills
  turnover — explain the analogy (a thermostat that doesn't flap).
- **Risk veto first:** volatility / drawdown / macro risk-off / analyst-disagreement can force flat, overriding
  any signal. Risk control is separated from alpha.

### 7. Credibility: the anti-look-ahead obsession
- One `get_observation(ticker, t)` gate returns only data ≤ t; execution at t+1; memory delayed; warm-up PnL
  never reported; a model whose knowledge ends Dec-2023 so it *cannot* have memorized 2025.
- A dedicated test (`test_no_lookahead`) is part of the build gate.
- **Message to practitioners:** this is the difference between a real backtest and a fantasy.

### 8. The result (through 1 May 2026)
- Metrics table: Strategy vs Buy-&-Hold AAPL.
  - Return **+21.3% vs +15.5%**, Sharpe **1.16 vs 0.42**, Max Drawdown **−14.0% vs −30.7%**, 38 trades,
    ~7-day average hold, flat 61% of the time.
- **The story:** it beat the benchmark on return *and* on risk — nearly **3× the Sharpe** and **less than half
  the drawdown** — by being in the market only when conviction earned it. Equity-curve figure.
- Honest one-liner: ~16 months is one regime; the value shown is the *behavior* (selective, low-turnover,
  risk-aware), and that behavior is what the design was built to produce.

### 9. It's a glass box: click any day and ask "why?"
- The explainability report (`results/report.html`): a clickable equity curve; click a day → see the news it
  read, every analyst's call + rationale, the bull/bear debate, the conviction, the final decision + reason.
- **Why it matters:** for a practitioner, an agent you can interrogate per-decision is the difference between a
  demo and something you'd deploy.

### 10. What I'd tell another practitioner (takeaways) + honest limits
- 5 transferable lessons:
  1. Make agents speak in **schemas**, not prose.
  2. **Compute** confidence; never trust a self-reported number.
  3. Separate **direction (LLM)** from **sizing/risk (deterministic)**.
  4. Treat **anti-look-ahead as a first-class invariant**, with a test.
  5. Build the **explainability view early** — it's also your debugger.
- Limits (brief, honest): single asset, one regime, endpoint chosen for the report, calibration is in-sample
  on the warm-up, shorts didn't fire in this window.
- Close: the point isn't "LLMs can trade" — it's a **discipline for turning an unreliable reasoner into a
  reliable system.**

---

## Style / production notes
- ~2,500–3,500 words. Short paragraphs. Bold the key idea in each section.
- 3 figures to reference: equity curve (`equity_curve_tau05online_thru01May2026.png`), reliability diagram
  (`reliability_diagram.png`), a screenshot of the report panel.
- One small code/schema snippet (a Pydantic schema) — just enough to make "typed protocol" concrete.
- Keep finance jargon defined inline (Sharpe, drawdown, hysteresis) — audience is practitioners, not quants.
- Numbers must match `results/metrics_tau05online_thru01May2026.json` exactly.
