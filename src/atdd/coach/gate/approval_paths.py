"""Where the operator-approval token lives — resolved identically at mint and at check.

``approval.py`` owns the token's RELATIVE shape (``approval_relpath``) and stays
pure/stdlib-only. This module owns the BASE the relpath is joined onto, and it is
the only thing #1376 moves: from the literal per-worktree cwd to the single shared
Control Root that every other operational ``.atdd/`` reader has resolved through
since #1346 (``atdd.state.paths.resolve_operational_root``).

Why it matters (#1670): the token is a receipt. ``atdd coach approve`` writes it
and ``ApprovalTokenGateCheck`` reads it — from two different call sites, in two
different processes, potentially from two different worktrees of the same project.
If those two resolve the base differently, the receipt is either invisible to the
gate that needs it or readable from a worktree it was never minted for. Both call
sites therefore resolve through :func:`approval_control_root`, so there is exactly
one answer to "where is the token".

Back-compat (#1376 Decision 2): tokens dropped under a child worktree's
``.atdd/runtime/`` BEFORE this change must keep working, so no operator has to
re-approve mid-flight. :func:`locate_approval_token` prefers the Control-Root path
and falls back to the worktree-local one only when the Control-Root token is
absent — a read-side fallback only; new tokens are always MINTED at the Control
Root, so the fallback drains rather than perpetuating the split.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atdd.coach.gate.approval import approval_relpath


@dataclass(frozen=True)
class ApprovalTokenLocation:
    """Where a transition's token was looked for, and which path answered.

    ``path`` is the one a caller should read: the Control-Root path whenever it
    exists (and whenever neither exists, so an absent-token message names the
    canonical location rather than a legacy one), otherwise the worktree-local
    path that back-compat kept alive.
    """

    path: Path
    control_root_path: Path
    worktree_path: Path
    exists: bool
    legacy: bool


def approval_control_root(worktree: Path) -> Path:
    """The Control Root that ``worktree``'s operational ``.atdd/`` resolves to (#1346).

    Degrades to ``worktree`` itself when no Control Root is resolvable — a
    consumer repo with no ``.atdd/`` yet, a hermetic tmp dir, or an ambiguous
    layout. ``resolve_operational_root`` already absorbs every ``StateLayoutError``
    that way, which is what keeps the single-repo and hermetic-test cases behaving
    exactly as they did before #1376.

    Imported lazily so the gate package keeps importing without pulling the state
    layer in — the same deferred-import shape ``SmokeExecutionGateCheck`` uses.
    """
    from atdd.state.paths import resolve_operational_root

    return Path(resolve_operational_root(Path(worktree)))


def approval_token_path(
    worktree: Path, issue_number: int, from_phase: str, to_phase: str
) -> Path:
    """The canonical token path for one transition: Control Root + ``approval_relpath``.

    This is where ``atdd coach approve`` writes and where the gate looks first.
    The relpath's shape is untouched (#1376 Decision 3) — only its base moves.
    """
    return approval_control_root(worktree) / approval_relpath(
        issue_number, from_phase, to_phase
    )


def locate_approval_token(
    worktree: Path, issue_number: int, from_phase: str, to_phase: str
) -> ApprovalTokenLocation:
    """Locate the token for one transition, preferring the shared Control Root.

    Falls back to the worktree-local path only when no Control-Root token exists,
    so a token dropped under a child worktree before #1376 still satisfies the
    gate. When the two resolve to the same directory (single-repo layouts, and
    every hermetic test that hands a bare tmp dir as the worktree) there is one
    path and the fallback is a no-op.
    """
    rel = approval_relpath(issue_number, from_phase, to_phase)
    control_root_path = approval_control_root(worktree) / rel
    worktree_path = Path(worktree) / rel

    if control_root_path.exists():
        return ApprovalTokenLocation(
            path=control_root_path,
            control_root_path=control_root_path,
            worktree_path=worktree_path,
            exists=True,
            legacy=False,
        )
    if worktree_path != control_root_path and worktree_path.exists():
        return ApprovalTokenLocation(
            path=worktree_path,
            control_root_path=control_root_path,
            worktree_path=worktree_path,
            exists=True,
            legacy=True,
        )
    return ApprovalTokenLocation(
        path=control_root_path,
        control_root_path=control_root_path,
        worktree_path=worktree_path,
        exists=False,
        legacy=False,
    )
