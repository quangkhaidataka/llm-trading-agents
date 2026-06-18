# Rule: Git Workflow

This folder is not yet a git repo (`git init` when ready). These rules apply once it is.

## Before every commit

- Run `make check` (lint + typecheck + test + e2e). A commit with a red `make check` is not allowed.
  The `PreToolUse` hook in `.claude/settings.json` runs it automatically on `git commit`.
- Confirm `.env`, `data/*.parquet`, `logs/`, and FAISS index files are not staged (see `.gitignore`).
- Update `PROGRESS.md` and, if a feature changed state, `features.json` (see the
  `update-progress` and `feature-status` skills).

## Commits

- Small, atomic commits aligned to the planner's atomic units — one logical change each.
- Imperative subject ≤ 72 chars; body explains *why*, not *what*. Reference the milestone (`M2`) and
  feature id (`F03`) when relevant.
- Record any non-obvious technical decision in `DECISIONS.md` (ADR style) in the same commit.

## Branches

- `main` stays green (`make check` passes at every commit).
- One branch per milestone or feature: `m2-agents`, `f04-macro-agent`. Never commit directly to
  `main` for multi-step work; branch first.

## Commit message footer

End commit messages created by Claude with:

```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

## Pull requests

- Open a PR only when the milestone's acceptance test passes. The PR body states which milestone/
  features it closes and pastes the `make check` evidence (the `verifier_agent` output).
- Never commit or push unless the user asks.
