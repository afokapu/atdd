"""Staged enforcement of worktree placement (#1524, Decision 4).

Decision 4 asks for a git hook that warns for one release and blocks after,
"so an agent is never walled off mid-flow". The staging is a config key rather
than a date or a version comparison, because a time bomb would flip on its own
in a repo whose worktrees had not finished draining — which IS walling an agent
off mid-flow, just on a schedule nobody was watching.

    worktree_placement_enforcement: warn   # default: report, never refuse
                                    block  # refuse a push from a misplaced worktree
                                    off    # say nothing

`warn` is the default and the whole of the first release. Moving a repo to
`block` is a deliberate act taken once its worktrees have drained via
`atdd worktree relocate`.

Two hooks, two stages, for a reason:

* **post-checkout** carries the warning. It is the hook `git worktree add` fires
  in the new worktree, so it speaks at the moment a misplaced worktree comes
  into existence — the one moment the operator is thinking about placement. Git
  ignores its exit code, so it structurally cannot refuse anything.
* **pre-push** carries the block. It is the only placement-relevant hook whose
  refusal is recoverable without losing work: the commits are already made, the
  worktree still exists, and `atdd worktree relocate --apply` clears it. Blocking
  a COMMIT would strand work an agent had just done, which is the failure
  Decision 4 names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

__all__ = ["ENFORCEMENT_DEFAULT", "resolve_enforcement", "placement_block_reason"]

ENFORCEMENT_DEFAULT = "warn"
_VALID = ("off", "warn", "block")


def resolve_enforcement(repo_root: Path) -> str:
    """The configured enforcement stage, defaulting to ``warn``.

    An unrecognised value reads as the default rather than raising. A hook is
    the worst possible place to discover a typo in a config key: the operator
    would be refused, with a traceback, at push time.
    """
    from atdd.coach.commands.worktree_placement import _config

    value = str(_config(repo_root).get("worktree_placement_enforcement") or "").strip()
    return value.lower() if value.lower() in _VALID else ENFORCEMENT_DEFAULT


def placement_block_reason(cwd: Optional[Path] = None) -> Optional[str]:
    """Why this push should be refused, or None to allow it.

    Returns None for every case that is not an unambiguous, fixable violation —
    enforcement `off` or `warn`, an unbound worktree, the primary checkout, a
    repo that configured no `worktree_root`, and any error at all. A gate that
    fires on a case the operator cannot act on teaches them to reach for a
    bypass, which is how enforcement stops meaning anything (#1442).
    """
    try:
        from atdd.coach.commands.worktree_placement import placement_drift_notice
        from atdd.coach.utils.repo import find_worktree_root

        worktree = Path(cwd) if cwd else Path.cwd()
        repo_root = find_worktree_root(worktree)
        if resolve_enforcement(repo_root) != "block":
            return None

        # Exactly the same predicate the warning uses. Enforcement that could
        # disagree with the warning that preceded it would refuse a push for a
        # reason the operator was never shown.
        drift = placement_drift_notice(worktree)
        if not drift:
            return None
        return (
            f"{drift}\n"
            f"   (worktree_placement_enforcement: block — set it to `warn` in\n"
            f"    .atdd/config.yaml to downgrade this to a notice)"
        )
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # Fail OPEN, deliberately, and only here. This gate protects a layout
        # convention, not a correctness invariant: refusing every push in a repo
        # where the check itself is broken would cost far more than the
        # misplaced directory it exists to prevent.
        return None
