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
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)


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


def scoping_honored_live_smoke() -> Dict[str, Any]:
    """Spawn a post-#1062 worker; run a safe command and a gated command.

    Returns evidence with ``safe_surfaced`` (must be False — auto-ran, no Feed item)
    and ``gated_surfaced`` (must be True — published a ``permissionRequest``), proving
    Claude Code honors the comma-delimited scoped allow-list at runtime (C010).
    """
    raise NotImplementedError(
        "RED #1076 (C010-SMOKE): GREEN spawns a real worker and observes feed.list "
        "for the safe vs gated command partition"
    )


def mediation_attach_gate_live_smoke() -> Dict[str, Any]:
    """Spawn a worker that publishes a gated decision; run the gate with/without a daemon.

    Returns evidence with ``handled_when_attached`` (must be True) and
    ``handled_when_unattached`` (must be False — flagged unmediated, not silently
    HANDLED), proving the gate asserts a real attach before HANDLED (M006).
    """
    raise NotImplementedError(
        "RED #1076 (M006-SMOKE): GREEN runs the S0 gate against a real worker with "
        "and without an attached daemon"
    )
