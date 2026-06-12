# URN: test:spawn-agents:coach-spawn-respawn-reliability-primitives:E032-SMOKE-001-real-issue-advance-idempotent
# Acceptance: acc:spawn-agents:E032-SMOKE-001-real-issue-advance-idempotent
# WMBT: wmbt:spawn-agents:E032
# Phase: SMOKE
# Layer: assembly
# Smoke: true
# Purpose: Against a real GitHub issue the idempotent advance lands the target label once; a second call mutates nothing.
"""E032-SMOKE-001 — against a real GitHub issue the advance is idempotent: the
first call lands the target label and a second call changes nothing.

Live-on-demand against the REAL ``gh`` label API. Drives the real GREEN function
``advance_phase_label_idempotent`` with real gh read/swap callables against a
SCRATCH issue (``SMOKE_TEST_ISSUE``) — never the live worktree issue. Skips
cleanly when not opted in (``ATDD_LIVE_SMOKE=1`` + ``SMOKE_TEST_ISSUE``) or when
``gh`` is absent. No mocks — this is the real label REST API.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

pytestmark = [pytest.mark.smoke]

_PHASES = ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]


def _gh_read_phase(issue_number: int) -> str:
    out = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "labels"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    labels = [l["name"] for l in json.loads(out.stdout)["labels"]]
    for name in labels:
        if name.startswith("atdd:"):
            return name[len("atdd:"):]
    return ""


def _gh_swap_label(issue_number: int, target: str) -> None:
    for phase in _PHASES:
        subprocess.run(
            ["gh", "issue", "edit", str(issue_number), "--remove-label", f"atdd:{phase}"],
            capture_output=True, text=True, timeout=30,
        )
    subprocess.run(
        ["gh", "issue", "edit", str(issue_number), "--add-label", f"atdd:{target}"],
        capture_output=True, text=True, timeout=30, check=True,
    )


def test_real_issue_advance_idempotent():
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        pytest.skip("live gh smoke is opt-in: set ATDD_LIVE_SMOKE=1")
    scratch = os.environ.get("SMOKE_TEST_ISSUE")
    if not scratch:
        pytest.skip("set SMOKE_TEST_ISSUE=<scratch issue number> (never the live worktree issue)")
    if not shutil.which("gh"):
        pytest.skip("gh not on PATH")

    from atdd.coach.label_advance import advance_phase_label_idempotent

    issue = int(scratch)
    source = _gh_read_phase(issue)
    target = _PHASES[min(_PHASES.index(source) + 1, len(_PHASES) - 1)] if source in _PHASES else "PLANNED"

    first = advance_phase_label_idempotent(
        issue, source=source, target=target,
        read_phase=_gh_read_phase, swap_label=_gh_swap_label,
    )
    assert first.status == "advanced"
    assert _gh_read_phase(issue) == target, "first call must land exactly the target label"

    second = advance_phase_label_idempotent(
        issue, source=source, target=target,
        read_phase=_gh_read_phase, swap_label=_gh_swap_label,
    )
    assert second.status == "noop", "second call must be a no-op (already at target)"
    assert _gh_read_phase(issue) == target, "label set unchanged after the second call"
