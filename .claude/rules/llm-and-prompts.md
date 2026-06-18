# Rule: LLM & Prompt Protocol

Applies to `src/agents/*` and `src/llm.py`. This is the heart of the project — the contribution is
the A2A *prompt protocol*, not a trained model. Reference: spec §5, §7.3, §12.2. Patterns doc:
[`docs/api-patterns.md`](../../docs/api-patterns.md).

## The canonical agent

Every agent is an LCEL runnable, built once in `_build_chain`, reused in `run`:

```python
chain = prompt | llm.with_structured_output(Schema)   # Schema from src/schemas.py
```

- **Never hand-parse JSON** or pass raw dicts/free text across an agent boundary — output is always a
  validated Pydantic schema.
- The model comes **only** from `make_llm(config)`. Never construct `ChatGroq`/`ChatOpenAI` inline —
  the one factory is what makes the backbone swappable in a single line (spec §12.2, RQ4).

## Prompt structure (spec §5)

- **System** message: role + hard constraints, parameterized (`{ticker}`, thresholds, …) via
  `ChatPromptTemplate`. No hardcoded `"AAPL"`.
- **Human** message: injects only point-in-time data and the upstream schemas rendered as labeled
  text. Nothing the agent shouldn't see at day `t`.
- **Mandatory anti-leak line** in every agent's System prompt: *"Rely only on the provided data; do
  not use outside knowledge or anything you know about events after this date."*
- TechnicalAgent: *"Do not make up numbers; only interpret the provided indicators"* — numbers are
  computed deterministically in the data layer, never by the LLM.
- DebateAgent: the 4-step structure (Bull → Bear → "is the thesis still valid?" → action +
  conviction), and prefer **hold** when a position is held and its thesis holds.

## Temperature & conviction

- `temperature=0` (`config.temperature`) for all decision agents — reproducibility.
- The **only** exception: the DebateAgent is sampled `config.K` times at `temperature>0` for
  self-consistency conviction. This is explicit and config-driven, never ad hoc.
- The number that drives thresholds is **computed, not the LLM's self-report** (composite signals →
  self-consistency → isotonic/Platt calibration). See coding-style + spec §7.3. Treat any LLM
  `confidence` field as one input to the math, never as the final conviction.

## Never pull live or external data into an agent

- Agents read data **only** through `get_observation(ticker, t)`. They must **not** call any external
  data source directly: no `requests`, no SDK, and **no MCP tools** (e.g. the FMP `quote`/`news`/
  `statements`, Gmail, Drive tools that may be present in the session).
- Why this is a hard rule here: live data is *today's* data. Pulling it into a 2025 backtest day is
  catastrophic look-ahead leakage, breaks offline/deterministic runs, bypasses the point-in-time
  gate, and introduces an unpinned, non-reproducible source. See
  [`security-rules.md`](security-rules.md) and the `check-lookahead` skill.
- MCP/live tools are fine for *your own* exploration in chat (e.g. sanity-checking a number) — never
  inside `src/` pipeline code or tests.

## Offline / MockLLM parity (spec §13.6)

- An agent must behave identically whether `make_llm` returned `ChatGroq` or `MockLLM`. It only ever
  sees an `Observation` + schemas and emits a schema — **never branch on `config.offline` inside an
  agent**. The factory and loaders own that branch.
- Tests exercise agents with `MockLLM` (canned responses from `fixtures/llm_responses.json`). If an
  agent can't run offline, the design is wrong.

## Changing a schema is a protocol change

Editing `src/schemas.py` changes the A2A contract for every agent that touches it. Update the schema
(not an ad-hoc payload), add/adjust the conformance test, and have `reviewer_agent` review it.

## Caching (spec §6, §12.6)

LLM output is cached by `(ticker, date, agent)` so re-running ablations costs no new API calls. Cache
is keyed point-in-time; a cache hit must never surface a response generated with future data.
