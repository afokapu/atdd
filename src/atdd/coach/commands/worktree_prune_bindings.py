# URN: component:govern-lifecycle:stale-worktree-bindings-are-cleared:worktree_prune_bindings:backend:presentation
# Runtime: python
# Purpose: `atdd worktree prune-bindings` — report, and on request retire, bindings whose directory is gone (#1894).

"""The operator surface over ``worktree_bindings``.

Reports by default and writes only with ``--apply``, matching ``gc`` and
``relocate``. The survey is the useful half: 104 of 134 bindings on this
repository name a directory that is gone, and an operator should be able to read
that before deciding to act on it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from atdd.coach.commands.worktree_bindings import stale_bindings


def run_prune_bindings(apply: bool = False, quiet: bool = False,
                       control_root: Optional[Path] = None) -> int:
    """Report stale bindings; retire them when *apply*."""
    from atdd.coach.commands.worktree_placement import write_worktree_binding
    from atdd.coach.utils.repo import find_repo_root
    from atdd.state.work_item_reader import WorkItemReader

    repo_root = Path(find_repo_root())
    root = Path(control_root) if control_root else repo_root.parent

    with WorkItemReader(control_root=root) as reader:
        items = reader.all_work_items()

    stale = list(stale_bindings(items))
    if not stale:
        if not quiet:
            print("No stale worktree bindings: every recorded path exists.")
        return 0

    print(f"{len(stale)} work item(s) name a worktree directory that is gone:\n")
    for binding in stale:
        print(f"  {binding.slug}")
        print(f"    {binding.path}")

    if not apply:
        print(
            "\nReport only. Re-run with --apply to retire these bindings.\n"
            "A path that does not exist is false by inspection; clearing it "
            "removes a value already known wrong and changes no phase."
        )
        return 0

    cleared = 0
    for binding in stale:
        try:
            write_worktree_binding(repo_root, binding.slug, "")
            cleared += 1
        except Exception as exc:  # one bad record must not abort the rest
            print(f"  could not clear {binding.slug}: {exc}")
    print(f"\nRetired {cleared} of {len(stale)} stale binding(s).")
    return 0 if cleared == len(stale) else 1
