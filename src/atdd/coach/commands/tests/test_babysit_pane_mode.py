"""
Babysit behaviour with pane-mode refs.

WMBT: wmbt:govern-lifecycle:D017-AC-UNIT-002
Phase 4 deliverable from #343.

Asserts:
1. Babysit reads each ref independently — surface refs work the same as workspace refs
   because refs are opaque strings dispatched by the backend.
2. When babysit receives a workspace ref that aggregates multiple surfaces, all
   surface output flows through one WorkspaceState entry — the shared-state caveat
   documented in orchestration.convention.yaml.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atdd.coach.commands.babysit import (
    BabysitDecision,
    WorkspaceState,
    process_workspace,
)

pytestmark = [pytest.mark.platform]


def _silent_backend(screens: list[str]) -> MagicMock:
    backend = MagicMock()
    backend.read_screen.side_effect = screens
    return backend


def test_babysit_reads_surface_ref_like_workspace_ref(tmp_path: Path):
    """Babysit treats a surface:* ref the same as a workspace:* ref — refs are opaque."""
    backend = _silent_backend(["idle output\n"])
    state = WorkspaceState(ref="surface:31")

    decision = process_workspace(
        backend=backend,
        state=state,
        stale_warn_minutes=15,
        stale_escalate_minutes=30,
        log_path=tmp_path / "log.jsonl",
    )

    backend.read_screen.assert_called_once_with("surface:31", lines=80)
    assert decision.action == "idle"


def test_babysit_pane_mode_shares_state_per_ref(tmp_path: Path):
    """Documented caveat: state is keyed by ref.

    When babysit is configured with a single workspace ref (pane mode default),
    multi-surface output is aggregated by cmux read-screen --workspace and
    ALL of it flows through one WorkspaceState entry. The state has no
    per-surface attribution — that is the shared-state caveat.
    """
    # Two consecutive screen captures from a workspace that hosts many surfaces.
    screens = [
        "surface A says: hello\n",
        "surface A says: hello\nsurface B says: world\n",
    ]
    backend = _silent_backend(screens)
    state = WorkspaceState(ref="workspace:17")

    process_workspace(
        backend=backend,
        state=state,
        stale_warn_minutes=15,
        stale_escalate_minutes=30,
        log_path=tmp_path / "log.jsonl",
    )
    first_hash = state.last_screen_hash
    first_change = state.last_change_ts

    process_workspace(
        backend=backend,
        state=state,
        stale_warn_minutes=15,
        stale_escalate_minutes=30,
        log_path=tmp_path / "log.jsonl",
    )

    # Same WorkspaceState updated twice; the hash changed because surface B's
    # output flowed through. There is no per-surface bookkeeping — by design.
    assert state.last_screen_hash != first_hash
    assert state.last_change_ts >= first_change


def test_babysit_handles_mixed_workspace_and_surface_refs(tmp_path: Path):
    """Babysit can monitor multiple refs of either kind in one run."""
    backend = MagicMock()
    backend.read_screen.side_effect = ["w\n", "s\n"]

    workspace_state = WorkspaceState(ref="workspace:17")
    surface_state = WorkspaceState(ref="surface:31")

    process_workspace(
        backend=backend,
        state=workspace_state,
        stale_warn_minutes=15,
        stale_escalate_minutes=30,
        log_path=tmp_path / "log.jsonl",
    )
    process_workspace(
        backend=backend,
        state=surface_state,
        stale_warn_minutes=15,
        stale_escalate_minutes=30,
        log_path=tmp_path / "log.jsonl",
    )

    calls = [c.args[0] for c in backend.read_screen.call_args_list]
    assert calls == ["workspace:17", "surface:31"]
    assert workspace_state.last_screen_hash != ""
    assert surface_state.last_screen_hash != ""
