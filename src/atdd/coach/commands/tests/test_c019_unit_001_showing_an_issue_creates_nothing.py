# URN: test:govern-lifecycle:read-verbs-are-side-effect-free:C019-UNIT-001-showing-an-issue-creates-nothing
# Acceptance: acc:govern-lifecycle:C019-UNIT-001-showing-an-issue-creates-nothing
# WMBT: wmbt:govern-lifecycle:C019
# Phase: RED
# Layer: application
"""C019-UNIT-001 — showing an issue must never reach branch/worktree creation.

`atdd coach issues <N>` is the READ verb, but it delegates to the entering path,
which creates when it cannot find a worktree. The read path must be able to say
"not here" without making it so.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue_lifecycle import IssueLifecycle


def _stub_lifecycle(monkeypatch, tmp_path: Path) -> IssueLifecycle:
    """An IssueLifecycle whose GitHub reads are stubbed to a RED-phase issue."""
    lc = IssueLifecycle()
    lc.target_dir = tmp_path / "somewhere-else"
    lc.target_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(lc, "_fetch_issue", lambda n: {
        "number": n, "title": "t", "labels": [{"name": "atdd:RED"}], "body": ""})
    monkeypatch.setattr(lc, "_resolve_wmbts", lambda n: [])
    monkeypatch.setattr(lc, "_get_slug_and_prefix", lambda issue: ("my-slug", "feat"))
    monkeypatch.setattr(lc, "_run_gate", lambda p: 0)
    monkeypatch.setattr(lc, "_print_context", lambda *a, **k: None)

    def _forbidden(*_a, **_k):
        raise AssertionError(
            "the read verb reached branch/worktree creation; showing an issue "
            "must not mutate the filesystem (#1708)"
        )
    monkeypatch.setattr(lc, "_create_branch", _forbidden)
    return lc


def test_showing_an_issue_never_creates(monkeypatch, tmp_path):
    lc = _stub_lifecycle(monkeypatch, tmp_path)

    rc = lc.enter(1708, create=False)

    assert rc == 0, "showing must still succeed and report, not merely refuse"


def test_entering_may_still_create(monkeypatch, tmp_path):
    """The handoff verb keeps its behaviour — #1708 scopes `enter` out."""
    lc = _stub_lifecycle(monkeypatch, tmp_path)
    called = {}
    monkeypatch.setattr(lc, "_create_branch",
                        lambda *a, **k: called.setdefault("hit", True) or tmp_path)

    lc.enter(1708, create=True)

    assert called.get("hit"), "entering must still be allowed to create"
