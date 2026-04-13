"""
Unit tests for `atdd orchestrate`.

SPEC-COACH-ORCH-0001: dependency DAG → wave grouping.
SPEC-COACH-ORCH-0002: one worktree per issue.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atdd.coach.commands.orchestrate import (
    PlannedIssue,
    _parse_dep_numbers,
    build_plan,
    compute_waves,
    load_state,
    save_state,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# compute_waves
# ---------------------------------------------------------------------------


def _plan_from(spec: dict[int, list[int]]) -> dict[int, PlannedIssue]:
    return {num: PlannedIssue(number=num, dependencies=deps) for num, deps in spec.items()}


def test_compute_waves_independent_issues_single_wave():
    plan = _plan_from({1: [], 2: [], 3: []})
    assert compute_waves(plan) == [[1, 2, 3]]


def test_compute_waves_linear_chain():
    plan = _plan_from({1: [], 2: [1], 3: [2]})
    assert compute_waves(plan) == [[1], [2], [3]]


def test_compute_waves_diamond():
    plan = _plan_from({1: [], 2: [1], 3: [1], 4: [2, 3]})
    waves = compute_waves(plan)
    assert waves == [[1], [2, 3], [4]]


def test_compute_waves_ignores_out_of_scope_deps():
    plan = _plan_from({10: [999], 11: [10]})
    assert compute_waves(plan) == [[10], [11]]


def test_compute_waves_detects_cycle():
    plan = _plan_from({1: [2], 2: [1]})
    with pytest.raises(ValueError, match="cycle"):
        compute_waves(plan)


def test_wave_field_populated_on_plan():
    plan = _plan_from({1: [], 2: [1]})
    compute_waves(plan)
    assert plan[1].wave == 0
    assert plan[2].wave == 1


# ---------------------------------------------------------------------------
# _parse_dep_numbers
# ---------------------------------------------------------------------------


def test_parse_dep_numbers_extracts_ints():
    body = "## Scope\n\n### Dependencies\n\n- #256 (complete)\n- #10 helper\n"
    assert _parse_dep_numbers(body) == [256, 10]


def test_parse_dep_numbers_empty_when_none():
    body = "## Scope\n\n(no dependency section)\n"
    assert _parse_dep_numbers(body) == []


# ---------------------------------------------------------------------------
# state file
# ---------------------------------------------------------------------------


def test_state_roundtrip(tmp_path: Path):
    state_path = tmp_path / "nested" / "state.json"
    payload = {"1": {"worktree_created": True, "launched": False}}
    save_state(state_path, payload)
    assert state_path.exists()
    assert load_state(state_path) == payload


def test_load_state_missing_returns_empty(tmp_path: Path):
    assert load_state(tmp_path / "nope.json") == {}


def test_load_state_malformed_returns_empty(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("not-json")
    assert load_state(path) == {}


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------


_ISSUE_A = {
    "number": 1,
    "title": "A",
    "body": (
        "## Issue Metadata\n\n"
        "| Field | Value |\n|-------|-------|\n"
        "| Branch | feat/a |\n\n"
        "## Scope\n\n### Dependencies\n\n(none)\n"
    ),
}

_ISSUE_B = {
    "number": 2,
    "title": "B",
    "body": (
        "## Issue Metadata\n\n"
        "| Field | Value |\n|-------|-------|\n"
        "| Branch | feat/b |\n\n"
        "## Scope\n\n### Dependencies\n\n- #1\n"
    ),
}


def test_build_plan_populates_branches_and_deps():
    fake_issues = {1: _ISSUE_A, 2: _ISSUE_B}

    def fake_fetch(n):
        return fake_issues.get(n, {})

    with patch(
        "atdd.coach.commands.orchestrate.fetch_issue",
        side_effect=fake_fetch,
    ):
        plan = build_plan([1, 2])

    assert set(plan.keys()) == {1, 2}
    assert plan[1].branch == "feat/a"
    assert plan[2].branch == "feat/b"
    assert plan[2].dependencies == [1]


def test_build_plan_skips_unfetchable():
    with patch(
        "atdd.coach.commands.orchestrate.fetch_issue",
        return_value={},
    ):
        plan = build_plan([42])
    assert plan == {}
