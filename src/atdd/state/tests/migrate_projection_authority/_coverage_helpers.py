# URN: component:migrate-projection-authority:test-support:coverage_fixtures:backend:tests
# Runtime: python
# Purpose: A real git checkout with a real store and a real committed projection — the given every C004 coverage acceptance needs, built once.

"""Shared fixtures for the C004 projection-coverage acceptances (#2042).

Every coverage acceptance needs the same expensive given: a real git repo, a real
``.atdd/state/state.sqlite`` written through the production writer, and a real
*committed* projection — committed, because coverage is judged against what is at
HEAD, never against the working tree.

**No population constant lives here.** The store this builds is whatever the caller
seeds, and the checks under test derive their obligation from the store rather than
from a number, so an acceptance can never accidentally pin the corpus size. That is
deliberate: the live corpus moved 1,053 -> 1,064 work items in the two days between
this issue being filed and being worked, and a check that bakes a population is a
check that starts failing on the next authored issue.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from atdd.state import projection as P


def require(name: str):
    """The ``projection`` attribute ``name``, or a RED failure that says what is missing.

    Importing it directly would make RED a collection error, and this wagon's convention is
    that a RED fails *inside* the behaviour with the system's own refusal, not on an import
    (see ``test_e002_unit_002``). Probing keeps the module importable, so the acceptance can
    state the obligation in its own words and fail on that.
    """
    from atdd.state import projection

    attribute = getattr(projection, name, None)
    assert attribute is not None, (
        f"atdd.state.projection.{name} does not exist. Coverage has no entrypoint, so nothing "
        "in the cutover chain can compare the committed projection against the store — which "
        "is the whole of #2042"
    )
    return attribute


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in ``repo`` (identity pinned so fixtures are hermetic)."""
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


def new_repo(path: Path) -> Path:
    """A real git repo with a Control Root marker and a gitignored store."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet", "-b", "main")
    git(path, "config", "user.email", "coverage@atdd.test")
    git(path, "config", "user.name", "Coverage Fixture")
    (path / ".atdd" / "state").mkdir(parents=True, exist_ok=True)
    (path / ".gitignore").write_text(".atdd/state/state.sqlite*\n", encoding="utf-8")
    return path


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", message)


def seed(
    root: Path,
    work_items: Iterable[Tuple[str, str]],
    *,
    other_kinds: Optional[Iterable[Tuple[str, str]]] = None,
) -> Dict[str, str]:
    """Write ``(slug, phase)`` work items through the PRODUCTION writer; return slug -> uid.

    ``other_kinds`` seeds ``(uid, kind)`` objects the projector never lists, which is how
    an acceptance arranges "excluded by a declared rule" without inventing a private path.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=root))
    try:
        minted = {
            slug: create_work_item(conn, slug, state=phase, data={"title": slug}).uid
            for slug, phase in work_items
        }
        store = StateStore(conn)
        for uid, kind in (other_kinds or ()):
            store.objects.upsert(uid, kind, state="ACTIVE", data={"title": uid})
        return minted
    finally:
        conn.close()


def project_and_commit(root: Path, message: str = "the projection") -> Path:
    """Project the store at ``root`` and commit the result; return the projection dir."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    out = root / P.PROJECTION_RELATIVE
    conn = connect(init_state_store(start=root))
    try:
        P.project(StateStore(conn), out)
    finally:
        conn.close()
    commit_all(root, message)
    return out


def committed_filenames(root: Path) -> List[str]:
    """The ``<uid>.yaml`` names in the projection at HEAD, sorted."""
    from atdd.state import gitstore

    return sorted(gitstore.projection_bytes_at(
        root, "HEAD", P.PROJECTION_RELATIVE.as_posix(),
    ))


def remove_document(root: Path, filename: str, message: str = "truncated") -> None:
    """Delete one committed document and commit the truncation."""
    (root / P.PROJECTION_RELATIVE / filename).unlink()
    commit_all(root, message)
