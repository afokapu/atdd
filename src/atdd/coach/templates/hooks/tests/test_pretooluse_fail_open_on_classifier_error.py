# URN: test:integration-hardening:coach-single-command-driver:pretooluse-fails-open-on-classifier-error
# Issue: #1454 (wire the PreToolUse prohibition guard)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""The PreToolUse hook must FAIL OPEN when the classifier errors (#1454).

``test_pretooluse_classifier_integration`` already proves the hook fails open
when the classifier is *absent*.  This module covers the other half of
Decision 6 (issue #668): a classifier that is *present but broken* must never
brick the agent.  A guard that hard-fails on its own bug is worse than no
guard — it makes every tool call unrunnable.

Both failure shapes are covered:
  * the classifier raises (non-zero exit)      → hook allows
  * the classifier emits garbage on stdout     → hook allows

In both cases the command under test is ``gh issue create`` — the very command
the guard exists to block — so a hook that blocked for the *wrong* reason
(e.g. by defaulting to "block" on error) would be caught here.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src/atdd/coach/templates/hooks/claude-pre-tool-use.sh"

_CLASSIFIER_RELPATH = "src/atdd/coach/utils/forbidden_command_classifier.py"


def _init_tmp_repo(path: Path) -> None:
    """Initialise a minimal git repo at *path* (so git rev-parse resolves)."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )


def _plant_classifier(repo_root: Path, body: str) -> None:
    """Write a stub classifier at the path the hook resolves."""
    classifier = repo_root / _CLASSIFIER_RELPATH
    classifier.parent.mkdir(parents=True, exist_ok=True)
    classifier.write_text(body)


def _run_hook(repo_root: Path, command: str) -> subprocess.CompletedProcess:
    """Run the hook with *command* as the Bash payload, rooted at *repo_root*."""
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}
    ).encode()
    env = {**os.environ, "ATDD_REPO_ROOT": str(repo_root), "CI": "false"}
    return subprocess.run(
        ["sh", str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        cwd=str(repo_root),
        env=env,
    )


def test_hook_fails_open_when_classifier_raises(tmp_path: Path) -> None:
    """A classifier that crashes must not block the tool call."""
    _init_tmp_repo(tmp_path)
    _plant_classifier(tmp_path, 'raise RuntimeError("classifier is broken")\n')

    result = _run_hook(tmp_path, "gh issue create --title x")

    assert result.returncode == 0, (
        "a crashing classifier bricked the agent — the hook must fail open.\n"
        f"exit={result.returncode} stderr={result.stderr.decode()!r}"
    )


def test_hook_fails_open_when_classifier_emits_garbage(tmp_path: Path) -> None:
    """A classifier that exits 0 with unparseable stdout must not block."""
    _init_tmp_repo(tmp_path)
    _plant_classifier(tmp_path, 'print("!!! not a verdict !!!")\n')

    result = _run_hook(tmp_path, "gh issue create --title x")

    assert result.returncode == 0, (
        "garbage classifier output must be treated as 'allow' (fail open).\n"
        f"exit={result.returncode} stderr={result.stderr.decode()!r}"
    )
