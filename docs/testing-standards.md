# Testing Standards

Rule form: [`.claude/rules/testing-rules.md`](../.claude/rules/testing-rules.md). `make check` is the
single source of truth for "is the code OK".

## Principles

1. **Offline & deterministic.** Every test runs with `Config(offline=True)` → `MockLLM` + `fixtures/`.
   No network, no API keys, no real LLM, no randomness without a fixed seed.
2. **Behavior over implementation.** Assert observable behavior (schema returned, position
   transition, fee charged), not internal call sequences.
3. **The no-lookahead test is sacred.** `tests/test_no_lookahead.py` must stay green and strong;
   never weaken it to pass other work.

## Test tiers

| Tier | Marker | Run by | Scope |
|---|---|---|---|
| Unit | (none) | `make test` | one module/function, fast |
| E2E / smoke | `@pytest.mark.e2e` | `make e2e` | CLI + pipeline wiring offline |

Markers are registered in `pyproject.toml`; `make test` excludes `e2e`, `make e2e` selects it.

## Fixtures (spec §13.6)

`fixtures/` holds small committed samples: `AAPL_news_sample.json`, `macro_news_sample.json`,
`prices_sample.csv`, `llm_responses.json`. Keep them tiny and fixed — they define the deterministic
world the tests live in. Add to them rather than mocking ad hoc.

## Per-milestone acceptance (spec §13.2)

- **M1** — `test_no_lookahead` green; one observation prints.
- **M2** — each agent returns its correct Pydantic schema on one fixture day.
- **M3** — one day yields a `TradeDecision`; memory write/read is point-in-time (delayed `h`).
- **M4** — equity curve + metrics; **PnL net of fees**; execution at `t+1`.
- **M5** — ablation comparison table + conviction reliability diagram.

## Using `xfail`

A not-yet-built feature's acceptance test may be `@pytest.mark.xfail(strict=False, reason="Mx ...")`
so `make check` stays green during scaffolding. When the feature lands, **remove the xfail** — a
silently-xfailing test that should pass is a defect the reviewer must flag.

## Writing tests

- One test file per module: `tests/test_<module>.py`.
- Name by behavior: `test_open_requires_conviction_above_tau_enter`.
- Sanity-check strength: would this test fail if the behavior were mutated? If not, it is too weak.
