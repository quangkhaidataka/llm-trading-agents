"""E2E smoke (M0) — the CLI entrypoint is wired and importable offline.

Runs `python -m src.main --help` in a subprocess and asserts it exits cleanly.
This is the minimal end-to-end check that the package + argparse load without the
heavy runtime stack (heavy imports are function-local).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.e2e
def test_cli_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()
    assert "--mode" in result.stdout
