"""ATDD Control Root resolver + layout guard (#1168 Phase 1, #1177).

The **ATDD Control Root** is the local directory that owns ``.atdd/`` and
therefore the State Store. It is distinct from a *Git worktree root* (a concrete
checkout) and from extension *workspace providers*. Two layouts are supported:

- **single-repo mode** — the Control Root *is* the Git worktree root; the store
  lives at ``repo/.atdd/state/state.sqlite``. This is today's layout.
- **sibling-worktree mode** — the Control Root is a parent directory and the
  Git worktree roots are children (``project/main/``, ``project/worktree1/``)
  that share one ``project/.atdd/state/state.sqlite``.

If both a parent ``.atdd/`` and a child-worktree ``.atdd/`` exist, the resolver
**fails loudly** rather than guess — a split-brain State Store is worse than an
error.

Dependency discipline: stdlib only (``os``, ``pathlib``, ``logging``).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

_log = logging.getLogger(__name__)

ATDD_DIR = ".atdd"
#: State Store path relative to the Control Root (#1168 Decision #2).
STATE_STORE_RELATIVE = Path(ATDD_DIR) / "state" / "state.sqlite"
#: Env override for the Control Root (resolver rule #1).
CONTROL_ROOT_ENV = "ATDD_CONTROL_ROOT"


class LayoutMode(str, Enum):
    """How the Control Root relates to the Git worktree root."""

    SINGLE_REPO = "single-repo"
    SIBLING_WORKTREE = "sibling-worktree"


class StateLayoutError(Exception):
    """Base for Control Root / layout resolution failures."""


class AmbiguousControlRootError(StateLayoutError):
    """Both a parent ``.atdd/`` and a child-worktree ``.atdd/`` exist.

    Resolving either would risk split-brain operational state, so the resolver
    refuses to choose. The operator must pick a layout or run the migration.
    """

    def __init__(self, parent_atdd: Path, child_atdd: Path) -> None:
        self.parent_atdd = Path(parent_atdd)
        self.child_atdd = Path(child_atdd)
        super().__init__(
            "Ambiguous ATDD Control Root.\nFound both:\n"
            f"  {self.parent_atdd}\n  {self.child_atdd}\n"
            "Choose one layout or run the migration command."
        )


class ControlRootNotFoundError(StateLayoutError):
    """No ``.atdd/`` was found at or above the starting directory."""

    def __init__(self, start: Path) -> None:
        self.start = Path(start)
        super().__init__(
            f"No ATDD Control Root (.atdd/) found at or above {self.start}. "
            "Run `atdd init` to create one."
        )


@dataclass(frozen=True)
class ControlRootResolution:
    """The resolved layout for a given starting directory."""

    control_root: Path
    git_worktree_root: Optional[Path]
    layout_mode: LayoutMode

    @property
    def state_store_path(self) -> Path:
        """Absolute path to the State Store SQLite file."""
        return self.control_root / STATE_STORE_RELATIVE

    @property
    def state_store_exists(self) -> bool:
        return self.state_store_path.is_file()


def _has_atdd(directory: Path) -> bool:
    return (directory / ATDD_DIR).is_dir()


def git_worktree_root(start: Path) -> Optional[Path]:
    """Return the nearest enclosing Git worktree root at or above ``start``.

    A worktree root is identified by a ``.git`` entry (a directory for a primary
    checkout, or a file for a linked worktree). Returns ``None`` if no ``.git``
    is found while walking upward — this keeps the resolver hermetically
    testable without invoking git.
    """
    start = Path(start).resolve()
    for directory in (start, *start.parents):
        git_entry = directory / ".git"
        if git_entry.is_dir() or git_entry.is_file():
            return directory
    return None


def resolve_control_root(
    start: Path,
    env: Optional[Mapping[str, str]] = None,
) -> ControlRootResolution:
    """Resolve the ATDD Control Root for ``start`` per #1168's resolver rules.

    Order (see #1168 "Control Root Resolver Rules"):

    1. ``ATDD_CONTROL_ROOT`` override, if set.
    2. Identify the enclosing Git worktree root.
    3. worktree has ``.atdd/`` and parent does not → single-repo.
    4. parent has ``.atdd/`` and current is a child worktree → sibling-worktree.
    5. both parent and worktree ``.atdd/`` exist → fail loudly.
    6. otherwise walk upward for any ``.atdd/`` (best-effort fallback) else raise.
    """
    env = os.environ if env is None else env
    start = Path(start).resolve()

    # Rule 1 — explicit override wins.
    override = env.get(CONTROL_ROOT_ENV)
    if override:
        root = Path(override).expanduser().resolve()
        gwr = git_worktree_root(start)
        mode = (
            LayoutMode.SINGLE_REPO
            if gwr is not None and gwr == root
            else LayoutMode.SIBLING_WORKTREE
        )
        _log.debug(
            "control root from env override",
            extra={"env": CONTROL_ROOT_ENV, "control_root": str(root), "layout_mode": mode.value},
        )
        return ControlRootResolution(control_root=root, git_worktree_root=gwr, layout_mode=mode)

    # Rule 2 — locate the enclosing Git worktree root.
    gwr = git_worktree_root(start)
    if gwr is not None:
        worktree_has = _has_atdd(gwr)
        parent = gwr.parent
        parent_has = _has_atdd(parent)

        # Rule 5 — ambiguous parent + child .atdd/.
        if worktree_has and parent_has:
            raise AmbiguousControlRootError(parent / ATDD_DIR, gwr / ATDD_DIR)
        # Rule 3 — single-repo.
        if worktree_has:
            return ControlRootResolution(gwr, gwr, LayoutMode.SINGLE_REPO)
        # Rule 4 — sibling-worktree (parent owns the Control Root).
        if parent_has:
            return ControlRootResolution(parent, gwr, LayoutMode.SIBLING_WORKTREE)

    # Rule 6 — fallback: walk upward for any .atdd/.
    for directory in (start, *start.parents):
        if _has_atdd(directory):
            mode = (
                LayoutMode.SINGLE_REPO
                if gwr is not None and gwr == directory
                else LayoutMode.SIBLING_WORKTREE
            )
            return ControlRootResolution(directory, gwr, mode)

    raise ControlRootNotFoundError(start)


def check_layout(control_root: Path) -> list[str]:
    """Validate that the filesystem layout under ``control_root`` is legal.

    Returns a list of human-readable violation strings (empty == legal). The
    central rule for sibling-worktree mode: there must be exactly ONE State
    Store (at the Control Root) — no child Git worktree may carry its own
    ``.atdd/state/state.sqlite`` (that would be split-brain operational state).
    """
    control_root = Path(control_root).resolve()
    violations: list[str] = []

    if not _has_atdd(control_root):
        violations.append(f"Control Root has no {ATDD_DIR}/ directory: {control_root}")
        return violations

    # Scan immediate children that are Git worktree roots for a forbidden,
    # independently-rooted State Store.
    for child in sorted(p for p in control_root.iterdir() if p.is_dir()):
        if child == control_root:
            continue
        git_entry = child / ".git"
        is_worktree = git_entry.is_dir() or git_entry.is_file()
        if not is_worktree:
            continue
        rogue_store = child / STATE_STORE_RELATIVE
        if rogue_store.is_file():
            violations.append(
                "Per-worktree State Store detected (sibling-worktree mode allows only one, "
                f"at the Control Root): {rogue_store} — run `atdd state migrate-layout`."
            )

    return violations
