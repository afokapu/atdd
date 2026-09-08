"""`atdd worktree relocate` — move one worktree to where the config says (#1524).

Placement is forward-only (Decision 2): setting `worktree_root` changes where
NEW worktrees land and moves nothing that already exists. This command is how an
existing worktree drains, one at a time, when someone asks — never as a fleet
migration, which is explicitly out of scope on the issue.

The offer declines rather than guesses. 77 of this repo's 113 worktrees carry no
State Store binding and 56 of those are unrecoverable — never atdd-created — so
"I don't know which work item this is" is a real and common answer. Reporting it
as a *failure* is what would send an operator hunting a bug that is not there,
which is why `RelocationOffer` carries a reason and this command prints it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

__all__ = ["run_relocate"]

# Why an offer was declined, said in the operator's terms rather than the
# resolver's. A reason with no entry here is still printed — verbatim — so a
# new decline reason cannot silently render as an empty explanation.
_DECLINED: dict = {
    "unbound": (
        "no work item in the State Store is bound to this directory, so there "
        "is no binding to rewrite and no way to tell which issue owns it.\n"
        "  Relocating it anyway would guess. Move it by hand if you know what "
        "it is, or leave it: an unbound worktree is #1529's problem, not this "
        "command's."
    ),
    "already-placed": (
        "it is already where `worktree_root` says it belongs. Nothing to do."
    ),
}


def run_relocate(
    target: Optional[str] = None, apply: bool = False, quiet: bool = False
) -> int:
    """Report, and optionally perform, this worktree's relocation.

    ``quiet`` suppresses the DECLINE messages only. It exists for the
    post-checkout hook, which fires on every branch switch: an operator who is
    told "already where it belongs" on every checkout stops reading the hook's
    output, and then does not read the one message that mattered.
    """
    from atdd.coach.commands.worktree_placement import (
        relocate_worktree,
        relocation_offer,
        resolve_worktree_root_dir,
    )
    from atdd.coach.utils.repo import find_worktree_root

    worktree = Path(target).expanduser().resolve() if target else Path.cwd().resolve()
    if not worktree.is_dir():
        if quiet:
            return 0
        print(f"Error: {worktree} is not a directory.")
        return 1

    try:
        repo_root = find_worktree_root(worktree)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        if quiet:
            return 0
        print(f"Error: {exc}")
        return 1

    offer = relocation_offer(repo_root, worktree)
    if not offer.offered:
        if quiet:
            return 0
        print(f"Not relocating {offer.source}:")
        print(f"  {_DECLINED.get(offer.reason, offer.reason)}")
        # Declining is a correct outcome, not an error. Exiting non-zero here
        # would make "already where it belongs" fail a script that relocates
        # opportunistically.
        return 0

    print(f"  from: {offer.source}")
    print(f"    to: {offer.destination}")
    print(f"  root: {resolve_worktree_root_dir(repo_root)}  (worktree_root)")

    if not apply:
        print("\nDry run. Re-run with --apply to move it.")
        return 0

    # `relocate_worktree` re-reads the binding and moves from the path the STORE
    # names, not from `offer.source`. Passing the destination only is deliberate:
    # it is the one value this command decides.
    try:
        moved = relocate_worktree(repo_root, offer.slug, offer.destination)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # The move is transactional — a failed store write rolls the git move
        # back — so there is nothing half-applied to report or clean up here.
        print(f"\nError: relocation failed, nothing was changed: {exc}")
        return 1

    print(f"\nRelocated to {moved}")
    if Path.cwd().resolve() == offer.source:
        # The shell's cwd is now a path that no longer exists. Saying so beats
        # letting the next command fail with a confusing ENOENT.
        print(f"  Your shell is still in the old path. Run: cd {moved}")
    return 0
