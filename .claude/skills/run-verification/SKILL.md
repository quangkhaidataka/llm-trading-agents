---
name: run-verification
description: Orchestrate the full verify pipeline (make check = lint + typecheck + test + e2e) and report pass/fail with evidence. Use when asked to verify, validate, confirm the build, check if code is OK, before commits, or before marking a milestone/feature done. Trigger keywords - verify, validate, make check, is it green, ready to commit, done.
---

# Run Verification

`make check` is the single source of truth for "is the code OK" (lint + typecheck + test + e2e).

## Steps

1. Ensure deps are present: if `make check` fails on a missing tool, run `make setup` first.
2. Run the gate:
   ```bash
   make check
   ```
3. If it fails, attribute the failure by running the sub-targets individually:
   ```bash
   make lint
   make typecheck
   make test
   make e2e
   ```
4. For a specific feature, also run its `verification` command from `features.json`.

## Reporting (evidence-first)

- Lead with **PASS** or **FAIL**.
- Paste the actual summary/error lines you saw — never assert a result without its output.
- On FAIL: name the first failing target and the exact error; do not over-speculate on fixes.
- On PASS: cite evidence (`N passed`, `All checks passed`) and the commit hash if a feature's
  `evidence` field needs updating.

## Rules

- Never edit source to force a pass — report the failure instead.
- Prefer delegating the actual run to `verifier_agent` when in a multi-agent flow; this skill defines
  the procedure either way.
- After a PASS that closes a feature, hand off to the `feature-status` and `update-progress` skills.
