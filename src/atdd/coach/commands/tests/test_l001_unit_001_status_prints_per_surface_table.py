# URN: test:observe-and-correct:observer-operator-surface:L001-UNIT-001-status-prints-per-surface-table
# Acceptance: acc:observe-and-correct:L001-UNIT-001-status-prints-per-surface-table
# WMBT: wmbt:observe-and-correct:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""L001-UNIT-001 — `atdd observer status` prints a per-surface table with
rows for each active agent under `.atdd/runtime/agents/`. Each row
includes name, phase, last-heartbeat (formatted via the absorbed
`_format_hms`), and token count. Layout matches the absorbed
``SurfaceRow`` schema.

Issue #515 (L6). Spec: `atdd-coach-spec-v9.md` §5.4 / §0.2 / §3.2.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Module surface — the four dashboard functions must land
# in the observer module per spec §0.2 absorption inventory.
# ---------------------------------------------------------------------------


def test_observer_module_exposes_absorbed_dashboard_names():
    from atdd.coach.commands import observer

    for name in (
        "SurfaceRow",
        "_format_hms",
        "_render_dashboard",
        "_extract_surface_state_from_runtime",
    ):
        assert hasattr(observer, name), (
            f"missing atdd.coach.commands.observer.{name} — required by "
            "L6 (#515) absorption inventory"
        )


def test_surface_row_carries_token_count_field():
    """Per AC-001 the row data must include `token_count` so the
    dashboard layer (or any downstream consumer) can surface it.
    `token_count` may be ``None`` when an agent has no telemetry."""
    from atdd.coach.commands.observer import SurfaceRow

    row = SurfaceRow(
        ref="agent-A",
        issue=515,
        phase="RED",
        last_tool_seconds=12.0,
        pending_prompt="",
        stalled=False,
        status="ACTIVE",
        token_count=12_345,
    )
    assert row.token_count == 12_345


def test_format_hms_signature():
    from atdd.coach.commands.observer import _format_hms

    assert _format_hms(0) == "0:00:00"
    assert _format_hms(14) == "0:00:14"
    assert _format_hms(3 * 3600 + 45 * 60 + 6) == "3:45:06"


# ---------------------------------------------------------------------------
# Reading from `.atdd/runtime/agents/*/` — the data-source migration
# ---------------------------------------------------------------------------


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _seed_agent(
    runtime: Path,
    *,
    agent_id: str,
    phase: str,
    issue: int,
    heartbeat_offset_s: int,
    token_count: int | None,
) -> None:
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    heartbeat = {
        "pid": 12345,
        "observed_at": _iso_z(now - timedelta(seconds=heartbeat_offset_s)),
        "status": "running",
    }
    if token_count is not None:
        heartbeat["token_count"] = token_count
    (agent_dir / "heartbeat.json").write_text(json.dumps(heartbeat))
    context = {"phase": phase, "issue": issue, "wmbt_urn": f"wmbt:fake:{phase}"}
    (agent_dir / "context.json").write_text(json.dumps(context))


def test_extract_surface_state_from_runtime_reads_heartbeat_and_context(
    tmp_path: Path,
):
    """Building a SurfaceRow from `.atdd/runtime/agents/<id>/` is a pure
    function of the per-agent files. No multiplexer polling."""
    from atdd.coach.commands.observer import _extract_surface_state_from_runtime

    runtime = tmp_path / ".atdd" / "runtime"
    _seed_agent(
        runtime,
        agent_id="agent-A",
        phase="RED",
        issue=515,
        heartbeat_offset_s=14,
        token_count=12_000,
    )
    agent_dir = runtime / "agents" / "agent-A"

    row = _extract_surface_state_from_runtime(agent_dir=agent_dir)

    assert row.ref == "agent-A"
    assert row.issue == 515
    assert row.phase == "RED"
    assert row.last_tool_seconds == pytest.approx(14, abs=2.0)
    assert row.token_count == 12_000


def test_extract_surface_state_from_runtime_handles_missing_token_count(
    tmp_path: Path,
):
    from atdd.coach.commands.observer import _extract_surface_state_from_runtime

    runtime = tmp_path / ".atdd" / "runtime"
    _seed_agent(
        runtime,
        agent_id="agent-B",
        phase="GREEN",
        issue=600,
        heartbeat_offset_s=4,
        token_count=None,
    )
    agent_dir = runtime / "agents" / "agent-B"

    row = _extract_surface_state_from_runtime(agent_dir=agent_dir)

    assert row.ref == "agent-B"
    assert row.token_count is None


# ---------------------------------------------------------------------------
# `cmd_status` end-to-end — prints a per-surface table for every active
# agent under `.atdd/runtime/agents/`
# ---------------------------------------------------------------------------


def test_cmd_status_prints_table_with_one_row_per_active_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    _seed_agent(
        runtime, agent_id="agent-A", phase="RED",
        issue=515, heartbeat_offset_s=14, token_count=12_000,
    )
    _seed_agent(
        runtime, agent_id="agent-B", phase="GREEN",
        issue=516, heartbeat_offset_s=82, token_count=42_000,
    )
    _seed_agent(
        runtime, agent_id="agent-C", phase="SMOKE",
        issue=517, heartbeat_offset_s=7, token_count=None,
    )

    rc = observer.cmd_status(runtime_dir=runtime)
    out = capsys.readouterr().out

    assert rc == 0
    # Header / column markers
    assert "ATDD Dashboard" in out
    for col in ("Surface", "Issue", "Phase"):
        assert col in out
    # Each agent surfaces in the rendered table (name = agent_id)
    for aid in ("agent-A", "agent-B", "agent-C"):
        assert aid in out, f"missing agent {aid} from status output"
    # Issue numbers from context.json
    assert "#515" in out
    assert "#516" in out
    # Phases from context.json
    for phase in ("RED", "GREEN", "SMOKE"):
        assert phase in out
    # Last-heartbeat formatted via _format_hms (h:mm:ss)
    assert "0:00:14" in out
    assert "0:01:22" in out


def test_cmd_status_handles_empty_runtime_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """No agents → status still prints a header (does not crash)."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rc = observer.cmd_status(runtime_dir=runtime)
    out = capsys.readouterr().out

    assert rc == 0
    assert "ATDD Dashboard" in out
