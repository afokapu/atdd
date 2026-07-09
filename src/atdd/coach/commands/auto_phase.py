"""
`atdd auto-phase` — auto-transition the parent atdd-issue's phase on PR merge.

Issue #355: when a PR closes a parent atdd-issue, advance the parent's phase
label one step per the state machine in CLAUDE.md (RED→GREEN, GREEN→SMOKE,
SMOKE→REFACTOR, REFACTOR→COMPLETE). Driven by GitHub Actions on
`pull_request: closed` with `merged == true`.

Composition:
    compute_next_phase(current)         pure state-machine lookup
    resolve_pr_to_transition(pr)        PR → AutoPhaseResult (no side effects)
    run(pr_number, dry_run=False)       CLI entrypoint; calls
                                        `atdd coach transition <N> <NEXT>` unless dry-run
"""
from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from atdd.coach.commands.pr import PRManager

logger = logging.getLogger(__name__)


# Single-step transitions on PR merge. Pre-implementation phases (INIT,
# PLANNED) and BLOCKED do not auto-advance — operator must transition
# manually. Terminal phases (COMPLETE, OBSOLETE) are no-ops.
_NEXT_PHASE = {
    "RED": "GREEN",
    "GREEN": "SMOKE",
    "SMOKE": "REFACTOR",
    "REFACTOR": "COMPLETE",
}


@dataclass
class AutoPhaseResult:
    pr_number: int
    issue_number: Optional[int]
    current_phase: Optional[str]
    next_phase: Optional[str]
    action: str  # "transition" | "noop"
    reason: Optional[str] = None


def compute_next_phase(current: Optional[str]) -> Optional[str]:
    """Pure state-machine lookup; returns next phase or None for no-op."""
    if not current:
        return None
    return _NEXT_PHASE.get(current.upper())


def resolve_pr_to_transition(
    pr_number: int,
    target_dir: Optional[Path] = None,
) -> AutoPhaseResult:
    """Resolve a PR to its parent issue and compute the next phase.

    No side effects — safe to call from tests and dry-run.
    """
    manager = PRManager(target_dir=target_dir)
    resolution = manager.resolve_linked_issue(pr_number)
    if resolution is None:
        return AutoPhaseResult(
            pr_number=pr_number,
            issue_number=None,
            current_phase=None,
            next_phase=None,
            action="noop",
            reason="no linked issue",
        )

    issue_number = resolution.get("issue_number")
    current_phase = resolution.get("phase_label")
    next_phase = compute_next_phase(current_phase)

    if next_phase is None:
        if not current_phase:
            reason = "no atdd phase label on issue"
        else:
            reason = f"phase {current_phase} has no auto-advance"
        return AutoPhaseResult(
            pr_number=pr_number,
            issue_number=issue_number,
            current_phase=current_phase,
            next_phase=None,
            action="noop",
            reason=reason,
        )

    return AutoPhaseResult(
        pr_number=pr_number,
        issue_number=issue_number,
        current_phase=current_phase,
        next_phase=next_phase,
        action="transition",
    )


def run(
    pr_number: int,
    dry_run: bool = False,
    target_dir: Optional[Path] = None,
) -> int:
    """CLI entrypoint. Returns shell exit code."""
    result = resolve_pr_to_transition(pr_number, target_dir=target_dir)

    if result.action == "noop":
        print(
            f"PR #{result.pr_number}: no-op — {result.reason}",
            file=sys.stdout,
        )
        return 0

    msg = (
        f"PR #{result.pr_number} → issue #{result.issue_number}: "
        f"{result.current_phase} → {result.next_phase}"
    )
    if dry_run:
        print(f"[dry-run] {msg}")
        return 0

    print(msg)
    cmd = ["atdd", "issue", str(result.issue_number), "--status", result.next_phase]
    proc = subprocess.run(cmd, cwd=target_dir)
    return proc.returncode
