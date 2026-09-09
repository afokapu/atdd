# URN: test:govern-lifecycle:govern-lifecycle:R011-SMOKE-001-the-real-cli-answers-in-both-forms
# Acceptance: acc:govern-lifecycle:R011-SMOKE-001-the-real-cli-answers-in-both-forms
# WMBT: wmbt:govern-lifecycle:R011
# Phase: SMOKE
# Layer: application
"""R011-SMOKE-001 — through the real CLI, which is where the NameError reached an operator.

`cli.py:2505` is the only caller that selects the JSON branch. A class-level call
can reach it, but only the CLI actually routes there, so this drives argv through
the real parser in a subprocess.

Runs the BRANCH's source, not whatever `atdd` is on PATH — a pipx-installed
binary would happily report a pass for code this branch does not contain.
"""
from __future__ import annotations

import json as json_module
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo


def _run(args: list[str], repo_root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(repo_root), env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.coder
@pytest.mark.platform
def test_atdd_gate_answers_in_both_forms():
    if not is_atdd_source_repo():
        pytest.skip("drives this repository's own CLI from source")

    repo_root = Path(find_repo_root())

    human = _run(["gate"], repo_root)
    assert human.returncode == 0, f"`atdd gate` failed:\n{human.stderr[-1500:]}"
    assert "Traceback" not in human.stderr

    js = _run(["gate", "--json"], repo_root)
    assert js.returncode == 0, f"`atdd gate --json` failed:\n{js.stderr[-1500:]}"
    assert "NameError" not in js.stderr, (
        "this is the defect: the JSON form raised NameError from cli.py"
    )

    # stdout may carry an upgrade banner ahead of the payload; take the JSON object.
    start = js.stdout.find("{")
    assert start != -1, f"no JSON object in stdout:\n{js.stdout[-800:]}"
    payload = json_module.loads(js.stdout[start:])

    assert "constraints" in payload and "diagnostic_commands" in payload, (
        f"the diagnostic payload a consumer reads is incomplete: {sorted(payload)}"
    )
    assert "files" not in payload, "the retired projection must not come back"
