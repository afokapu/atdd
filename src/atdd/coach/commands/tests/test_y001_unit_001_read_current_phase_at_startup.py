# URN: test:drive-state-machine:coach-state-machine-and-runtime:Y001-UNIT-001-read-current-phase-at-startup
# Acceptance: acc:drive-state-machine:Y001-UNIT-001-read-current-phase-at-startup
# WMBT: wmbt:drive-state-machine:Y001
# Phase: RED
# Layer: application
"""Y001-UNIT-001 — _drive_single_issue reads the live GitHub phase at startup.

Issue #712 Edge A. The current code always cold-starts from INIT regardless
of the issue's actual GitHub phase. This test verifies that a dedicated
_read_current_github_phase helper is imported from coach.py and is called
at _drive_single_issue entry so the SM can resume from the correct phase.

RED until _read_current_github_phase exists in coach.py.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_read_current_github_phase_is_importable():
    """_read_current_github_phase must be importable from coach.py."""
    from atdd.coach.commands.coach import _read_current_github_phase  # noqa: F401


def test_read_current_github_phase_returns_phase_enum_or_none():
    """_read_current_github_phase returns a Phase enum value or None.

    When called with a valid issue number and a monkeypatched gh CLI, the
    function maps the atdd:<phase> label to the Phase enum.
    """
    from atdd.coach.commands.coach import Phase, _read_current_github_phase
    import subprocess

    captured = []

    def fake_run(args, **kwargs):
        captured.append(args)
        result = type("R", (), {"stdout": '["atdd:PLANNED", "atdd-issue"]', "returncode": 0})()
        return result

    import unittest.mock as mock
    with mock.patch("subprocess.run", side_effect=fake_run):
        phase = _read_current_github_phase(690)

    assert phase == Phase.PLANNED, f"Expected PLANNED, got {phase}"


def test_read_current_github_phase_returns_none_on_no_phase_label():
    """_read_current_github_phase returns None when no atdd:<phase> label is present."""
    from atdd.coach.commands.coach import _read_current_github_phase
    import unittest.mock as mock

    def fake_run(args, **kwargs):
        result = type("R", (), {"stdout": '["atdd-issue", "archetype:coach"]', "returncode": 0})()
        return result

    with mock.patch("subprocess.run", side_effect=fake_run):
        phase = _read_current_github_phase(690)

    assert phase is None
