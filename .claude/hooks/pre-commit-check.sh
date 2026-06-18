#!/usr/bin/env bash
# PreToolUse hook: when a Bash tool call is a `git commit`, run `make check`
# first and BLOCK the commit (exit 2) if the gate is red. Other Bash calls pass
# through untouched. Reads the tool-call JSON from stdin (Claude Code hook API).
set -uo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)"

case "$cmd" in
  *"git commit"*)
    echo "[pre-commit] running 'make check' before commit..." >&2
    if make check >/tmp/llmta_precommit.log 2>&1; then
      echo "[pre-commit] make check passed." >&2
      exit 0
    else
      echo "[pre-commit] make check FAILED — commit blocked. Tail of output:" >&2
      tail -n 40 /tmp/llmta_precommit.log >&2
      exit 2
    fi
    ;;
  *)
    exit 0
    ;;
esac
