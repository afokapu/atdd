# URN: test:drive-state-machine:coach-state-machine-and-runtime:wave-planning-unit
# Phase: GREEN
# Layer: application
"""Direct unit coverage for wave planning (issue #985).

These replace the compute_waves cases from the retired parity tests:
the topological-sort planner is now first-class coach code in
``commands/wave_planning.py`` (relocated from the decommissioned
legacy launcher).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.wave_planning import PlannedIssue, compute_waves

pytestmark = [pytest.mark.platform]


def _plan(deps: dict[int, list[int]]) -> dict[int, PlannedIssue]:
    return {n: PlannedIssue(number=n, dependencies=d) for n, d in deps.items()}


def test_compute_waves_independent_issues_single_wave():
    waves = compute_waves(_plan({1: [], 2: [], 3: []}))
    assert waves == [[1, 2, 3]]


def test_compute_waves_linear_chain():
    waves = compute_waves(_plan({1: [], 2: [1], 3: [2]}))
    assert waves == [[1], [2], [3]]


def test_compute_waves_diamond():
    waves = compute_waves(_plan({1: [], 2: [1], 3: [1], 4: [2, 3]}))
    assert waves == [[1], [2, 3], [4]]


def test_compute_waves_ignores_out_of_scope_deps():
    # Dep #99 is not in the plan → treated as already-resolved.
    waves = compute_waves(_plan({1: [99], 2: [1]}))
    assert waves == [[1], [2]]


def test_compute_waves_detects_cycle():
    with pytest.raises(ValueError, match="cycle"):
        compute_waves(_plan({1: [2], 2: [1]}))


def test_compute_waves_assigns_wave_index_on_records():
    plan = _plan({1: [], 2: [1]})
    compute_waves(plan)
    assert plan[1].wave == 0
    assert plan[2].wave == 1
