"""Live-smoke entrypoints for surface-worker-decisions (real cmux + spawned worker).

These drive the REAL spawn path under the cmux Claude wrapper and observe the real
cmux Feed. They are the end-to-end proof that a spawned worker's blocking decision
reaches ``cmux rpc feed.list`` — the headline acceptance of #967 / #971. Exercised at
the SMOKE phase by the coach; the unit/integration tiers cover the pure logic.

Each entrypoint launches a worker through the PRODUCTION launch builders — the
``claude-code`` adapter (now Bash-free, #971) composed with
``spawn._build_cmux_native_command`` — exactly as ``cmd_spawn`` does for the
default cmux-native transport. A worker spawned this way runs under the cmux
wrapper with ``CMUX_SURFACE_ID`` set, so the wrapper injects its
PermissionRequest -> ``cmux hooks feed`` hook and decisions publish to the Feed.

These require a live cmux + claude install and an opt-in (``ATDD_LIVE_SMOKE=1``);
``live_smoke_available()`` guards the SMOKE tests so they skip cleanly in CI. The
captured evidence for a documented run lives in docs/smoke-audit.md per #983.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)


def live_smoke_available() -> Optional[str]:
    """Return ``None`` when the live harness can run, else a skip reason.

    Requires cmux + claude on PATH, a live cmux surface (``CMUX_SURFACE_ID``), and
    the explicit ``ATDD_LIVE_SMOKE=1`` opt-in (so ordinary test runs never spawn a
    real worker). The proof for a CI run lives in docs/smoke-audit.md per #983.
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


def _rpc_feed_list() -> List[Dict[str, Any]]:
    out = subprocess.run(
        ["cmux", "rpc", "feed.list"], capture_output=True, text=True, timeout=20
    )
    if out.returncode != 0:
        return []
    try:
        return json.loads(out.stdout).get("items", [])
    except json.JSONDecodeError as exc:
        _log.debug("feed.list returned non-JSON; treating as empty", extra={"error": str(exc)})
        return []


def _production_launch_command(cwd: Path, seed_prompt: str) -> str:
    """Build the exact launch command cmd_spawn uses for the cmux-native transport."""
    from atdd.coach.commands import spawn

    adapter_command = spawn.ADAPTER_REGISTRY["claude-code"](cwd / ".launch_prompt.txt")
    return spawn._build_cmux_native_command(adapter_command, seed_prompt)


def _spawn_worker_and_wait(
    seed_prompt: str,
    predicate: Callable[[Dict[str, Any], str], bool],
    *,
    timeout_s: int = 200,
) -> Dict[str, Any]:
    """Spawn a real worker via the production builders and poll feed.list until
    ``predicate(item, cwd)`` matches. Always closes the worker's workspace.

    Returns ``{"surfaced": bool, "evidence": <item|all-items>, "cwd": str,
    "launch_command": str}``.
    """
    from atdd.coach.commands import spawn

    cwd = Path("/private/tmp") / f"swd-smoke-{uuid.uuid4().hex[:6]}"
    cwd.mkdir(parents=True, exist_ok=True)
    cwd_str = str(cwd)
    try:
        spawn._pre_trust_worktree(cwd)
    except Exception as exc:
        # Best-effort: a failed pre-trust only risks a trust modal, which the
        # poll loop will simply time out on — log it loudly rather than hide it.
        _log.warning("pre-trust failed", extra={"cwd": str(cwd), "error": str(exc)})

    launch_command = _production_launch_command(cwd, seed_prompt)
    create = subprocess.run(
        ["cmux", "new-workspace", "--cwd", cwd_str, "--command", launch_command,
         "--name", f"swd-smoke-{cwd.name}", "--focus", "false"],
        capture_output=True, text=True, timeout=30,
    )
    ws_ref = None
    if create.returncode == 0 and "workspace:" in create.stdout:
        ws_ref = "workspace:" + create.stdout.split("workspace:")[1].split()[0].strip()

    try:
        if create.returncode != 0:
            raise RuntimeError(f"cmux new-workspace failed: {create.stderr.strip()!r}")
        deadline = time.time() + timeout_s
        seen: List[Dict[str, Any]] = []
        while time.time() < deadline:
            seen = [i for i in _rpc_feed_list() if i.get("cwd") == cwd_str]
            for item in seen:
                if predicate(item, cwd_str):
                    return {
                        "surfaced": True,
                        "evidence": item,
                        "cwd": cwd_str,
                        "launch_command": launch_command,
                    }
            time.sleep(5)
        return {
            "surfaced": False,
            "evidence": seen,
            "cwd": cwd_str,
            "launch_command": launch_command,
        }
    finally:
        if ws_ref:
            subprocess.run(
                ["cmux", "close-workspace", "--workspace", ws_ref],
                capture_output=True, text=True, timeout=20,
            )


def _is_pending_bash_permission(item: Dict[str, Any], cwd: str) -> bool:
    """A genuine surfaced decision: a pending permissionRequest for Bash (not the
    auto-approved `toolUse` telemetry that a safe command like `echo` produces)."""
    status = (item.get("status") or "").lower()
    kind = (item.get("kind") or "").lower()
    return (
        item.get("tool_name") == "Bash"
        and status != "telemetry"
        and ("permission" in kind or status in {"pending", "blocked"})
    )


def _gated_bash_seed() -> str:
    """A deny-pattern bash command Claude never auto-approves (unlike a safe
    `echo`), targeting a nonexistent /tmp path so it is harmless even if ever run."""
    target = f"/private/tmp/swd-{uuid.uuid4().hex[:8]}-absent"
    return f"Use the Bash tool to run exactly this command and nothing else: rm -rf {target}"


def decision_appears_blocked_live_smoke() -> Dict[str, Any]:
    """Spawn a worker the toolkit way, induce a blocking decision, and confirm a
    pending item appears in cmux feed.list (E008-SMOKE-001)."""
    result = _spawn_worker_and_wait(_gated_bash_seed(), _is_pending_bash_permission)
    if not result["surfaced"]:
        raise AssertionError(
            f"no blocking decision surfaced to feed.list; saw: {result['evidence']!r}"
        )
    return result


def bash_decision_surfaces_live_smoke() -> Dict[str, Any]:
    """Confirm a worker's Bash command surfaces as a pending permission decision in
    feed.list (with the command in tool_input) instead of auto-executing (C006-SMOKE-001)."""
    result = _spawn_worker_and_wait(_gated_bash_seed(), _is_pending_bash_permission)
    if not result["surfaced"]:
        raise AssertionError(
            f"Bash command did not surface as a pending decision; saw: {result['evidence']!r}"
        )
    assert "command" in json.dumps(result["evidence"].get("tool_input")), "tool_input lacks the command"
    return result


def launch_argv_matches_policy_live_smoke() -> Dict[str, Any]:
    """Capture a live worker's launch argv and confirm it is the image of the policy:
    Bash absent from --allowedTools, no bypass flag (Y002-SMOKE-001)."""
    from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
        resolve,
    )

    cwd = Path("/private/tmp") / f"swd-argv-{uuid.uuid4().hex[:6]}"
    cwd.mkdir(parents=True, exist_ok=True)
    launch_command = _production_launch_command(cwd, "noop")
    values = resolve("claude-code")

    _, _, after_allowed = launch_command.partition("--allowedTools")
    assert "Bash" not in after_allowed, launch_command
    assert "--dangerously-skip-permissions" not in launch_command
    assert "bypassPermissions" not in launch_command
    for tool in values.allowed_tools:
        assert tool in launch_command, tool
    return {"surfaced": True, "launch_command": launch_command, "cwd": str(cwd)}


def worker_has_active_feed_hook_live_smoke() -> Dict[str, Any]:
    """Confirm a live spawned worker runs under the wrapper with the
    PermissionRequest->feed hook injected (L004-SMOKE-001).

    Proven by a real published item: a worker whose decision reaches feed.list
    necessarily had the hook path active. Also asserts the launch-environment
    preconditions (CMUX_SURFACE_ID + live socket) via the production probe.
    """
    from atdd.mediate_worker_decisions.surface_worker_decisions.src.integration.cmux_hook_probe import (
        CmuxHookProbe,
    )

    presence = CmuxHookProbe().evaluate()
    assert presence.active, f"hook path inactive at launch: {presence.reason}"

    result = _spawn_worker_and_wait(_gated_bash_seed(), _is_pending_bash_permission)
    if not result["surfaced"]:
        raise AssertionError(
            f"worker published no item — hook path not live; saw: {result['evidence']!r}"
        )
    return result


def dispatch_worker_decision_publishes_live_smoke(*, timeout_s: int = 200) -> Dict[str, Any]:
    """Spawn a worker via the REAL dispatch surface path and confirm its gated
    Bash decision publishes to cmux feed.list (E013-SMOKE-001, #1025).

    Drives the production ``_create_surface`` (the ``cmux new-surface --pane`` +
    ``cmux send`` dispatch path), NOT the raw new-workspace standalone spawn — so
    it proves the wrapper Feed hook is live for the DISPATCH spawn specifically
    (the producer half the closed #967 missed). Returns ``{"surfaced": bool,
    "evidence": ..., "cwd": str, "launch_command": str}``.
    """
    from atdd.coach.commands import spawn
    from atdd.coach.utils.multiplexer import CmuxBackend

    cwd = Path("/private/tmp") / f"dispatch-smoke-{uuid.uuid4().hex[:6]}"
    cwd.mkdir(parents=True, exist_ok=True)
    cwd_str = str(cwd)
    try:
        spawn._pre_trust_worktree(cwd)
    except Exception as exc:
        _log.warning("pre-trust failed", extra={"cwd": cwd_str, "error": str(exc)})

    launch_command = _production_launch_command(cwd, _gated_bash_seed())
    backend = CmuxBackend()
    surface_ref = spawn._create_surface(
        backend, worktree=cwd, command=launch_command, name=f"dispatch-smoke-{cwd.name}",
    )
    try:
        deadline = time.time() + timeout_s
        seen: List[Dict[str, Any]] = []
        while time.time() < deadline:
            seen = [i for i in _rpc_feed_list() if i.get("cwd") == cwd_str]
            for item in seen:
                if _is_pending_bash_permission(item, cwd_str):
                    return {"surfaced": True, "evidence": item, "cwd": cwd_str,
                            "launch_command": launch_command}
            time.sleep(5)
        return {"surfaced": False, "evidence": seen, "cwd": cwd_str,
                "launch_command": launch_command}
    finally:
        try:
            backend.close(surface_ref)
        except Exception as exc:
            _log.warning("dispatch-smoke surface cleanup failed",
                         extra={"surface": surface_ref, "error": str(exc)})


if __name__ == "__main__":
    import sys

    skip = live_smoke_available()
    if skip:
        print(f"[skip] {skip}")
        sys.exit(0)
    captured = bash_decision_surfaces_live_smoke()
    print(json.dumps(captured["evidence"], indent=2))
