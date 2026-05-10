# URN: test:drive-state-machine:coach-state-machine-and-runtime:D001-UNIT-003-compute-waves-reuse
# Acceptance: acc:drive-state-machine:D001-UNIT-003-compute-waves-reuse
# WMBT: wmbt:drive-state-machine:D001
# Phase: RED
# Layer: application
"""D001-UNIT-003 — multi-issue invocations reuse `compute_waves()`.

Per spec §0.2 absorption discipline: every absorbed function moves into
coach modules with behavior preserved — nothing is rewritten. J1 reuses
`compute_waves()` from `commands/orchestrate.py` directly; it does not
copy or shadow the function. `--strict-deps` propagates into the
wave-transition gating policy.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def test_coach_imports_compute_waves_from_orchestrate():
    """The function symbol in coach.py must BE the one in the archived
    orchestrate module (P5 #531: orchestrate.py is now a stub; the
    absorbed implementation lives in commands/_archived/orchestrate.py)."""
    import atdd.coach.commands.coach as coach_mod
    from atdd.coach.commands._archived import orchestrate as orchestrate_mod

    assert coach_mod.compute_waves is orchestrate_mod.compute_waves


def test_coach_does_not_shadow_compute_waves_with_local_def():
    """If we ever rewrite compute_waves locally, this test fails."""
    import inspect

    import atdd.coach.commands.coach as coach_mod

    src = inspect.getsource(coach_mod)
    assert "def compute_waves" not in src, (
        "coach.py must reuse compute_waves from orchestrate; do not redefine it"
    )


def test_run_multi_issue_invokes_compute_waves(capsys):
    """`atdd coach 358 359 360 --strict-deps --dry-run` calls
    `compute_waves` and prints the resolved wave assignment."""
    from atdd.coach.commands.coach import run
    from atdd.coach.commands._archived.orchestrate import PlannedIssue

    fake_plan = {
        358: PlannedIssue(number=358, dependencies=[]),
        359: PlannedIssue(number=359, dependencies=[358]),
        360: PlannedIssue(number=360, dependencies=[359]),
    }

    with patch(
        "atdd.coach.commands.coach.build_plan",
        return_value=fake_plan,
    ) as mock_build, patch(
        "atdd.coach.commands.coach.compute_waves",
        wraps=__import__(
            "atdd.coach.commands._archived.orchestrate",
            fromlist=["compute_waves"],
        ).compute_waves,
    ) as mock_waves:
        rc = run(
            issue_numbers=[358, 359, 360],
            strict_deps=True,
            dry_run=True,
        )

    assert rc == 0
    assert mock_build.called
    assert mock_waves.called

    out = capsys.readouterr().out
    assert "wave" in out.lower()
    assert "358" in out and "359" in out and "360" in out


def test_strict_deps_propagates_into_state_machine_policy():
    """When --strict-deps is set, the resolved configuration carries the
    flag forward so wave-transition gating can consult it later."""
    from atdd.coach.commands.coach import parse_cli, resolve_policy

    cfg = parse_cli(["358", "359", "360", "--strict-deps"])
    policy = resolve_policy(cfg)

    assert policy.strict_deps is True


def test_strict_deps_default_false():
    from atdd.coach.commands.coach import parse_cli, resolve_policy

    cfg = parse_cli(["358"])
    policy = resolve_policy(cfg)

    assert policy.strict_deps is False
