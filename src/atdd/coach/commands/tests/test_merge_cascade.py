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
    fetch_pr_files,
    run,
    update_branch,
    wait_for_ci,
)
from atdd.coach.commands.merge_cascade_topology import MergeCascadeCycleError

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


# Payloads below carry `bucket`, which is what `gh pr checks --json` actually
# returns. They used to carry `conclusion` — a field gh does not serve on this
# command — so they asserted the old verdict against data no real gh produces
# and stayed green throughout #1612. See acc:coach-ops:M003-UNIT-001.


def test_fetch_ci_status_pass():
    json_out = '[{"state":"SUCCESS","name":"ci","bucket":"pass"}]'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        state, _ = fetch_ci_status(1)
    assert state == "pass"


def test_fetch_ci_status_pending():
    json_out = '[{"state":"IN_PROGRESS","name":"ci","bucket":"pending"}]'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        state, _ = fetch_ci_status(1)
    assert state == "pending"


def test_fetch_ci_status_fail():
    json_out = '[{"state":"FAILURE","name":"ci","bucket":"fail"}]'
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


# ---------------------------------------------------------------------------
# fetch_pr_files
# ---------------------------------------------------------------------------


def test_fetch_pr_files_parses_gh_json():
    json_out = '{"files":[{"path":"pyproject.toml"},{"path":"src/foo.py"}]}'
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        return_value=_gh_ok(json_out),
    ):
        files = fetch_pr_files(123)
    assert files == {"pyproject.toml", "src/foo.py"}


def test_fetch_pr_files_returns_empty_on_error():
    with patch(
        "atdd.coach.commands.merge_cascade._run_gh",
        side_effect=_gh_fail("not found"),
    ):
        files = fetch_pr_files(123)
    assert files == set()


# ---------------------------------------------------------------------------
# run() — dry-run path
# ---------------------------------------------------------------------------


def test_run_dry_run_prints_topological_order(capsys):
    """Dry-run should print PRs in topological order, not input order."""
    diffs = {
        350: {"pyproject.toml"},
        351: {"pyproject.toml"},
        352: {"pyproject.toml"},
        353: {"pyproject.toml"},
    }
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_pr_files",
        side_effect=lambda pr: diffs[pr],
    ):
        rc = run([353, 351, 350, 352], dry_run=True)
    assert rc == 0
    out = capsys.readouterr().out
    # Topo order is 350, 351, 352, 353 — find them in that sequence
    pos = [out.index(f"#{pr}") for pr in (350, 351, 352, 353)]
    assert pos == sorted(pos), f"PRs not in ascending topo order: {out}"


def test_run_dry_run_includes_rebase_hints_for_overlap(capsys):
    diffs = {
        300: {"pyproject.toml"},
        301: {"pyproject.toml"},
    }
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_pr_files",
        side_effect=lambda pr: diffs[pr],
    ):
        run([300, 301], dry_run=True)
    out = capsys.readouterr().out
    assert "rebase" in out.lower()
    assert "pyproject.toml" in out


def test_run_dry_run_no_hint_when_disjoint(capsys):
    diffs = {
        300: {"a.py"},
        301: {"b.py"},
    }
    with patch(
        "atdd.coach.commands.merge_cascade.fetch_pr_files",
        side_effect=lambda pr: diffs[pr],
    ):
        run([300, 301], dry_run=True)
    out = capsys.readouterr().out
    assert "no deps" in out.lower() or "independent" in out.lower()


# ---------------------------------------------------------------------------
# run() — cycle detection
# ---------------------------------------------------------------------------


def test_run_dry_run_reports_cycle_and_exits_nonzero(capsys):
    """When the helper raises MergeCascadeCycleError, run() exits 1."""
    def boom(pr_numbers, fetch_diff, extra_deps=None):
        raise MergeCascadeCycleError([1, 2, 1])

    with patch(
        "atdd.coach.commands.merge_cascade.compute_merge_order",
        side_effect=boom,
    ), patch(
        "atdd.coach.commands.merge_cascade.fetch_pr_files",
        return_value=set(),
    ):
        rc = run([1, 2], dry_run=True)
    assert rc == 1
    captured = capsys.readouterr()
    err = captured.err + captured.out
    assert "cycle" in err.lower()
    assert "#1" in err and "#2" in err


def test_run_live_path_uses_topo_order_too(capsys):
    """Live (non-dry-run) cascade also runs PRs through compute_merge_order."""
    diffs = {
        300: {"pyproject.toml"},
        301: {"pyproject.toml"},
    }
    seen: list[int] = []

    def fake_update(pr):
        seen.append(pr)
        return MergeResult(pr=pr, status="merged")

    with patch(
        "atdd.coach.commands.merge_cascade.fetch_pr_files",
        side_effect=lambda pr: diffs[pr],
    ), patch(
        "atdd.coach.commands.merge_cascade.update_branch",
        side_effect=fake_update,
    ), patch(
        "atdd.coach.commands.merge_cascade.wait_for_ci",
        return_value=MergeResult(pr=0, status="merged"),
    ), patch(
        "atdd.coach.commands.merge_cascade.merge_pr",
        return_value=MergeResult(pr=0, status="merged"),
    ):
        rc = run([301, 300], auto=True)
    assert rc == 0
    # Even though input was [301, 300], topo order [300, 301] should run
    assert seen == [300, 301]


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
