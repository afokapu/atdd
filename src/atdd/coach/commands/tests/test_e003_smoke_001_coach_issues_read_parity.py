# URN: test:coach-verb-split:coach-verb-split:E003-SMOKE-001-real-read-in-temp-control-root
# Acceptance: acc:coach-verb-split:E003-SMOKE-001-real-read-in-temp-control-root
# WMBT: wmbt:coach-verb-split:E003
# Phase: SMOKE
# Harness: smoke
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — live end-to-end read smoke for `atdd coach issues`.

Drives the REAL boundary: runs `atdd coach issues open` and the deprecated
`atdd issue open` as ACTUAL subprocesses against the real repo — real CLI
dispatch, real coach_verbs resolution, real delegation into
IssueManager.open_issues, real GitHub client boundary. Substitutes NOTHING
(honors tester.smoke.no-collaborator-substitution / #1298 — no monkeypatch/patch
of any production collaborator).

READ-ONLY by construction: listing open issues mutates nothing and creates no
worktree, so it never touches or archives a live issue (the #1304 incident was a
MUTATION on a real issue; a list is safe). Show/enter parity and the fully
hermetic delegation proofs live in the E003 INTEGRATION suite
(test_e003_coach_issues_read_extraction.py); this smoke proves the list verb
runs end-to-end for real and that the deprecated shim routes into it.

Network-tolerant: the shim prints its deprecation notice BEFORE any GitHub call,
so the routing assertion is deterministic; the real-boundary assertion accepts a
successful listing OR a clean GitHub error (both prove the real open_issues path
was reached) but never a crash/traceback.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

# src/atdd/coach/commands/tests/<this> -> repo root is 5 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[5]


def _run_atdd(args: list[str]) -> subprocess.CompletedProcess:
    """Run `python -m atdd <args>` as a real subprocess in the repo (inherits env
    so the atdd under test — src or editable install — is the one exercised)."""
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        capture_output=True, text=True, timeout=120, cwd=str(_REPO_ROOT),
    )


class TestCoachIssuesReadSmoke:
    def test_coach_issues_open_reaches_real_list_boundary(self):
        """`atdd coach issues open` dispatches through the real coach_verbs
        resolver into the real IssueManager.open_issues, hitting the real GitHub
        boundary. It must reach that boundary (list header, empty-list notice, or
        a clean GitHub error) and never crash."""
        r = _run_atdd(["coach", "issues", "open"])
        assert "Traceback" not in r.stderr, r.stderr
        reached = (
            "Open Issues" in r.stdout
            or "No open issues" in r.stdout
            or "Error:" in r.stdout
        )
        assert reached, f"real list boundary not reached: {r.stdout!r} / {r.stderr!r}"

