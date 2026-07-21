"""Config-driven worktree placement — the single seam that decides where a
worktree lives (issue #1524).

Before this module, seven call sites each derived a worktree path independently,
every one of them hardcoding the flat-sibling layout:

    branch.py:418           target_dir.parent / worktree_dir_name        create
    branch.py:604           target_dir.parent / f"{prefix}-{slug}"       remove fallback
    issue_lifecycle.py:156  target_dir.parent / worktree_dir_name        existing lookup
    issue_lifecycle.py:178  target_dir.parent / f"{prefix}-{slug}"       create (2nd path)
    session_template.py:225 f"../{branch.replace('/', '-')}"             launch prompt
    worktree_gc.py:80       repo_root.parent + '"-" in name'             orphan scan
    repo.py:125             common.parent.name == "main"                 layout assertion

Two of those are COMPLETE creation paths (`atdd worktree create` and
`atdd coach enter`), so configuring placement at one of them alone would make the
two commands disagree about where the same branch's worktree belongs. A third,
`session_template.py`, used a different algorithm again — string manipulation
producing a relative `../` path — and its result is what a spawned agent is told
to `cd` into.

The contract here is deliberately small:

* ``resolve_worktree_root`` reads ``worktree_root`` from ``.atdd/config.yaml``
  and defaults to ``..`` — today's flat sibling. An upgraded consumer that
  configures nothing sees placement bit-identical to what it had (Decision 2,
  forward-only migration).
* ``resolve_worktree_path`` is what every call site uses. Given a prefix and
  slug it returns one absolute path, so agreement between call sites is
  structural rather than a thing to remember.

Relocation lives here too, because moving a worktree is exactly the operation
that must keep git and the State Store in step — a half-applied move (git moved,
store stale) manufactures the same stale-binding class this repo already carries
31 of.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "DEFAULT_WORKTREE_ROOT",
    "RelocationOffer",
    "relocate_worktree",
    "relocation_offer",
    "resolve_worktree_dir_name",
    "resolve_worktree_path",
    "resolve_worktree_root",
    "write_worktree_binding",
]

# Today's layout: a flat sibling of the checkout. Keeping this as the default
# is what makes the migration forward-only — see Decision 2 on #1524.
DEFAULT_WORKTREE_ROOT = Path("..")


def _config(repo_root: Path) -> dict:
    """`.atdd/config.yaml` for a checkout, or an empty dict when unreadable.

    Placement must not become a new way for a command to fail: a missing or
    malformed config falls back to the default layout rather than raising.
    """
    from atdd.coach.utils.config import load_atdd_config

    try:
        return load_atdd_config(Path(repo_root)) or {}
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        # An unreadable config yields the default placement, which is today's
        # behaviour. Raising here would break `worktree create` on repos that
        # never opted into configuring placement at all.
        return {}


def resolve_worktree_root(repo_root: Path) -> Path:
    """The configured worktree root, as written — relative or absolute.

    Returns ``Path("..")`` when ``worktree_root`` is absent, which is the
    flat-sibling layout every existing repo already has.
    """
    value = _config(repo_root).get("worktree_root")
    if value in (None, ""):
        return DEFAULT_WORKTREE_ROOT
    return Path(str(value))


def resolve_worktree_dir_name(prefix: str, slug: str) -> str:
    """The directory name for a worktree — unchanged from the inlined form."""
    return f"{prefix}-{slug}"


def resolve_worktree_path(repo_root: Path, prefix: str, slug: str) -> Path:
    """Absolute path where this branch's worktree belongs.

    The single seam. Every derivation site routes through here, so
    ``atdd worktree create``, ``atdd coach enter``, and the launch prompt handed
    to a spawned agent cannot disagree.
    """
    repo_root = Path(repo_root)
    root = resolve_worktree_root(repo_root)
    base = root if root.is_absolute() else repo_root / root
    return (base / resolve_worktree_dir_name(prefix, slug)).resolve()


def resolve_worktree_root_dir(repo_root: Path) -> Path:
    """The absolute directory worktrees are placed in (not a specific worktree).

    `worktree_gc` needs this to scan the configured root, and to exclude that
    root from its own orphan candidate set — by identity, not by whether its
    name happens to contain a hyphen.
    """
    repo_root = Path(repo_root)
    root = resolve_worktree_root(repo_root)
    base = root if root.is_absolute() else repo_root / root
    return base.resolve()


# ---------------------------------------------------------------------------
# Relocation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelocationOffer:
    """Whether a worktree can be offered relocation, and where to.

    ``reason`` distinguishes "there is nothing here to relocate" from "the
    relocation failed". Reporting the first as the second is what sends an
    operator hunting a bug that does not exist.
    """

    offered: bool
    reason: str
    source: Path
    destination: Optional[Path] = None


def _bound_work_item(repo_root: Path, worktree: Path) -> Optional[tuple]:
    """``(slug, data)`` of the work item bound to this worktree, if any.

    77 of 113 worktrees on this repo carry no binding at all, and 56 of those
    are unrecoverable — never atdd-created. Returning None for them is the
    point: the caller declines rather than guessing.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import WORK_ITEM_KIND
    from atdd.state.store import StateStore

    target = str(Path(worktree).resolve())
    conn = connect(init_state_store(start=Path(repo_root)))
    try:
        for obj in StateStore(conn).objects.list(kind=WORK_ITEM_KIND):
            data = obj.data or {}
            bound = data.get("worktree_path")
            if bound and str(Path(bound).resolve()) == target:
                return obj.uid, data
    finally:
        conn.close()
    return None


def write_worktree_binding(repo_root: Path, slug: str, worktree_path: Path) -> None:
    """Rewrite ``data.worktree_path`` for a work item.

    Its own seam so relocation's failure mode is injectable: the rollback below
    only means something if this write is genuinely attempted and can genuinely
    fail.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=Path(repo_root)))
    try:
        store = StateStore(conn)
        obj = store.objects.get(slug)
        if obj is None:
            raise ValueError(f"no work item {slug!r} to bind")
        data = dict(obj.data or {})
        data["worktree_path"] = str(worktree_path)
        store.objects.upsert(slug, obj.kind, state=obj.state, data=data)
        conn.commit()
    finally:
        conn.close()


def relocation_offer(repo_root: Path, worktree: Path) -> RelocationOffer:
    """Whether this worktree can be moved under the configured root.

    Declines — rather than guessing — for a worktree the store does not know
    about. That is why the store↔git drift (#1529) is a sibling of this issue
    and not a prerequisite for it.
    """
    repo_root = Path(repo_root)
    worktree = Path(worktree)

    bound = _bound_work_item(repo_root, worktree)
    if bound is None:
        return RelocationOffer(offered=False, reason="unbound", source=worktree)

    slug, data = bound
    branch = data.get("branch") or ""
    prefix = branch.split("/", 1)[0] if "/" in branch else "feat"
    destination = resolve_worktree_path(repo_root, prefix, slug)

    if destination == worktree.resolve():
        return RelocationOffer(
            offered=False, reason="already-placed", source=worktree, destination=destination
        )

    return RelocationOffer(
        offered=True, reason="relocatable", source=worktree, destination=destination
    )


def relocate_worktree(repo_root: Path, slug: str, destination: Path) -> Path:
    """Move a worktree and rewrite its store binding, or do neither.

    The git move and the store write commit together. If the store write fails
    the directory is moved back, so a failure cannot leave the store naming a
    path that no longer exists — the stale-binding class this issue exists to
    avoid manufacturing.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import WORK_ITEM_KIND
    from atdd.state.store import StateStore

    repo_root = Path(repo_root)
    destination = Path(destination)

    conn = connect(init_state_store(start=repo_root))
    try:
        obj = StateStore(conn).objects.get(slug)
    finally:
        conn.close()
    if obj is None or not (obj.data or {}).get("worktree_path"):
        raise ValueError(f"work item {slug!r} has no worktree binding to relocate")
    if obj.kind != WORK_ITEM_KIND:
        raise ValueError(f"{slug!r} is not a work item")

    source = Path(obj.data["worktree_path"])
    if not source.exists():
        raise FileNotFoundError(f"bound worktree {source} does not exist")

    destination.parent.mkdir(parents=True, exist_ok=True)
    moved = _git_worktree_move(repo_root, source, destination)

    try:
        write_worktree_binding(repo_root, slug, destination)
    except Exception:
        # Roll the move back before re-raising. Leaving git moved with a stale
        # store binding is the one genuinely painful failure state here.
        if moved:
            _git_worktree_move(repo_root, destination, source, rollback=True)
        raise
    return destination


def _git_worktree_move(
    repo_root: Path, source: Path, destination: Path, *, rollback: bool = False
) -> bool:
    """`git worktree move`, falling back to a directory move for plain dirs.

    Returns True when the directory actually moved, so the caller knows whether
    there is anything to undo.
    """
    result = subprocess.run(
        ["git", "worktree", "move", str(source), str(destination)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    if result.returncode == 0:
        return True
    # Not a registered worktree (or git declined): fall back to a plain move so
    # the rollback path stays symmetric with the forward path.
    if source.exists() and not destination.exists():
        shutil.move(str(source), str(destination))
        return True
    if rollback:
        return False
    raise RuntimeError(
        f"git worktree move failed: {result.stderr.strip() or result.stdout.strip()}"
    )
