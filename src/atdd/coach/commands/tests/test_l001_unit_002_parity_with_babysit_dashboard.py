# URN: test:observe-and-correct:observer-operator-surface:L001-UNIT-002-parity-with-babysit-dashboard
# Acceptance: acc:observe-and-correct:L001-UNIT-002-parity-with-babysit-dashboard
# WMBT: wmbt:observe-and-correct:L001
# Phase: RED
# Layer: application
# Assertion: behavioral
"""L001-UNIT-002 — `atdd observer status` is at parity with `atdd babysit`'s
dashboard at time of decommissioning, modulo trailing whitespace.

The data source for `atdd observer status` is `.atdd/runtime/agents/*/`,
not direct multiplexer polling. Parity is documented as a gating
condition for #P6 (babysit decommissioning).

Issue #515 (L6). Spec: `atdd-coach-spec-v9.md` §5.4 / §0.2 / §11.3.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _strip_trailing_ws(s: str) -> list[str]:
    return [ln.rstrip() for ln in s.splitlines()]


def _seed_agent(
    runtime: Path, *, agent_id: str, phase: str, issue: int,
    heartbeat_offset_s: int, token_count: int | None = None,
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
    (agent_dir / "context.json").write_text(
        json.dumps({"phase": phase, "issue": issue, "wmbt_urn": "wmbt:x:R001"})
    )


# ---------------------------------------------------------------------------
# Parity: same renderer, same column content for a fixture set
# ---------------------------------------------------------------------------


def test_observer_uses_absorbed_renderer_and_row_object():
    """Parity guarantee: observer's renderer/value-object are imported
    from the SAME module so any rendering change applies uniformly."""
    from atdd.coach.commands.observer import (
        _render_dashboard as observer_render,
    )
    from atdd.coach.commands.observer import (
        SurfaceRow as observer_row,
    )
    # The babysit module re-exports the absorbed names so existing imports
    # (e.g. legacy babysit dashboard tests) keep working without depending
    # on the absorbed bodies living in babysit.py.
    from atdd.coach.commands.babysit import (
        SurfaceRow as babysit_row,
    )
    from atdd.coach.commands.babysit import (
        _render_dashboard as babysit_render,
    )

    assert observer_render is babysit_render, (
        "babysit must re-export the absorbed _render_dashboard from observer"
    )
    assert observer_row is babysit_row, (
        "babysit must re-export the absorbed SurfaceRow from observer"
    )


def test_dashboard_row_content_matches_babysit_modulo_trailing_whitespace(
    tmp_path: Path,
):
    """Same SurfaceRow inputs → same rendered string modulo trailing
    whitespace. This protects every operator using the dashboard from a
    silent regression at decommissioning time."""
    from atdd.coach.commands.observer import (
        SurfaceRow,
        _render_dashboard,
    )

    rows = [
        SurfaceRow(
            ref="agent-A", issue=515, phase="RED",
            last_tool_seconds=14.0, pending_prompt="",
            stalled=False, status="ACTIVE",
        ),
        SurfaceRow(
            ref="agent-B", issue=516, phase="GREEN",
            last_tool_seconds=82.0, pending_prompt="1 (Bash)",
            stalled=False, status="escalated",
        ),
        SurfaceRow(
            ref="agent-C", issue=517, phase="SMOKE",
            last_tool_seconds=14 * 60 + 8, pending_prompt="",
            stalled=True, status="STALLED",
        ),
    ]
    out = _render_dashboard(
        rows=rows,
        now_iso="2026-05-09T17:14:00Z",
        scope_label=".atdd/runtime/agents/",
    )

    lines = _strip_trailing_ws(out)
    # Header references the runtime-folder scope, not multiplexer polling
    assert any(".atdd/runtime/agents/" in ln for ln in lines)
    # Column row content for every agent matches what babysit would render
    assert any("agent-A" in ln and "#515" in ln and "RED" in ln and "0:00:14" in ln for ln in lines)
    assert any("agent-B" in ln and "#516" in ln and "GREEN" in ln and "0:01:22" in ln and "1 (Bash)" in ln for ln in lines)
    assert any("agent-C" in ln and "#517" in ln and "SMOKE" in ln and "0:14:08" in ln and "STALLED" in ln for ln in lines)


def test_observer_status_data_source_is_runtime_folder_not_multiplexer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """`atdd observer status` MUST read from `.atdd/runtime/agents/*/`.
    Detection: when the runtime folder has agents, status uses them
    even with no multiplexer/babysit machinery available."""
    from atdd.coach.commands import observer

    # Sentinel: any attempt to call into babysit's polling helpers must fail
    # the test. observer.cmd_status MUST NOT route through these paths.
    import atdd.coach.commands.babysit as babysit_mod

    def _fail(*_a, **_kw):  # pragma: no cover — assertion path
        raise AssertionError(
            "observer.cmd_status routed through babysit polling — must read "
            "from .atdd/runtime/agents/*/ only"
        )

    monkeypatch.setattr(babysit_mod, "_load_orchestrate_state", _fail, raising=False)
    monkeypatch.setattr(babysit_mod, "_fetch_phase_cache", _fail, raising=False)

    runtime = tmp_path / ".atdd" / "runtime"
    _seed_agent(
        runtime, agent_id="agent-A", phase="RED",
        issue=515, heartbeat_offset_s=14, token_count=12_000,
    )

    rc = observer.cmd_status(runtime_dir=runtime)
    out = capsys.readouterr().out

    assert rc == 0
    assert "agent-A" in out
    assert "#515" in out
    assert "RED" in out


def test_parity_gating_condition_documented_in_module_docstring():
    """Per AC-002 the parity is documented as a gating condition for #P6
    (babysit decommissioning). The observer module records this so an
    operator searching the codebase can find the contract."""
    import atdd.coach.commands.observer as observer_mod

    text = (observer_mod.__doc__ or "")
    assert "#P6" in text or "decommission" in text.lower(), (
        "observer module docstring must record the #P6 parity-gating "
        "condition per AC-002"
    )
