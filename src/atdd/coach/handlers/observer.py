"""Observer handler — L1 wiring (issue #589).

Co-spawns an L1 observer thread alongside the current phase agent at every
state-machine transition. Records the observer thread identity in
`observer_pid.json` so downstream consumers can verify co-spawn per
acc:integration-hardening:L1-INTEGRATION-001-observer-alongside-agent.

Corrections route through the cli-return injection path (L1 default).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition


def _runtime_root() -> Path:
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    return Path(env) if env else Path.cwd() / ".atdd" / "runtime"


def _find_phase_agent_id(issue_number: int, runtime_root: Path) -> Optional[str]:
    """Return the most recently created non-reviewer agent_id for this issue."""
    agents_dir = runtime_root / "agents"
    if not agents_dir.exists():
        return None
    candidates: list[tuple[float, str]] = []
    for entry in agents_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            continue
        if data.get("issue") == issue_number and data.get("persona") != "reviewer":
            candidates.append((entry.stat().st_mtime, entry.name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Co-spawn an L1 observer thread for the current phase agent.

    Finds the most recent non-reviewer agent for `ctx.issue_number`, starts
    an Observer thread, and writes `observer_pid.json` to the agent dir.
    Returns NOOP when dry_run or when no phase agent exists yet.
    """
    if ctx.dry_run:
        return HandlerResult.NOOP

    runtime_root = _runtime_root()
    agent_id = _find_phase_agent_id(ctx.issue_number, runtime_root)
    if agent_id is None:
        return HandlerResult.NOOP

    from atdd.coach.commands.observer import Observer

    rules_dir = Path.cwd() / ".atdd" / "observer" / "rules"
    obs = Observer(
        agent_id=agent_id,
        runtime_dir=runtime_root,
        rules_dir=rules_dir if rules_dir.exists() else None,
    )
    obs.load_rules()
    obs.start()

    agent_dir = runtime_root / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    pid_record = {
        "agent_id": agent_id,
        "observer_thread_ident": obs._thread.ident if obs._thread else None,
        "phase": transition.dst.value,
    }
    pid_file = agent_dir / "observer_pid.json"
    pid_file.write_text(json.dumps(pid_record, indent=2, sort_keys=True))

    return HandlerResult.HANDLED
