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


# ---------------------------------------------------------------------------
# --multiplexer-mode pane (wmbt:govern-lifecycle:D016)
# ---------------------------------------------------------------------------


class _FakeBackend:
    """Records calls; returns predictable refs for new_workspace/new_surface."""

    def __init__(self):
        self.workspace_calls: list[dict] = []
        self.surface_calls: list[dict] = []
        self._wcounter = 0
        self._scounter = 0

    def new_workspace(self, cwd, command, name=None):
        self._wcounter += 1
        self.workspace_calls.append({"cwd": cwd, "command": command, "name": name})
        return f"workspace:{self._wcounter}"

    def new_surface(self, workspace_ref=None, pane_ref=None, cwd=None, command=None, name=None):
        self._scounter += 1
        self.surface_calls.append({
            "workspace_ref": workspace_ref,
            "pane_ref": pane_ref,
            "cwd": cwd,
            "command": command,
            "name": name,
        })
        return f"surface:{self._scounter}"


def _wire_run_orchestrate(tmp_path, backend, plan: dict[int, PlannedIssue]):
    """Patch orchestrate's collaborators so run() exercises the dispatch logic only."""
    from atdd.coach.commands import orchestrate as orch

    def fake_build_plan(issue_numbers):
        return {n: plan[n] for n in issue_numbers if n in plan}

    def fake_create_worktree(branch, path):
        Path(path).mkdir(parents=True, exist_ok=True)

    fake_build_context = lambda *a, **kw: type(
        "Ctx", (), {"branch": kw.get("branch", "feat/x"), "stop_condition": ""}
    )()
    fake_render = lambda ctx: "launch script body"

    return patch.multiple(
        orch,
        build_plan=fake_build_plan,
        _create_worktree=fake_create_worktree,
        get_multiplexer=lambda preferred=None: backend,
        build_context=lambda **kw: type("Ctx", (), {"stop_condition": "", "branch": "feat/x"})(),
        render=lambda ctx: "launch script body",
    )


def test_orchestrate_pane_mode_calls_new_surface_not_new_workspace(tmp_path: Path):
    """D016-AC-UNIT-001: pane mode dispatches to new_surface; new_workspace is NOT called.

    State file records the surface ref per issue.
    """
    from atdd.coach.commands.orchestrate import run as run_orchestrate

    plan = {
        1: PlannedIssue(number=1, title="A", branch="feat/a", body="", dependencies=[]),
        2: PlannedIssue(number=2, title="B", branch="feat/b", body="", dependencies=[]),
    }
    backend = _FakeBackend()
    state_file = tmp_path / "state.json"

    with _wire_run_orchestrate(tmp_path, backend, plan):
        rc = run_orchestrate(
            issue_numbers=[1, 2],
            multiplexer_mode="pane",
            state_file=str(state_file),
        )

    assert rc == 0
    assert len(backend.surface_calls) == 2
    assert backend.workspace_calls == []

    saved = json.loads(state_file.read_text())
    assert saved["1"]["mode"] == "pane"
    assert saved["1"]["ref"].startswith("surface:")
    assert saved["2"]["ref"].startswith("surface:")


def test_orchestrate_default_mode_is_workspace_backwards_compatible(tmp_path: Path):
    """D016-AC-UNIT-001: default invocation (no flag) preserves the existing workspace mode."""
    from atdd.coach.commands.orchestrate import run as run_orchestrate

    plan = {1: PlannedIssue(number=1, title="A", branch="feat/a", body="", dependencies=[])}
    backend = _FakeBackend()
    state_file = tmp_path / "state.json"

    with _wire_run_orchestrate(tmp_path, backend, plan):
        rc = run_orchestrate(
            issue_numbers=[1],
            state_file=str(state_file),
        )

    assert rc == 0
    assert len(backend.workspace_calls) == 1
    assert backend.surface_calls == []


def test_orchestrate_resume_pane_mode_skips_already_launched(tmp_path: Path):
    """D016-AC-UNIT-002: --resume in pane mode reuses existing surface refs without recreating them."""
    from atdd.coach.commands.orchestrate import run as run_orchestrate

    plan = {
        1: PlannedIssue(number=1, title="A", branch="feat/a", body="", dependencies=[]),
        2: PlannedIssue(number=2, title="B", branch="feat/b", body="", dependencies=[]),
    }
    backend = _FakeBackend()
    state_file = tmp_path / "state.json"

    # Pre-existing state from a prior pane-mode run
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "1": {
            "worktree_created": True,
            "worktree_path": str(tmp_path / "feat-a"),
            "launched": True,
            "ref": "surface:777",
            "mode": "pane",
        },
        "2": {
            "worktree_created": True,
            "worktree_path": str(tmp_path / "feat-b"),
        },
    }))

    with _wire_run_orchestrate(tmp_path, backend, plan):
        rc = run_orchestrate(
            issue_numbers=[1, 2],
            multiplexer_mode="pane",
            resume=True,
            state_file=str(state_file),
        )

    assert rc == 0
    # Issue 1 is already launched in pane mode → should NOT call new_surface again.
    # Only issue 2 needs a fresh surface.
    assert len(backend.surface_calls) == 1
    assert len(backend.workspace_calls) == 0

    saved = json.loads(state_file.read_text())
    assert saved["1"]["ref"] == "surface:777"  # untouched
    assert saved["2"]["ref"].startswith("surface:")
