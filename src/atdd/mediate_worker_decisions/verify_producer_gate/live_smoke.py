"""Live-smoke entrypoints for verify-producer-gate (real cmux + spawned worker, #1076).

These drive the REAL post-#1062 spawn path under the cmux Claude wrapper and observe
the real cmux Feed — the S0 gate's live proof. They require a live cmux + claude
install and an opt-in (``ATDD_LIVE_SMOKE=1``); ``live_smoke_available()`` guards the
SMOKE tests so they skip cleanly in CI. The captured evidence for a documented run
lives in docs/smoke-audit.md.

STUB (RED #1076): the skip guard is real (so the SMOKE tests collect and skip
cleanly); the two entrypoints are NotImplementedError until GREEN wires them to the
production spawn + feed.list + daemon-attach state.
"""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)


def _safe_command_seed() -> str:
    """Seed a worker to run a freedom-layer pre-authorized command (must auto-run)."""
    return (
        "Use the Bash tool to run exactly this command and nothing else: "
        "pytest --version"
    )


def live_smoke_available() -> Optional[str]:
    """Return ``None`` when the live harness can run, else a skip reason.

    Requires cmux + claude on PATH, a live cmux surface (``CMUX_SURFACE_ID``), and
    the explicit ``ATDD_LIVE_SMOKE=1`` opt-in (so ordinary test runs never spawn a
    real worker).
    """
    if os.environ.get("ATDD_LIVE_SMOKE") != "1":
        return "live smoke is opt-in: set ATDD_LIVE_SMOKE=1 (needs a live cmux surface)"
    if not shutil.which("cmux"):
        return "cmux not on PATH"
    if not shutil.which("claude"):
        return "claude not on PATH"
    if not os.environ.get("CMUX_SURFACE_ID"):
        return "not running under a live cmux surface (CMUX_SURFACE_ID unset)"
    return None


def scoping_honored_live_smoke(*, safe_timeout_s: int = 60) -> Dict[str, Any]:
    """Spawn post-#1062 workers via the production builders; run a safe command and a
    gated command, observing the real cmux Feed (C010-SMOKE-001).

    Reuses the proven surface-worker-decisions spawn harness (no mocks). The gated
    command must surface a pending ``permissionRequest``; the safe pre-authorized
    command must auto-run with NO pending item — proving Claude Code honors the
    comma-delimited scoped allow-list at runtime. Returns ``{"safe_surfaced": bool,
    "gated_surfaced": bool, "gated_evidence": ..., "safe_cwd": str}``.
    """
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        _gated_bash_seed,
        _is_pending_bash_permission,
        _spawn_worker_and_wait,
    )

    # A gated command surfaces a pending permissionRequest the daemon can mediate.
    gated = _spawn_worker_and_wait(_gated_bash_seed(), _is_pending_bash_permission)
    # A freedom-layer safe command auto-runs: no pending item appears before timeout.
    safe = _spawn_worker_and_wait(
        _safe_command_seed(), _is_pending_bash_permission, timeout_s=safe_timeout_s
    )

    result = {
        "safe_surfaced": bool(safe["surfaced"]),
        "gated_surfaced": bool(gated["surfaced"]),
        "gated_evidence": gated["evidence"],
        "safe_cwd": safe["cwd"],
    }
    if result["safe_surfaced"]:
        raise AssertionError(
            f"safe pre-authorized command surfaced a Feed decision (scoping NOT "
            f"honored): {safe['evidence']!r}"
        )
    if not result["gated_surfaced"]:
        raise AssertionError(
            f"gated command did not surface a permissionRequest: {gated['evidence']!r}"
        )
    return result


def mediation_attach_gate_live_smoke() -> Dict[str, Any]:
    """Spawn a worker that publishes a real gated decision, then run the production
    S0 gate against it with and without an attached daemon (M006-SMOKE-001).

    Drives real production wiring end-to-end: the surface-worker-decisions spawn
    harness produces a genuine published ``permissionRequest``; the real
    ``evaluate_mediation`` gate is run against it through a real
    ``ManagerRegistry``-backed attach probe (the registry record IS how an attached
    daemon is represented — full daemon-process liveness is covered by coach-runtime
    M004/M005). Returns ``{"handled_when_attached": bool, "handled_when_unattached":
    bool, "workspace_id": str}``.
    """
    from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
        ManagedDaemon,
    )
    from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
        ManagerRegistry,
    )
    from atdd.mediate_worker_decisions.surface_worker_decisions.live_smoke import (
        _gated_bash_seed,
        _is_pending_bash_permission,
        _spawn_worker_and_wait,
    )
    from atdd.mediate_worker_decisions.verify_producer_gate.src.application.verify_producer_gate import (
        evaluate_mediation,
    )
    from atdd.mediate_worker_decisions.verify_producer_gate.src.integration.manager_registry_attach_probe import (
        ManagerRegistryAttachProbe,
    )

    # A real spawned worker publishes a genuine gated decision to the Feed.
    spawned = _spawn_worker_and_wait(_gated_bash_seed(), _is_pending_bash_permission)
    if not spawned["surfaced"]:
        raise AssertionError(
            f"no gated decision published to feed.list: {spawned['evidence']!r}"
        )
    item = spawned["evidence"]
    workspace = item.get("workstream_id") or spawned["cwd"]
    decision = {
        "request_id": item.get("request_id"),
        "workspace_id": workspace,
        "tool_name": item.get("tool_name"),
    }

    # A real ManagerRegistry-backed attach probe: load(workspace) is the attach signal.
    root = Path("/private/tmp") / f"vpg-attach-{uuid.uuid4().hex[:6]}"
    registry = ManagerRegistry(root)
    probe = ManagerRegistryAttachProbe(registry)

    # Unattached arm: no manager record for the workspace -> UNMEDIATED, not HANDLED.
    unattached = evaluate_mediation(decision, probe)

    # Attached arm: a real ManagerRegistry record for the workspace -> HANDLED.
    registry.save(
        ManagedDaemon(
            workspace_id=workspace,
            daemon_workspace=f"workspace:daemon-{uuid.uuid4().hex[:6]}",
            lock_path=str(root / "lock"),
            escalations_path=str(root / "escalations.jsonl"),
            verdicts_path=str(root / "verdicts.jsonl"),
        )
    )
    attached = evaluate_mediation(decision, probe)

    result = {
        "handled_when_attached": bool(attached.handled),
        "handled_when_unattached": bool(unattached.handled),
        "workspace_id": workspace,
    }
    if not result["handled_when_attached"]:
        raise AssertionError("confirmed attach did not record HANDLED")
    if result["handled_when_unattached"]:
        raise AssertionError(
            "attach failure recorded HANDLED — unmediated worker miscounted (#1084/A1)"
        )
    return result
