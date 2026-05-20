# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y002-INTEGRATION-001-github-label-reflects-sm-phase
# Acceptance: acc:drive-state-machine:Y002-INTEGRATION-001-github-label-reflects-sm-phase
# WMBT: wmbt:drive-state-machine:Y002
# Phase: RED
# Layer: integration
"""Y002-INTEGRATION-001 — GitHub label sequence mirrors SM advance sequence.

Issue #712 Edge B. After _drive_single_issue drives from PLANNED through
RED→GREEN, the _swap_phase_label stub records calls in order [RED, GREEN].
Each call's issue_number matches the SM's issue_number.

RED until _swap_phase_label is wired into all advance paths.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _make_cfg(tmp_path=None, *, issue_numbers=(690,), dry_run: bool = False):
    from atdd.coach.commands.coach import Config
    return Config(
        issue_numbers=list(issue_numbers),
        dry_run=dry_run,
        skip_review=True,
    )


def test_integration_label_calls_match_sm_history(tmp_path, monkeypatch):
    """_swap_phase_label call sequence matches sm.history after PLANNED→RED→GREEN drive."""
    from atdd.coach.commands.coach import Phase, _drive_single_issue
    from atdd.coach.handlers.state_machine import HandlerResult, StateMachine

    swap_log: list[tuple[int, object]] = []

    monkeypatch.setattr(
        "atdd.coach.commands.coach._read_current_github_phase",
        lambda _issue: Phase.PLANNED,
    )
    monkeypatch.setattr(
        "atdd.coach.commands.coach._swap_phase_label",
        lambda issue, phase: swap_log.append((issue, phase)),
    )

    def stub_spawn(ctx, t):
        return HandlerResult.HANDLED

    # Warm-resume at PLANNED advances to RED (swap #1).
    # Event1 (RED→GREEN, swap #2). Event2 (GREEN→SMOKE, swap #3).
    events = [
        {"event_type": "agent_done", "agent_id": "tester-690-aaa"},   # RED→GREEN
        {"event_type": "agent_done", "agent_id": "coder-690-bbb"},    # GREEN→SMOKE
    ]

    cfg = _make_cfg(tmp_path, dry_run=True)
    sm = StateMachine(issue_number=690, phase=Phase.INIT)

    rc = _drive_single_issue(
        cfg, sm, tmp_path,
        _spawn_func=stub_spawn,
        _injected_events=events,
    )

    assert rc == 0

    assert len(swap_log) == 3, (
        f"Expected 3 label swaps (warm-resume + 2 events); got {len(swap_log)}: {swap_log}"
    )

    issue_numbers = [n for n, _ in swap_log]
    assert all(n == 690 for n in issue_numbers), (
        f"All swaps must be for issue 690; got {issue_numbers}"
    )

    phases_swapped = [p for _, p in swap_log]
    assert phases_swapped == [Phase.RED, Phase.GREEN, Phase.SMOKE], (
        f"Label swap order must mirror SM advance order (warm-resume + 2 events); got {phases_swapped}"
    )
