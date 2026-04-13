"""
Unit tests for `atdd merge-cascade`.

SPEC-COACH-ORCH-0006: merge in order with update-branch → CI → merge loop.
SPEC-COACH-ORCH-0007: halt on conflict and report offending PR.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.merge_cascade import (
    MergeHalt,
    MergeResult,
    cascade,
    fetch_ci_status,
    update_branch,
    wait_for_ci,
)

pytestmark = [pytest.mark.platform]


def _gh_ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _gh_fail(stderr: str, returncode: int = 1) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        returncode=returncode, cmd=["gh"], output="", stderr=stderr
    )


# ---------------------------------------------------------------------------
# update_branch
# ---------------------------------------------------------------------------


def test_update_branch_success():
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(),
    ):
        result = update_branch(100)
    assert result.status == "merged"


def test_update_branch_conflict():
    err = _gh_fail("merge conflict in src/foo.py")
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        side_effect=err,
    ):
        result = update_branch(100)
    assert result.status == "conflict"
    assert "conflict" in result.detail.lower()


# ---------------------------------------------------------------------------
# fetch_ci_status
# ---------------------------------------------------------------------------


def test_fetch_ci_status_pass():
    json_out = '[{"state":"COMPLETED","name":"ci","conclusion":"SUCCESS"}]'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        state, _ = fetch_ci_status(1)
    assert state == "pass"


def test_fetch_ci_status_pending():
    json_out = '[{"state":"IN_PROGRESS","name":"ci","conclusion":""}]'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        state, _ = fetch_ci_status(1)
    assert state == "pending"


def test_fetch_ci_status_fail():
    json_out = '[{"state":"COMPLETED","name":"ci","conclusion":"FAILURE"}]'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        state, detail = fetch_ci_status(1)
    assert state == "fail"
    assert "ci" in detail


def test_fetch_ci_status_no_required_checks():
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        side_effect=_gh_fail("no required checks"),
    ):
        state, _ = fetch_ci_status(1)
    assert state == "pass"


# ---------------------------------------------------------------------------
# wait_for_ci
# ---------------------------------------------------------------------------


def test_wait_for_ci_passes_immediately():
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_ci_status",
        return_value=("pass", "ok"),
    ):
        r = wait_for_ci(1, poll_interval=0, timeout=5)
    assert r.status == "merged"


def test_wait_for_ci_fail_returns_ci_failed():
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_ci_status",
        return_value=("fail", "test_x failed"),
    ):
        r = wait_for_ci(1, poll_interval=0, timeout=5)
    assert r.status == "ci_failed"


def test_wait_for_ci_times_out():
    times = iter([0.0, 100.0, 200.0])
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_ci_status",
        return_value=("pending", "1 in progress"),
    ):
        r = wait_for_ci(
            1,
            poll_interval=0,
            timeout=50,
            sleep=lambda _: None,
            clock=lambda: next(times),
        )
    assert r.status == "timeout"


# ---------------------------------------------------------------------------
# cascade
# ---------------------------------------------------------------------------


def test_cascade_merges_in_order():
    with patch("atdd.coach.commands.merge_cascade.update_branch", return_value=MergeResult(pr=0, status="merged")), \
         patch("atdd.coach.commands.merge_cascade.wait_for_ci", return_value=MergeResult(pr=0, status="merged")), \
         patch("atdd.coach.commands.merge_cascade.merge_pr", return_value=MergeResult(pr=0, status="merged")):
        results = cascade([1, 2, 3], poll_interval=0, timeout=1, auto=True)
    assert [r.status for r in results] == ["merged", "merged", "merged"]


def test_cascade_halts_on_conflict():
    def update_side_effect(pr):
        if pr == 2:
            return MergeResult(pr=2, status="conflict", detail="merge conflict")
        return MergeResult(pr=pr, status="merged")

    with patch(
        "atdd.coach.commands.merge_cascade.update_branch",
        side_effect=update_side_effect,
    ), patch(
        "atdd.coach.commands.merge_cascade.wait_for_ci",
        return_value=MergeResult(pr=0, status="merged"),
    ), patch(
        "atdd.coach.commands.merge_cascade.merge_pr",
        return_value=MergeResult(pr=0, status="merged"),
    ):
        with pytest.raises(MergeHalt) as exc_info:
            cascade([1, 2, 3], poll_interval=0, timeout=1, auto=True)
    assert exc_info.value.result.pr == 2
    assert exc_info.value.result.status == "conflict"


def test_cascade_halts_on_ci_fail():
    with patch("atdd.coach.commands.merge_cascade.update_branch", return_value=MergeResult(pr=0, status="merged")), \
         patch(
             "atdd.coach.commands.merge_cascade.wait_for_ci",
             return_value=MergeResult(pr=1, status="ci_failed", detail="test_x"),
         ), patch(
             "atdd.coach.commands.merge_cascade.merge_pr",
             return_value=MergeResult(pr=0, status="merged"),
         ):
        with pytest.raises(MergeHalt) as exc_info:
            cascade([1], poll_interval=0, timeout=1, auto=True)
    assert exc_info.value.result.status == "ci_failed"
