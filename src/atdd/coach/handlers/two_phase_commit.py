"""Two-phase-commit handler — COMPLETE → MERGED wiring (issue #590).

Wires the COMPLETE → MERGED state transition to the J4 two-phase commit
discipline absorbed from `atdd orchestrate`:
  Phase A: create PR via `atdd pr <N>` (validates default-branch base per #477)
  Phase B: merge via `gh pr merge --squash --delete-branch`
  Phase D: cleanup worktree (best-effort; failure → warn, still MERGED)

Phase C (release tagging) is intentionally omitted: publish.yml owns
tagging on push-to-main (review note 2026-05-11 afokapu; two scenarios
documented in issue #590 comment thread).

Without --auto-merge: escalate to `escalation_channel` and return NOOP
so the COMPLETE state persists pending operator approval. The operator
resumes with: `atdd coach <N> --auto-merge`.

On any pre-merge failure: return ERROR (maps to BLOCKED with rationale).
On cleanup failure: log warning and return HANDLED (already merged).

Spec: atdd-coach-spec-v9.md §4.7 (PR-based COMPLETE → MERGED).
"""
from __future__ import annotations

import subprocess
import sys
from typing import Optional

from atdd.coach.handlers.state_machine import CoachContext, HandlerResult, Phase, Transition


def _create_pr(issue_number: int) -> bool:
    """Invoke `atdd pr <N>`; returns True on success."""
    result = subprocess.run(
        ["atdd", "pr", str(issue_number)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ atdd pr {issue_number} failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    if result.stdout.strip():
        print(result.stdout.strip())
    return True


def _merge_pr() -> tuple[bool, str]:
    """Invoke `gh pr merge --squash --delete-branch`; returns (success, rationale)."""
    result = subprocess.run(
        ["gh", "pr", "merge", "--squash", "--delete-branch"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        print(f"❌ gh pr merge failed: {stderr}", file=sys.stderr)
        return False, stderr
    return True, ""


def _find_worktree_for_issue(issue_number: int) -> Optional[str]:
    """Scan `git worktree list --porcelain` for a path whose branch contains the issue number."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    current_path: Optional[str] = None
    current_branch: Optional[str] = None
    marker = str(issue_number)
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current_path and current_branch and marker in current_branch:
                return current_path
            current_path = line[len("worktree "):]
            current_branch = None
        elif line.startswith("branch "):
            current_branch = line[len("branch "):]
    if current_path and current_branch and marker in current_branch:
        return current_path
    return None


def _cleanup_worktree(worktree_path: str) -> None:
    """Best-effort worktree removal; logs warning on failure (per review note)."""
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", worktree_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(
            f"⚠️  worktree cleanup failed ({worktree_path}): {result.stderr.strip()}",
            file=sys.stderr,
        )


def _send_escalation(issue_number: int, escalation_channel: Optional[str]) -> None:
    """Notify operator that --auto-merge is required to proceed."""
    print(
        f"⏳ Issue #{issue_number} reached COMPLETE but --auto-merge not set. "
        f"Awaiting operator approval. Run: atdd coach {issue_number} --auto-merge",
        file=sys.stderr,
    )
    if escalation_channel:
        print(f"  → escalation channel: {escalation_channel}", file=sys.stderr)


def handle(ctx: CoachContext, transition: Transition) -> HandlerResult:
    """Handle the COMPLETE → MERGED transition.

    With auto_merge=True: create PR, merge, cleanup worktree, return HANDLED.
    Without auto_merge: escalate and return NOOP (COMPLETE stays pending).
    """
    if transition.src != Phase.COMPLETE or transition.dst != Phase.MERGED:
        return HandlerResult.NOOP

    if not ctx.auto_merge:
        _send_escalation(ctx.issue_number, ctx.escalation_channel)
        return HandlerResult.NOOP

    # Phase A: create PR (validates default-branch base per #477)
    if not _create_pr(ctx.issue_number):
        return HandlerResult.ERROR

    # Phase B: merge (squash + delete branch per spec §4.7)
    merge_ok, _ = _merge_pr()
    if not merge_ok:
        return HandlerResult.ERROR

    # Phase D: cleanup worktree (best-effort; failure → warn, still HANDLED)
    worktree_path = _find_worktree_for_issue(ctx.issue_number)
    if worktree_path:
        _cleanup_worktree(worktree_path)

    return HandlerResult.HANDLED
