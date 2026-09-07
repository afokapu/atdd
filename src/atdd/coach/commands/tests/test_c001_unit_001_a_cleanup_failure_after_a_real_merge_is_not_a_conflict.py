# URN: test:coach-ops:merge-outcome-classification:C001-UNIT-001-a-cleanup-failure-after-a-real-merge-is-not-a-conflict
# Acceptance: acc:coach-ops:C001-UNIT-001-a-cleanup-failure-after-a-real-merge-is-not-a-conflict
# WMBT: wmbt:coach-ops:C001
# Phase: RED
# Layer: application
"""C001-UNIT-001 — classify from the pull request, not from the exit code.

`gh pr merge --squash --delete-branch` merges and THEN deletes the branch. The
deletion fails while a worktree still holds it — the state this repo mandates —
so the command exits non-zero on a merge that succeeded, and every non-zero exit
was being called a conflict.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.commands import merge_cascade as mc

_CLEANUP_STDERR = (
    "failed to run git: fatal: 'main' is already used by worktree at "
    "'/Users/x/Github/atdd/main'"
)


def _raise_cleanup_failure(*_a, **_k):
    raise subprocess.CalledProcessError(
        returncode=1, cmd=["gh", "pr", "merge"], stderr=_CLEANUP_STDERR
    )


def test_a_merge_that_landed_is_reported_merged(monkeypatch):
    monkeypatch.setattr(mc, "_run_gh", _raise_cleanup_failure)
    monkeypatch.setattr(mc, "_pr_is_merged", lambda pr: True)

    result = mc.merge_pr(1792)

    assert result.status == "merged", (
        "the pull request merged; only the branch cleanup failed. Reporting a "
        f"conflict halts the wave on work that landed. got: {result.status} — "
        f"{result.detail}"
    )


def test_the_cleanup_failure_is_still_surfaced(monkeypatch):
    """Not silently swallowed — a branch left behind must still be visible."""
    monkeypatch.setattr(mc, "_run_gh", _raise_cleanup_failure)
    monkeypatch.setattr(mc, "_pr_is_merged", lambda pr: True)

    result = mc.merge_pr(1792)

    assert "cleanup" in result.detail.lower() or "worktree" in result.detail.lower(), (
        f"the cleanup failure must remain reportable: {result.detail!r}"
    )


def test_a_merge_that_did_not_land_is_still_a_conflict(monkeypatch):
    """The guard: a genuine merge failure must keep halting the wave."""
    monkeypatch.setattr(mc, "_run_gh", _raise_cleanup_failure)
    monkeypatch.setattr(mc, "_pr_is_merged", lambda pr: False)

    result = mc.merge_pr(1792)

    assert result.status == "conflict", (
        f"an unmerged pull request must still halt the cascade; got {result.status}"
    )


def test_the_happy_path_is_unchanged(monkeypatch):
    monkeypatch.setattr(mc, "_run_gh", lambda *a, **k: None)
    result = mc.merge_pr(1792)
    assert result.status == "merged" and result.detail == "squash-merged"


# --- the probe itself -------------------------------------------------------
# The tests above monkeypatch `_pr_is_merged`, so they never execute it. That
# gap let a NameError through on first write (the module had no `logger`), so
# these drive the real function.

class _Proc:
    def __init__(self, stdout): self.stdout = stdout


def test_probe_reads_merged_from_gh(monkeypatch):
    monkeypatch.setattr(mc, "_run_gh", lambda *a, **k: _Proc('{"state": "MERGED"}'))
    assert mc._pr_is_merged(1792) is True


def test_probe_reports_open_as_not_merged(monkeypatch):
    monkeypatch.setattr(mc, "_run_gh", lambda *a, **k: _Proc('{"state": "OPEN"}'))
    assert mc._pr_is_merged(1792) is False


@pytest.mark.parametrize("stdout", ["", "not json", '{"nope": 1}', None])
def test_probe_fails_closed_on_an_unusable_answer(monkeypatch, stdout):
    """Unanswerable must mean 'not merged', keeping the old halting behaviour."""
    monkeypatch.setattr(mc, "_run_gh", lambda *a, **k: _Proc(stdout))
    assert mc._pr_is_merged(1792) is False


def test_probe_fails_closed_when_gh_itself_fails(monkeypatch, caplog):
    monkeypatch.setattr(mc, "_run_gh", _raise_cleanup_failure)
    import logging as _logging
    with caplog.at_level(_logging.WARNING):
        assert mc._pr_is_merged(1792) is False
    assert caplog.records, "the probe failure must be reported, not swallowed"
