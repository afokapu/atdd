"""
`atdd auto-phase` — auto-transition the parent atdd-issue's phase on PR merge.

Issue #355: when a PR closes a parent atdd-issue, advance the parent's phase
label one step per the state machine in CLAUDE.md (RED→GREEN, GREEN→SMOKE,
SMOKE→REFACTOR, REFACTOR→COMPLETE). Driven by GitHub Actions on
`pull_request: closed` with `merged == true`.

Issue #1452: the current phase is read from the **State Store**
(``objects.state``), not from the ``atdd:<PHASE>`` label. The label is a
projection; reading it let a workflow that stamped the label first silence this
path entirely. When store and label disagree, auto-phase now exits non-zero
instead of no-opping green.

Composition:
    compute_next_phase(current)         pure state-machine lookup
    read_store_phase(issue)             objects.state — the source of truth
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
    action: str  # "transition" | "noop" | "divergence"
    reason: Optional[str] = None
    # #1452: the two readings of "what phase is this issue?", kept side by side
    # so a divergence can be reported with both values rather than silently
    # resolved in favour of whichever one was read.
    store_phase: Optional[str] = None
    label_phase: Optional[str] = None


def compute_next_phase(current: Optional[str]) -> Optional[str]:
    """Pure state-machine lookup; returns next phase or None for no-op."""
    if not current:
        return None
    return _NEXT_PHASE.get(current.upper())


def read_store_phase(
    issue_number: int,
    target_dir: Optional[Path] = None,
) -> Optional[str]:
    """The issue's phase from ``objects.state`` — the source of truth (#1452).

    Returns ``None`` when the store is unavailable or does not know this issue,
    which the caller must treat as "cannot decide", never as "no phase".
    """
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=target_dir) as reader:
            state = reader.status(issue_number)
        return str(state).upper() if state else None
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        logger.debug(
            "State Store phase read unavailable",
            extra={"issue": issue_number, "error": str(exc)},
        )
        return None


def resolve_pr_to_transition(
    pr_number: int,
    target_dir: Optional[Path] = None,
) -> AutoPhaseResult:
    """Resolve a PR to its parent issue and compute the next phase.

    #1452: the phase is read from the **State Store** (``objects.state``), not
    from the ``atdd:<PHASE>`` label. The label is a projection, and reading a
    projection is exactly what let a label race silence this code path: a
    workflow with no checkout stamped ``atdd:COMPLETE`` ~11s before this ran,
    auto-phase read that label, found a terminal phase, and no-opped green while
    the store stayed at SMOKE.

    When the store and the label disagree the result is ``action="divergence"``
    — an error state, not a no-op. Something wrote a phase without going through
    ``IssueManager.update``, and continuing would either act on an unearned
    phase or bury the evidence.

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
    label_phase = (resolution.get("phase_label") or "").upper() or None
    store_phase = read_store_phase(issue_number, target_dir=target_dir)

    # Divergence is only decidable when the store actually knows the issue. A
    # store that has never seen it (consumer repo, un-imported work item) is
    # silent, not contradictory — fall back to the label rather than failing a
    # build over a store we cannot read.
    if store_phase is not None and label_phase is not None and store_phase != label_phase:
        return AutoPhaseResult(
            pr_number=pr_number,
            issue_number=issue_number,
            current_phase=store_phase,
            next_phase=None,
            action="divergence",
            reason=(
                f"store/label divergence on issue #{issue_number}: "
                f"objects.state={store_phase} but label=atdd:{label_phase}. "
                "The store is authoritative; the label was written by something "
                "other than IssueManager.update."
            ),
            store_phase=store_phase,
            label_phase=label_phase,
        )

    current_phase = store_phase or label_phase
    next_phase = compute_next_phase(current_phase)

    if next_phase is None:
        if not current_phase:
            reason = "issue has no phase in the store and no atdd phase label"
        else:
            reason = f"phase {current_phase} has no auto-advance"
        return AutoPhaseResult(
            pr_number=pr_number,
            issue_number=issue_number,
            current_phase=current_phase,
            next_phase=None,
            action="noop",
            reason=reason,
            store_phase=store_phase,
            label_phase=label_phase,
        )

    return AutoPhaseResult(
        pr_number=pr_number,
        issue_number=issue_number,
        current_phase=current_phase,
        next_phase=next_phase,
        action="transition",
        store_phase=store_phase,
        label_phase=label_phase,
    )


def run(
    pr_number: int,
    dry_run: bool = False,
    target_dir: Optional[Path] = None,
) -> int:
    """CLI entrypoint. Returns shell exit code."""
    result = resolve_pr_to_transition(pr_number, target_dir=target_dir)

    # #1452: FAIL LOUD. Silence is what let 236 records accumulate — auto-phase
    # exited 0 on a label it did not write, so every merged PR reported green
    # while its store stood still. A divergence is now a red build.
    if result.action == "divergence":
        print(f"Error: PR #{result.pr_number}: {result.reason}", file=sys.stderr)
        print(
            "Repair the projection from the store (the store is the survivor) — "
            "see #1338 for the repair verb. Do NOT hand-write objects.state.",
            file=sys.stderr,
        )
        return 1

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
    # #1309: `atdd issue <N> --status <TO>` was removed in 4.0.0. This is a REAL
    # invocation driven by .github/workflows/atdd-auto-phase.yml on PR merge, so
    # it must name the live command or auto-phase-on-merge breaks in CI.
    cmd = ["atdd", "coach", "transition", str(result.issue_number), result.next_phase]
    proc = subprocess.run(cmd, cwd=target_dir)
    return proc.returncode
