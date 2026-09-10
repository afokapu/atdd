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
  and defaults to ``.`` — the project root, which IS today's flat sibling of
  the checkout. An upgraded consumer that configures nothing sees placement
  bit-identical to what it had (Decision 2, forward-only migration).
* A relative ``worktree_root`` is anchored on the PROJECT ROOT, never on the
  calling checkout. ``worktrees`` therefore means ``<project>/worktrees/`` —
  beside ``main/``, which is the layout Decision 1 chose — and it means the
  same directory whether the command runs from ``main/`` or from inside
  another worktree.
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
from typing import Optional, Union

__all__ = [
    "DEFAULT_WORKTREE_ROOT",
    "RelocationOffer",
    "placement_drift_notice",
    "relocate_worktree",
    "relocation_offer",
    "resolve_worktree_dir_name",
    "resolve_project_root",
    "resolve_worktree_path",
    "resolve_worktree_root",
    "write_worktree_binding",
]

# Today's layout: worktrees are flat siblings of the checkout, i.e. they sit
# directly in the PROJECT ROOT. Expressed against that anchor the default is
# ".", and keeping it is what makes the migration forward-only (Decision 2).
DEFAULT_WORKTREE_ROOT = Path(".")

# What the key used to be documented as, back when placement was resolved
# against the checkout rather than the project root. Read as a synonym for the
# default so a config written against the draft semantics still lands at the
# flat-sibling location instead of one level ABOVE the project.
_LEGACY_CHECKOUT_RELATIVE_DEFAULT = Path("..")


def _config(repo_root: Path) -> dict:
    """`.atdd/config.yaml` governing placement, or an empty dict when unreadable.

    Read from the PRIMARY checkout when there is one, not from the calling
    worktree. `.atdd/config.yaml` is a tracked file, so every worktree carries
    whatever revision of it its branch is on — and a branch cut before
    `worktree_root` was set would place its worktrees somewhere else. Layout is
    a property of the repository, so it is read from the one checkout every
    worktree shares. Falls back to the caller's own config when the primary
    checkout has none (a standalone clone, or a `main/` on an older revision).

    Placement must not become a new way for a command to fail: a missing or
    malformed config falls back to the default layout rather than raising.
    """
    from atdd.coach.utils.config import load_atdd_config

    for candidate in _config_candidates(Path(repo_root)):
        try:
            config = load_atdd_config(candidate) or {}
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
            # An unreadable config yields the default placement, which is
            # today's behaviour. Raising here would break `worktree create` on
            # repos that never opted into configuring placement at all.
            continue
        if "worktree_root" in config:
            return config
    return {}


def _config_candidates(repo_root: Path) -> list:
    """The primary checkout first, then the caller — deduplicated, in order."""
    from atdd.coach.utils.repo import _git_common_dir

    candidates = []
    common = _git_common_dir(repo_root)
    if common is not None and common.name == ".git":
        candidates.append(common.parent)
    if repo_root not in candidates:
        candidates.append(repo_root)
    return candidates


def resolve_project_root(repo_root: Path) -> Path:
    """The directory that HOLDS the checkouts — ``main/``'s parent.

    Placement has to be anchored here rather than on the calling checkout,
    because the two are not at the same depth. ``main/`` sits one level under
    the project root; a worktree under a configured root sits two. Anchoring on
    the caller made ``worktree_root: worktrees`` mean ``main/worktrees/`` when
    resolved from the checkout — inside the checkout, not beside it — and
    ``worktrees/feat-x/worktrees/`` when resolved from a worktree, so a
    worktree created from within a worktree nested one level deeper each time.
    The project root is the same directory for every caller, so every caller
    agrees.

    The git COMMON dir is what identifies it: every linked worktree shares
    ``<project>/main/.git``, so its parent is the primary checkout and its
    grandparent is the project root. Falls back to ``repo_root.parent`` when
    git cannot answer, which is the pre-#1524 derivation and therefore keeps
    an unresolvable repo on today's behaviour rather than failing.
    """
    from atdd.coach.utils.repo import _git_common_dir

    repo_root = Path(repo_root).resolve()
    common = _git_common_dir(repo_root)
    if common is not None and common.name == ".git":
        return common.parent.parent
    return repo_root.parent


def resolve_worktree_root(repo_root: Path) -> Path:
    """The configured worktree root, as written — relative or absolute.

    A relative value is interpreted against the PROJECT ROOT, which is what
    the conceptual model on #1524 says it is. Returns ``Path(".")`` when
    ``worktree_root`` is absent — the flat-sibling layout every existing repo
    already has.
    """
    value = _config(repo_root).get("worktree_root")
    if value in (None, ""):
        return DEFAULT_WORKTREE_ROOT
    root = Path(str(value))
    if root == _LEGACY_CHECKOUT_RELATIVE_DEFAULT:
        return DEFAULT_WORKTREE_ROOT
    return root


def resolve_worktree_dir_name(prefix: str, slug: str) -> str:
    """The directory name for a worktree — unchanged from the inlined form."""
    return f"{prefix}-{slug}"


def resolve_worktree_path(repo_root: Path, prefix: str, slug: str) -> Path:
    """Absolute path where this branch's worktree belongs.

    The single seam. Every derivation site routes through here, so
    ``atdd worktree create``, ``atdd coach enter``, and the launch prompt handed
    to a spawned agent cannot disagree.
    """
    return (
        resolve_worktree_root_dir(repo_root) / resolve_worktree_dir_name(prefix, slug)
    ).resolve()


def resolve_worktree_root_dir(repo_root: Path) -> Path:
    """The absolute directory worktrees are placed in (not a specific worktree).

    `worktree_gc` needs this to scan the configured root, and to exclude that
    root from its own orphan candidate set — by identity, not by whether its
    name happens to contain a hyphen.
    """
    repo_root = Path(repo_root)
    root = resolve_worktree_root(repo_root)
    base = root if root.is_absolute() else resolve_project_root(repo_root) / root
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
    #: uid of the work item bound to this worktree, when there is one. The
    #: offer has to resolve it to know where the worktree belongs, and
    #: `relocate_worktree` needs the same value — returning it means the
    #: caller cannot pair an offer with a different work item's slug.
    slug: Optional[str] = None


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


def write_worktree_binding(
    repo_root: Path, slug: str, worktree_path: Union[Path, str]
) -> None:
    """Rewrite ``data.worktree_path`` for a work item.

    Accepts a str as well as a Path so the empty string can retire a binding
    whose directory is gone (#1894), rather than forcing a second write path
    to the same field.

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
            offered=False,
            reason="already-placed",
            source=worktree,
            destination=destination,
            slug=slug,
        )

    return RelocationOffer(
        offered=True,
        reason="relocatable",
        source=worktree,
        destination=destination,
        slug=slug,
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


def placement_drift_notice(cwd: Optional[Path] = None) -> Optional[str]:
    """A one-line notice when THIS worktree is not where the config says, else None.

    The issue asks for a relocation offer "on the first `atdd` command after a
    version change". This is that offer, and it is deliberately a NOTICE rather
    than a prompt: its caller, ``print_upgrade_sync_notice``, runs on every CLI
    invocation under a hard read-only contract (#342 — a banner that also
    mutated the working tree was the bug that contract exists to prevent).
    Blocking `atdd --help` on an interactive question would be a worse version
    of the same mistake, and Decision 4's staging rationale — never wall an
    agent off mid-flow — says the same thing.

    Returns None, silently, for every case that is not an actionable drift:
    no config, no drift, an unbound worktree (which cannot be relocated without
    guessing), or any error at all. A placement notice must never be the reason
    a command fails or gets noisier than it was.
    """
    try:
        from atdd.coach.utils.repo import find_worktree_root

        worktree = Path(cwd) if cwd else Path.cwd()
        repo_root = find_worktree_root(worktree)

        # Only a LINKED worktree is relocatable. The primary checkout has a
        # `.git` directory rather than a gitfile, and its location is what the
        # project root is derived from — moving it would move the anchor.
        if not (repo_root / ".git").is_file():
            return None

        offer = relocation_offer(repo_root, repo_root)
        if not offer.offered:
            return None
        return (
            f"This worktree sits outside the configured worktree_root.\n"
            f"     here: {offer.source}\n"
            f"   config: {offer.destination}\n"
            f"   Move it with: atdd worktree relocate --apply"
        )
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None
