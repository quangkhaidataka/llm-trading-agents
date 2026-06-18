---
name: update-progress
description: Update PROGRESS.md at session end (or after a milestone lands) to reflect Current State, Completed, In Progress, Blocked, Known Issues, and Next Steps. Use when wrapping up a session, after finishing work, or when asked to record progress / hand off. Trigger keywords - update progress, session end, wrap up, handoff, what's next, progress.md.
---

# Update Progress

Keep `PROGRESS.md` an accurate, current snapshot so the next session resumes instantly.

## Steps

1. Read `PROGRESS.md`, `features.json`, and the recent diff / what was done this session.
2. Verify before claiming done — only mark something Completed if `make check` (or the feature's
   verification command) actually passed this session. If unverified, put it under In Progress with a
   note.
3. Update each section:
   - **Current State** — one paragraph: which milestone, what runs today.
   - **Completed** — append finished units/features with their evidence (commit hash / passing test).
   - **In Progress** — what is mid-flight and the next concrete step for it.
   - **Blocked** — blockers with the reason and what would unblock.
   - **Known Issues** — bugs/limitations not yet addressed.
   - **Next Steps** — the ordered next units (from `planner_agent`), most important first.
4. Use absolute dates (e.g. 2026-06-18), not "today".

## Rules

- Do not invent progress. Mirror `features.json` state; never list a feature as Completed that
  `features.json` marks below `passing`.
- Keep it skimmable — bullets, not prose dumps. Move detail to `DECISIONS.md` if it's a rationale.
- This skill edits docs only; it does not change code or run the verifier (call `run-verification`
  first if a claim needs evidence).
