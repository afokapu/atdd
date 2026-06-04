"""Live-smoke entrypoints for surface-worker-decisions (real cmux + spawned worker).

These drive the REAL spawn path under the cmux Claude wrapper and observe the real
cmux Feed. They are the end-to-end proof that a spawned worker's blocking decision
reaches ``cmux rpc feed.list`` — the headline acceptance of #967. Exercised at the
SMOKE phase by the coach; the unit/integration tiers cover the pure logic.
"""
from __future__ import annotations

from typing import Any, Dict


def decision_appears_blocked_live_smoke() -> Dict[str, Any]:
    """Spawn a worker the toolkit way, induce a blocking decision, and confirm a
    pending item appears in cmux feed.list (E008-SMOKE-001)."""
    raise NotImplementedError("SMOKE: decision_appears_blocked_live_smoke")


def bash_decision_surfaces_live_smoke() -> Dict[str, Any]:
    """Confirm a worker's Bash command surfaces as a pending permission decision in
    feed.list (with the command in tool_input) instead of auto-executing (C006-SMOKE-001)."""
    raise NotImplementedError("SMOKE: bash_decision_surfaces_live_smoke")


def launch_argv_matches_policy_live_smoke() -> Dict[str, Any]:
    """Capture a live worker's launch argv and confirm it is the image of the policy:
    Bash absent from --allowedTools, no bypass flag (Y002-SMOKE-001)."""
    raise NotImplementedError("SMOKE: launch_argv_matches_policy_live_smoke")


def worker_has_active_feed_hook_live_smoke() -> Dict[str, Any]:
    """Confirm a live spawned worker runs under the wrapper with the
    PermissionRequest->feed hook injected (L004-SMOKE-001)."""
    raise NotImplementedError("SMOKE: worker_has_active_feed_hook_live_smoke")
