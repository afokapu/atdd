"""Reviewer handler — N5 wiring (issue #589).

Spawns a reviewer persona at each enabled phase boundary (per `--review-phases`),
waits for the reviewer to submit `atdd agent review`, validates the report against
the schema + hard rules, then routes based on verdict:

  pass    → HandlerResult.HANDLED  (state advances normally)
  concern → judge call site #2 invoked; HandlerResult.HANDLED
  fail    → HandlerResult.ERROR    (triggers coder respawn)

Honors `--skip-review` to bypass all reviewer spawns per
acc:integration-hardening:N5-INTEGRATION-003-skip-review-honored.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import uuid
from typing import Optional

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Transition

_POLL_INTERVAL = float(os.environ.get("ATDD_REVIEWER_POLL_INTERVAL", "1.0"))
_TIMEOUT = float(os.environ.get("ATDD_REVIEWER_TIMEOUT", "3600.0"))


def _runtime_root() -> Path:
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    return Path(env) if env else Path.cwd() / ".atdd" / "runtime"


def _write_reviewer_manifest(agent_dir: Path, agent_id: str, issue: int, phase: str) -> None:
    manifest = {
        "agent_id": agent_id,
        "issue": issue,
        "persona": "reviewer",
        "phase": phase,
    }
    tmp = agent_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, sort_keys=True))
    tmp.replace(agent_dir / "manifest.json")


def _find_review_report(reviewer_agent_dir: Path) -> Optional[dict]:
    """Return the first parseable report from reviews/, or None."""
    reviews_dir = reviewer_agent_dir / "reviews"
    if not reviews_dir.exists():
        return None
    for review_file in sorted(reviews_dir.glob("*.json")):
        try:
            return json.loads(review_file.read_text())
        except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            continue
    return None


def _wait_for_review_report(
    reviewer_agent_dir: Path,
    *,
    timeout: float = _TIMEOUT,
    poll_interval: float = _POLL_INTERVAL,
) -> Optional[dict]:
    """Poll reviews/ until a report appears or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        report = _find_review_report(reviewer_agent_dir)
        if report is not None:
            return report
        time.sleep(poll_interval)
    return None


def _spawn_reviewer(
    ctx: CoachContext,
    transition: Transition,
    reviewer_agent_id: str,
    runtime_root: Path,
) -> None:
    """Spawn the reviewer via the N1 spawn adapter.

    No-ops when `ctx.dry_run`. Errors are logged to stderr and swallowed so
    the handler can proceed to poll for a report (test environments pre-write
    the report without a real spawn).
    """
    if ctx.dry_run:
        return
    try:
        from atdd.coach.commands import spawn as spawn_mod
        from atdd.coach.utils.multiplexer import get_multiplexer

        llm = ctx.persona_llm.get("reviewer") or ctx.llm or "claude-code"
        multiplexer = get_multiplexer(preferred=ctx.multiplexer)
        worktree = Path.cwd()

        spawn_mod.cmd_spawn(
            persona="reviewer",
            llm=llm,
            worktree=worktree,
            issue=ctx.issue_number,
            agent_id=reviewer_agent_id,
            runtime_root=runtime_root,
            phase=transition.dst.value,
            multiplexer=multiplexer,
        )
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"reviewer handler: spawn failed for {reviewer_agent_id}: {exc}",
            file=sys.stderr,
        )


def _route_concern(ctx: CoachContext, report: dict) -> None:
    """Invoke judge call site #2 for a concern verdict (N4/#529)."""
    try:
        from atdd.coach.commands.judge_call_sites import route_reviewer_concern

        route_reviewer_concern(
            review_report=report,
            llm=ctx.judge_llm or ctx.llm or "claude-code",
            coach_run_id=f"coach-{ctx.issue_number}",
        )
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        print(
            f"reviewer handler: judge routing failed: {exc}",
            file=sys.stderr,
        )


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Spawn reviewer at enabled phase boundaries and route on verdict.

    Returns NOOP when skip_review is set or the destination phase is not in
    review_phases. Returns HANDLED on pass/concern verdicts, ERROR on fail or
    timeout.
    """
    if ctx.skip_review:
        return HandlerResult.NOOP

    phase_name = transition.dst.value.lower()
    if phase_name not in ctx.review_phases:
        return HandlerResult.NOOP

    runtime_root = _runtime_root()
    reviewer_agent_id = (
        f"reviewer-{ctx.issue_number}-{phase_name}-{uuid.uuid4().hex[:8]}"
    )
    reviewer_agent_dir = runtime_root / "agents" / reviewer_agent_id
    reviewer_agent_dir.mkdir(parents=True, exist_ok=True)

    _write_reviewer_manifest(
        reviewer_agent_dir,
        reviewer_agent_id,
        ctx.issue_number,
        transition.dst.value,
    )

    _spawn_reviewer(ctx, transition, reviewer_agent_id, runtime_root)

    report = _wait_for_review_report(reviewer_agent_dir)
    if report is None:
        print(
            f"reviewer handler: timeout waiting for report from {reviewer_agent_id}",
            file=sys.stderr,
        )
        return HandlerResult.ERROR

    from atdd.coach.utils.review_report_intake import validate_review_report

    intake = validate_review_report(report)
    if not intake.valid:
        print(
            f"reviewer handler: report validation failed for {reviewer_agent_id}: "
            + "; ".join(intake.error_messages),
            file=sys.stderr,
        )
        return HandlerResult.ERROR

    verdict = report.get("verdict", "")
    if verdict == "pass":
        return HandlerResult.HANDLED
    if verdict == "concern":
        _route_concern(ctx, report)
        return HandlerResult.HANDLED
    # fail or unknown verdict
    return HandlerResult.ERROR
