"""
Unit tests for `atdd babysit --dashboard` (issue #377).

Covers:
  * ``_load_orchestrate_state`` — invert the ``{"<issue>": {"ref": ...}}`` map
    written by ``orchestrate.py`` into ``{ref: issue_num}``.
  * ``_extract_surface_state`` — turn a per-ref ``WorkspaceState`` plus the
    inverted orchestrate state into a ``SurfaceRow`` (issue, phase label,
    last-tool elapsed, pending-prompt indicator, stalled flag).
  * ``_render_dashboard`` — pure renderer of the aggregate table.

Tests are behavioral: exercise the function under test and assert on the
returned value, not on internal control flow.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from atdd.coach.commands.babysit import (
    BabysitDecision,
    SurfaceRow,
    WorkspaceState,
    _extract_surface_state,
    _load_orchestrate_state,
    _render_dashboard,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# _load_orchestrate_state — inversion of orchestrate-state.json
# ---------------------------------------------------------------------------


def test_load_orchestrate_state_inverts_issue_to_ref(tmp_path: Path):
    state_file = tmp_path / "orchestrate-state.json"
    state_file.write_text(
        json.dumps(
            {
                "340": {"ref": "surface:31", "launched": True, "mode": "pane"},
                "341": {"ref": "surface:32", "launched": True, "mode": "pane"},
            }
        )
    )

    inverted = _load_orchestrate_state(state_file)

    assert inverted == {"surface:31": 340, "surface:32": 341}


def test_load_orchestrate_state_returns_empty_when_file_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist.json"

    assert _load_orchestrate_state(missing) == {}


def test_load_orchestrate_state_skips_entries_without_ref(tmp_path: Path):
    state_file = tmp_path / "orchestrate-state.json"
    state_file.write_text(
        json.dumps(
            {
                "340": {"ref": "surface:31", "launched": True},
                "341": {"worktree_created": True},  # no ref yet
                "342": {"ref": "", "launched": False},  # empty ref
            }
        )
    )

    inverted = _load_orchestrate_state(state_file)

    assert inverted == {"surface:31": 340}


def test_load_orchestrate_state_handles_legacy_workspace_ref_key(tmp_path: Path):
    """Older state files used `workspace_ref` instead of `ref` (resume path
    fallback in orchestrate.run)."""
    state_file = tmp_path / "orchestrate-state.json"
    state_file.write_text(
        json.dumps(
            {
                "340": {"workspace_ref": "workspace:17", "launched": True},
            }
        )
    )

    inverted = _load_orchestrate_state(state_file)

    assert inverted == {"workspace:17": 340}


# ---------------------------------------------------------------------------
# _extract_surface_state — assemble one dashboard row
# ---------------------------------------------------------------------------


def test_extract_surface_state_resolves_issue_and_phase():
    now = 1_000_000.0
    state = WorkspaceState(
        ref="surface:31",
        last_screen_hash="abc",
        last_change_ts=now - 14,  # 0:00:14 elapsed
    )
    row = _extract_surface_state(
        ref="surface:31",
        state=state,
        ref_to_issue={"surface:31": 340},
        phase_cache={340: "RED"},
        last_decision=None,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.ref == "surface:31"
    assert row.issue == 340
    assert row.phase == "RED"
    assert row.last_tool_seconds == pytest.approx(14, abs=0.5)
    assert row.pending_prompt == ""
    assert row.stalled is False
    assert row.status == "ACTIVE"


def test_extract_surface_state_unresolved_issue_renders_dash():
    """When the ref is not in orchestrate-state.json, issue/phase fall back
    to a placeholder rather than crashing the whole dashboard."""
    now = 1_000_000.0
    state = WorkspaceState(ref="surface:99", last_change_ts=now)
    row = _extract_surface_state(
        ref="surface:99",
        state=state,
        ref_to_issue={},
        phase_cache={},
        last_decision=None,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.issue is None
    assert row.phase == "?"


def test_extract_surface_state_missing_phase_label_uses_question_mark():
    now = 1_000_000.0
    state = WorkspaceState(ref="surface:31", last_change_ts=now)
    row = _extract_surface_state(
        ref="surface:31",
        state=state,
        ref_to_issue={"surface:31": 340},
        phase_cache={},  # phase fetch hasn't populated this issue
        last_decision=None,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.issue == 340
    assert row.phase == "?"


def test_extract_surface_state_pending_prompt_from_decision():
    now = 1_000_000.0
    state = WorkspaceState(ref="surface:31", last_change_ts=now)
    decision = BabysitDecision(
        action="escalate", matched="Bash", reason="unknown command"
    )
    row = _extract_surface_state(
        ref="surface:31",
        state=state,
        ref_to_issue={"surface:31": 340},
        phase_cache={340: "GREEN"},
        last_decision=decision,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.pending_prompt == "1 (Bash)"
    assert row.status == "escalated"


def test_extract_surface_state_pending_prompt_recomputes_when_resolved():
    """The pending-prompt indicator is stateless — once the latest decision
    is no longer an escalate (e.g. agent moved on, classifier auto-approved
    next cycle), the indicator clears."""
    now = 1_000_000.0
    state = WorkspaceState(ref="surface:31", last_change_ts=now)
    auto = BabysitDecision(action="auto_approve", matched="Read")
    row = _extract_surface_state(
        ref="surface:31",
        state=state,
        ref_to_issue={"surface:31": 340},
        phase_cache={340: "GREEN"},
        last_decision=auto,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.pending_prompt == ""
    assert row.status == "ACTIVE"


def test_extract_surface_state_stalled_at_threshold_boundary():
    """Exactly stale_warn_minutes elapsed → STALLED."""
    now = 1_000_000.0
    state = WorkspaceState(
        ref="surface:36",
        last_change_ts=now - (15 * 60),  # exactly 15 min
    )
    row = _extract_surface_state(
        ref="surface:36",
        state=state,
        ref_to_issue={"surface:36": 343},
        phase_cache={343: "SMOKE"},
        last_decision=None,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.stalled is True
    assert row.status == "STALLED"


def test_extract_surface_state_stalled_just_under_threshold_is_active():
    now = 1_000_000.0
    state = WorkspaceState(
        ref="surface:36",
        last_change_ts=now - ((15 * 60) - 1),
    )
    row = _extract_surface_state(
        ref="surface:36",
        state=state,
        ref_to_issue={"surface:36": 343},
        phase_cache={343: "SMOKE"},
        last_decision=None,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.stalled is False
    assert row.status == "ACTIVE"


def test_extract_surface_state_violation_decision_becomes_status():
    now = 1_000_000.0
    state = WorkspaceState(ref="surface:31", last_change_ts=now)
    violation = BabysitDecision(
        action="violation", matched=".atdd/ hand-edit", reason="bad"
    )
    row = _extract_surface_state(
        ref="surface:31",
        state=state,
        ref_to_issue={"surface:31": 340},
        phase_cache={340: "RED"},
        last_decision=violation,
        now=now,
        stale_warn_minutes=15,
    )

    assert row.status == "violation"


# ---------------------------------------------------------------------------
# _render_dashboard — pure renderer
# ---------------------------------------------------------------------------


def test_render_dashboard_includes_header_and_columns():
    rows = [
        SurfaceRow(
            ref="surface:31",
            issue=340,
            phase="RED",
            last_tool_seconds=14,
            pending_prompt="",
            stalled=False,
            status="ACTIVE",
        ),
    ]
    output = _render_dashboard(
        rows=rows,
        now_iso="2026-05-03T17:14:00+00:00",
        scope_label="workspace:17",
    )

    assert "ATDD Dashboard" in output
    assert "workspace:17" in output
    assert "2026-05-03T17:14:00" in output
    # Column headers
    for col in ("Surface", "Issue", "Phase", "LastTool", "PendingPrompts", "Status"):
        assert col in output


def test_render_dashboard_renders_each_row():
    rows = [
        SurfaceRow(
            ref="surface:31",
            issue=340,
            phase="RED",
            last_tool_seconds=14,
            pending_prompt="",
            stalled=False,
            status="ACTIVE",
        ),
        SurfaceRow(
            ref="surface:32",
            issue=341,
            phase="GREEN",
            last_tool_seconds=82,
            pending_prompt="1 (Bash)",
            stalled=False,
            status="escalated",
        ),
        SurfaceRow(
            ref="surface:36",
            issue=343,
            phase="SMOKE",
            last_tool_seconds=14 * 60 + 8,
            pending_prompt="",
            stalled=True,
            status="STALLED",
        ),
    ]
    output = _render_dashboard(
        rows=rows,
        now_iso="2026-05-03T17:14:00+00:00",
        scope_label="workspace:17",
    )

    assert "surface:31" in output
    assert "#340" in output
    assert "RED" in output
    assert "0:00:14" in output

    assert "surface:32" in output
    assert "#341" in output
    assert "GREEN" in output
    assert "0:01:22" in output
    assert "1 (Bash)" in output
    assert "escalated" in output

    assert "surface:36" in output
    assert "#343" in output
    assert "SMOKE" in output
    assert "0:14:08" in output
    assert "STALLED" in output


def test_render_dashboard_lasttool_format_is_h_mm_ss():
    rows = [
        SurfaceRow(
            ref="surface:1",
            issue=1,
            phase="RED",
            last_tool_seconds=3 * 3600 + 45 * 60 + 6,
            pending_prompt="",
            stalled=False,
            status="ACTIVE",
        ),
    ]
    output = _render_dashboard(
        rows=rows, now_iso="2026-05-03T00:00:00+00:00", scope_label="ws"
    )
    assert "3:45:06" in output


def test_render_dashboard_unresolved_issue_renders_dash():
    rows = [
        SurfaceRow(
            ref="surface:99",
            issue=None,
            phase="?",
            last_tool_seconds=0,
            pending_prompt="",
            stalled=False,
            status="ACTIVE",
        ),
    ]
    output = _render_dashboard(
        rows=rows, now_iso="2026-05-03T00:00:00+00:00", scope_label="ws"
    )
    assert "—" in output or "-" in output  # placeholder for unknown issue


def test_render_dashboard_empty_rows_still_produces_header():
    output = _render_dashboard(
        rows=[],
        now_iso="2026-05-03T00:00:00+00:00",
        scope_label="workspace:17",
    )
    assert "ATDD Dashboard" in output
    assert "workspace:17" in output


# ---------------------------------------------------------------------------
# Integration: extract + render builds a stable string from real states
# ---------------------------------------------------------------------------


def test_extract_then_render_pipeline_smoke():
    now = time.time()
    states = {
        "surface:31": WorkspaceState(ref="surface:31", last_change_ts=now - 14),
        "surface:32": WorkspaceState(ref="surface:32", last_change_ts=now - 82),
    }
    decisions = {
        "surface:31": None,
        "surface:32": BabysitDecision(action="escalate", matched="Bash"),
    }
    ref_to_issue = {"surface:31": 340, "surface:32": 341}
    phase_cache = {340: "RED", 341: "GREEN"}

    rows = [
        _extract_surface_state(
            ref=ref,
            state=states[ref],
            ref_to_issue=ref_to_issue,
            phase_cache=phase_cache,
            last_decision=decisions[ref],
            now=now,
            stale_warn_minutes=15,
        )
        for ref in states
    ]
    output = _render_dashboard(
        rows=rows,
        now_iso="2026-05-03T17:14:00+00:00",
        scope_label="workspace:17",
    )

    assert "#340" in output
    assert "#341" in output
    assert "1 (Bash)" in output
