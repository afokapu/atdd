# URN: test:coach-wave-orchestration:within-wave-concurrency-and-pane-identity:E001-UNIT-003-blocked-member-not-aborting-siblings
# Acceptance: acc:coach-wave-orchestration:E001-UNIT-003-blocked-member-not-aborting-siblings
# WMBT: wmbt:coach-wave-orchestration:E001
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E001-UNIT-003 — a BLOCKED wave member is surfaced in the aggregate result
without preventing already-spawned siblings from running to completion.

RED: ``_execute_cold_start`` returns on the first non-zero ``rc``
(``if rc != 0: return rc``), so a BLOCKED #A aborts the whole run before #B is
ever driven. This test pins the aggregate-result behaviour from Decision #1.
"""
from __future__ import annotations

import threading

import pytest

from atdd.coach.commands import coach

pytestmark = [pytest.mark.platform]

ISSUE_A = 9201
ISSUE_B = 9202


def _aggregate_rc(result):
    """Extract the aggregate return code from ``_execute_cold_start``'s result."""
    if hasattr(result, "rc"):
        return result.rc
    if isinstance(result, dict) and "rc" in result:
        return result["rc"]
    return result


def _blocked_members(result):
    """Extract the set of BLOCKED issue numbers, or None if not identifiable."""
    if hasattr(result, "blocked"):
        return set(result.blocked)
    if isinstance(result, dict) and "blocked" in result:
        return set(result["blocked"])
    return None


def test_blocked_member_does_not_abort_siblings(tmp_path, monkeypatch):
    """#B runs to COMPLETE even though sibling #A resolves BLOCKED."""
    # build_plan -> None: single wave [ISSUE_A, ISSUE_B].
    monkeypatch.setattr(coach, "build_plan", lambda nums: None)

    lock = threading.Lock()
    entered: list[int] = []
    completed: list[int] = []
    barrier = threading.Barrier(2, timeout=3)

    def fake_drive(cfg, sm, runtime_dir, **kwargs):
        n = sm.issue_number
        with lock:
            entered.append(n)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        # #A resolves BLOCKED (non-zero rc); #B runs to COMPLETE (rc 0).
        if n == ISSUE_A:
            sm.history.append(sm.phase)
            sm.phase = coach.Phase.BLOCKED
            return 1
        sm.history.append(sm.phase)
        sm.phase = coach.Phase.COMPLETE
        with lock:
            completed.append(n)
        return 0

    monkeypatch.setattr(coach, "_drive_single_issue", fake_drive)

    cfg = coach.Config(issue_numbers=[ISSUE_A, ISSUE_B])
    machines = [coach.initialize_state_machine(n) for n in (ISSUE_A, ISSUE_B)]

    result = coach._execute_cold_start(cfg, machines, tmp_path)

    # #B was driven to its COMPLETE terminal state — not un-spawned or skipped.
    assert ISSUE_B in entered, "#B was never entered — #A's rc aborted it"
    assert ISSUE_B in completed, "#B did not run to COMPLETE"
    # The aggregate rc is non-zero...
    assert _aggregate_rc(result) != 0, (
        f"aggregate rc should be non-zero when a member BLOCKs; got {result!r}"
    )
    # ...and it identifies #A — not #B — as the BLOCKED member.
    blocked = _blocked_members(result)
    assert blocked is not None, (
        f"_execute_cold_start return {result!r} carries no per-member identity "
        f"— the operator cannot tell which member BLOCKED"
    )
    assert ISSUE_A in blocked, f"#A not reported as BLOCKED: {blocked}"
    assert ISSUE_B not in blocked, f"#B wrongly reported as BLOCKED: {blocked}"
