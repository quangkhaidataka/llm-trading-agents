# Decision Log (ADR)

Architecture/technical decisions, newest first. One entry per non-obvious choice. Append via the
`doc_agent` / in the same commit as the change. Use absolute dates.

Template:

```
## ADR-NNN · <short title>
- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | superseded by ADR-MMM
- **Decision:** what we chose.
- **Reason:** why — the forces that drove it.
- **Rejected alternatives:** what else was considered and why not.
- **Consequences:** follow-on effects, risks, what this commits us to.
```

---

## ADR-001 · Project-local `.venv`; split dev vs full runtime
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** `make setup` creates a project-local `.venv` and installs only dev tooling +
  minimal runtime (`requirements-dev.txt`). The heavy stack (langchain, faiss, vectorbt, ta,
  sentence-transformers) lives in `requirements.txt`, installed separately by `make setup-full`.
- **Reason:** The scaffold (M0) imports none of the heavy stack — its imports are function-local — so
  `make check` must not depend on a slow/fragile build. Isolating in `.venv` protects the user's
  existing conda env (`finrl_env`) from accidental dependency downgrades (e.g. numpy).
- **Rejected alternatives:** (a) one `requirements.txt` installed by `make setup` — slow, risks
  breaking the scaffold gate and the user's env; (b) installing into the active conda env — could
  downgrade numpy 2.2 for vectorbt/numba and corrupt unrelated work.
- **Consequences:** Contributors run `make setup-full` before M1+ work that actually executes the
  pipeline. vectorbt ↔ numpy 2.x compatibility must be validated then.

## ADR-000 · `make check` is the single source of truth
- **Date:** 2026-06-18
- **Status:** accepted
- **Decision:** "Is the code OK?" is answered only by `make check` (= lint + typecheck + test + e2e).
  No other ad-hoc judgement counts; `features.json` evidence and commits cite it.
- **Reason:** A single, executable, reproducible gate removes ambiguity and lets the verifier_agent /
  CI / hooks all agree. Aligns with spec §13's evidence-first DoD.
- **Rejected alternatives:** Per-tool manual checks (drift, inconsistent); trusting agent self-reports
  (not reproducible).
- **Consequences:** Every feature needs an executable verification; the pre-commit hook runs the gate.
