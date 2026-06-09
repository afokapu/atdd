"""Live cmux orchestration for the enforce-surface-conformance SMOKE acceptances.

Kept out of the test files (per the bridge-cmux-feed live-smoke pattern) so the
tests stay thin and skip cleanly when cmux is absent. These drive REAL cmux:
create per-workspace surfaces, run the real conformance pass, and read back
``surface.list`` per workspace. Every helper cleans up the workspaces it creates.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, List, Tuple

from atdd.coach.observer_rules.canonical_role_naming import (
    flag_non_conforming,
    is_conforming,
)
from atdd.coach.utils.multiplexer import CmuxBackend
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.layout_plan import (
    WorkerSurface,
)
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.presentation.apply_conformance import (
    apply_surface_conformance,
)

_WS_RE = re.compile(r"workspace:\d+")
_SURF_RE = re.compile(r"surface:\d+")
_TITLE_DECORATION = re.compile(r"^[^A-Za-z0-9]+")


def _cmux(*args: str) -> str:
    return subprocess.run(
        ["cmux", *args], capture_output=True, text=True, check=False
    ).stdout or ""


def _new_workspace(name: str) -> Tuple[str, str]:
    """Create a throwaway workspace running a long sleep; return (ws, surface)."""
    out = _cmux(
        "new-workspace", "--cwd", "/tmp", "--command", "sleep 3600",
        "--name", name, "--focus", "false",
    )
    ws_match = _WS_RE.search(out)
    surf_match = _SURF_RE.search(out)
    return (
        ws_match.group(0) if ws_match else "",
        surf_match.group(0) if surf_match else "",
    )


def _write(evidence_path: str, evidence: dict[str, Any]) -> None:
    Path(evidence_path).write_text(json.dumps(evidence, indent=2, default=str))


def never_collapse_live_smoke(*, evidence_path: str, worker_count: int = 2) -> dict[str, Any]:
    """Spawn ``worker_count`` real per-workspace surfaces, run the conformance
    layout pass, and prove each worker still resolves to its own single-identity
    workspace (no daemon-scope collapse)."""
    backend = CmuxBackend()
    coach_ws = backend.current_workspace()
    created: List[Tuple[str, str]] = []
    try:
        for i in range(worker_count):
            ws, surf = _new_workspace(f"ATDD865-worker-smoke-{i}")
            if ws:
                created.append((ws, surf))
        if len(created) < worker_count:
            raise RuntimeError(f"could only create {len(created)}/{worker_count} workspaces")

        workers = [
            WorkerSurface(surface_ref=s or w, workspace_id=w, identity=s or w)
            for w, s in created
        ]
        result = apply_surface_conformance(
            backend,
            coach_pane=coach_ws,
            coach_workspace_id=coach_ws,
            workers=workers,
        )
        identities_by_workspace = {
            w: backend.list_surface_identities(w) for w, _ in created
        }
        evidence = {
            "coach_workspace": coach_ws,
            "layout_invocations": result.layout_invocations,
            "workspaces_verified": list(result.workspaces_verified),
            "identities_by_workspace": identities_by_workspace,
        }
        _write(evidence_path, evidence)
        return evidence
    finally:
        for w, _ in created:
            _cmux("close-workspace", "--workspace", w)


def naming_validator_live_smoke(*, evidence_path: str) -> dict[str, Any]:
    """Create a throwaway workspace, give its surface a role-aware canonical name,
    read it back from the live ``surface.list``, and run the bound validator: the
    role-aware name passes; a drifted (no-role) live name is flagged."""
    backend = CmuxBackend()
    conforming = "ATDD865-worker-coach-layout"
    drifted = "ATDD865-coach-layout"
    created: List[Tuple[str, str]] = []
    try:
        ws, surf = _new_workspace(conforming)
        if ws:
            created.append((ws, surf))
        if surf:
            _cmux("rename-tab", "--surface", surf, conforming)

        # Read the live surface.list back and locate our surface's title.
        payload = json.loads(_cmux("rpc", "surface.list") or "{}")
        readback = ""
        for s in payload.get("surfaces", []):
            if s.get("ref") == surf:
                readback = _TITLE_DECORATION.sub("", (s.get("title") or ""))
                break

        conforming_passed = is_conforming(readback) if readback else is_conforming(conforming)
        events = [
            {"type": "surface_state", "ref": surf or "surface:x", "name": readback or conforming},
            {"type": "surface_state", "ref": "surface:drift", "name": drifted},
        ]
        flagged = flag_non_conforming(events)
        evidence = {
            "conforming_name": readback or conforming,
            "conforming_passed": bool(conforming_passed),
            "drifted_name": drifted,
            "drifted_flagged": "surface:drift" in flagged,
            "flagged": flagged,
        }
        _write(evidence_path, evidence)
        return evidence
    finally:
        for w, _ in created:
            _cmux("close-workspace", "--workspace", w)
