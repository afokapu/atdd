# URN: component:govern-lifecycle:stale-worktree-bindings-are-cleared:worktree_bindings:backend:application
# Runtime: python
# Purpose: See and retire a work item's worktree_path when the directory it names is gone (#1894).

"""Stale worktree bindings — the store asserting a directory that is not there.

``data.worktree_path`` is written when a worktree is created and rewritten when
it relocates (``worktree_placement.write_worktree_binding``). Nothing clears it.
``git worktree remove`` knows nothing about the State Store, so every removal
leaves a binding pointing at a path that no longer exists.

Measured 2026-09-10: 132 work items carry a worktree_path; 104 name a directory
that is gone. 73 of those appeared in a single afternoon of ordinary correct
maintenance. That rate is why this is a leak rather than a backlog.

STALE MEANS THE DIRECTORY IS ABSENT. Not that the work item is COMPLETE, not
that its branch merged — a finished issue whose worktree is still checked out is
an ordinary state, and neither the phase nor the branch is evidence about the
filesystem. Keying on anything else would unbind live work.

AN ABSENT BINDING IS A DIFFERENT DEFECT. A work item carrying no worktree_path
asserts nothing false; it is the untracked half of #1529, it needs an operator to
say which issue owns which directory, and it is deliberately not reported here.
Mixing a mechanical clear with a judgement call is how the judgement gets skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

_BINDING_FIELD = "worktree_path"


@dataclass(frozen=True)
class StaleBinding:
    """One work item asserting a directory that does not exist."""

    slug: str
    path: str


def _bound_path(record: Mapping[str, Any]) -> str:
    """The worktree_path this record asserts, or "" when it asserts none."""
    return str(record.get(_BINDING_FIELD) or "").strip()


def stale_bindings(records: Iterable[Mapping[str, Any]]) -> Iterator[StaleBinding]:
    """Every record whose ``worktree_path`` names an absent directory.

    Pure over the records and the filesystem, so the survey is testable without a
    store and safe to run before anyone decides to act on it.
    """
    for record in records:
        path = _bound_path(record)
        if not path:
            continue
        if Path(path).exists():
            continue
        yield StaleBinding(slug=str(record.get("slug") or ""), path=path)


def clear_binding(record: Mapping[str, Any]) -> dict:
    """A copy of *record* with the stale binding retired, everything else intact.

    Returns a new mapping rather than mutating: the caller holds a record read
    from the store, and rewriting it in place is how a repair clobbers a field a
    parallel session wrote between the read and the write.

    The phase and state are untouched — retiring a path that does not exist is
    not a lifecycle event.
    """
    cleared = dict(record)
    cleared[_BINDING_FIELD] = ""
    return cleared
