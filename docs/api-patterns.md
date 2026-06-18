# Agent / API Patterns

This project exposes no web API. "API patterns" here means the **internal agent contracts** and the
LangChain/LangGraph idioms every agent follows (spec §5, §12.2).

## The canonical agent

Every agent is an LCEL runnable built once and reused:

```python
chain = prompt | llm.with_structured_output(Schema)   # Schema from src/schemas.py
```

- `prompt` is a `ChatPromptTemplate` with a System message (role + constraints, parameterized by
  `{ticker}`, thresholds, …) and a Human message that injects the point-in-time data.
- `llm` comes only from `make_llm(config)` — never construct a model inline.
- Output is forced into a Pydantic schema. **Never** hand-parse JSON or read free text across an agent
  boundary.
- `temperature=0` for decision agents; the DebateAgent runs `config.K` times at `temperature>0` only
  for self-consistency conviction (spec §7.3).

## Agent contracts (input → output)

| Agent | Reads | Emits |
|---|---|---|
| NewsAgent | AAPL news (relevance-filtered) | `NewsSignal` |
| MacroAgent | macro news by topic + SPY trend | `MacroSignal` (also → PositionManager veto) |
| TechnicalAgent | precomputed indicators | `TechnicalSignal` |
| MemoryAgent | top-k closed FAISS episodes | `MemoryContext` |
| DebateAgent | the four signals + `PortfolioState` | `ResearchStance` |
| PositionManager | `ResearchStance` + `MacroSignal` + state + risk inputs | `TradeDecision` |

## Prompt conventions (spec §5)

- System defines role + hard constraints; always include the anti-leak line: "Do not use outside
  knowledge or anything you know about the future."
- Human injects only point-in-time data and the upstream schemas rendered as labeled text.
- TechnicalAgent: "Do not make up numbers; only interpret the provided indicators."
- DebateAgent: 4 steps — Bull case, Bear case, "is the thesis still valid?", action + conviction;
  prefer **hold** when a position is held and the thesis holds.

## Adding or changing an agent

1. Define/extend its schema in `src/schemas.py` (this is a protocol change — review it).
2. Subclass `BaseAgent`; implement `_build_chain` and `run`.
3. Wire it into `src/graph/build_graph.py`.
4. Add a schema-conformance test on a fixture day.
5. Make every new knob a `config.py` field, not a literal.

## Offline mode

When `config.offline=True`, `make_llm` returns `MockLLM`, which yields canned schema instances from
`fixtures/llm_responses.json`. Agents are written so they cannot tell which mode they are in — they
only ever see an `Observation` and produce a schema.
