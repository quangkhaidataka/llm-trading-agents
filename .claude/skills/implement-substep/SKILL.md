---
name: implement-substep
description: Implement one substep from the plan/ folder, after reading the full context first. Use whenever asked to implement/build/code a substep or step (e.g. "implement S11", "build substep S31", "do S42", "code step 2's analysts"). Reads PLAN.md + the substep plan + the relevant rules and stubs BEFORE writing code, then implements per the plan and verifies its Definition of Done. Trigger keywords - implement substep, implement S, build S, code the substep, do step, start S.
---

# Implement a Substep (read the full picture first)

The design is already decided in `plan/`. Realize it faithfully and simply. Follow these steps in order.

## Step 0 — Read for the full picture (BEFORE writing any code)

Read these, in order, so you understand how the substep fits the whole system:
1. **The substep plan** — `plan/S{i}_*/S{ij}_plan_*.md` for the requested id (Objective, Inputs/Outputs,
   Skeleton Python Code, How It Connects, Key Technology, **Definition of Done**).
2. **The matching step in `PLAN.md`** — the `### Step {i}: …` section, plus the top **Guiding
   principles** and the bottom **## Execution discipline**.
3. **Rules** (`.claude/rules/`): always `follow-the-plan.md`, `architecture.md`, `coding-style.md`,
   `testing-rules.md`. Add `llm-and-prompts.md` for any agent/LLM substep; add `security-rules.md` and
   run the `check-lookahead` skill for any data / memory / backtest substep.
4. **The code it touches** — the `src/…` stub files the substep names, plus `config.py` and
   `src/schemas.py` (use exact existing names/signatures; the plan's skeleton matches them).
5. **`features.json`** — the mapped `F` id and its `verification` command.

Do not start coding until you have read these. If a phrase in the plan is unclear, resolve it from the
spec (`project_description.md`) before guessing.

## Step 1 — Implement (follow the plan)

- Implement exactly the classes/functions/signatures from the substep's **Skeleton Python Code**, in the
  file paths it names. Fill the `...` bodies — do **not** add modules, layers, or abstractions the plan
  didn't ask for (`follow-the-plan.md`).
- Keep the plan's altitude: simple functions, the chosen libraries, **numbers only in `config.py`**,
  data only via `get_observation`, LLM only via `make_llm`, agents as `prompt |
  llm.with_structured_output(Schema)`. No new heavy dependency.
- Write the offline, deterministic tests the substep's Definition of Done names (write the test first
  when practical — see `test-driven-development`).

## Step 2 — Verify the Definition of Done (evidence before claims)

- Run the substep's **acceptance command** AND `make check` (lint + typecheck + test + e2e). Do not say
  "done" until you have seen them pass (`run-verification` / `verifier_agent`).
- For data/memory/backtest substeps, run the `check-lookahead` audit — a fix must never break
  point-in-time discipline or offline determinism.

## Step 3 — Record

- Flip the mapped `features.json` id to `passing` with evidence (commit hash / passing test); update
  `PROGRESS.md`; add a `DECISIONS.md` ADR for any non-obvious choice.

## If you hit errors

Follow `follow-the-plan.md`: debug the root cause, make the **smallest** fix that passes the DoD, keep
it as simple as the plan, and don't mess things up. If a fix genuinely requires deviating from the
plan, update the substep doc + `PLAN.md` and record an ADR **first**, then implement — code must never
silently diverge from the plan.
