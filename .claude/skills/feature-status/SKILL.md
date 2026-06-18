---
name: feature-status
description: Read or write features.json — the machine-readable feature list with state (not_started/active/blocked/passing) and evidence. Use to check what is built, mark a feature active/blocked/passing, or attach evidence after verification. Trigger keywords - feature status, features.json, mark feature, what's done, feature list, set state.
---

# Feature Status

`features.json` is the machine-readable source of truth for what behavior exists and how it is
proven. Each feature: `id`, `behavior`, `verification` (an executable command), `state`, `evidence`.

## Reading

- To answer "what's done / what's left", parse `features.json` and group by `state`.
- A feature is only `passing` if its `verification` command currently succeeds.

## Writing (state transitions)

Valid states: `not_started` → `active` → `passing`, with `blocked` as a side state.

1. Set `active` when work starts on the feature.
2. Set `blocked` with a note in `PROGRESS.md` when it cannot proceed.
3. Set `passing` ONLY after running the feature's `verification` command and seeing it pass — then
   set `evidence` to the commit hash or log reference that proves it. Never set `passing` without
   evidence (delegate the run to `run-verification` / `verifier_agent`).

## Rules

- Keep the JSON valid (it is consumed programmatically) — verify it parses after editing.
- One feature = one user-facing behavior with one executable verification. Do not invent features
  not in `project_description.md`; add new ones only when the spec/plan introduces them.
- Keep `features.json`, `PROGRESS.md`, and reality in sync — update all three together via the
  `update-progress` skill at session end.
