# URN: component:state:test-support:shared_fixtures:backend:tests
# Runtime: python
# Purpose: The hermetic git-checkout, canonical-projection and in-memory-store fixtures every atdd.state wagon builds on, defined once.

"""The fixtures every ``atdd.state`` wagon shares (#1400).

Each wagon under ``atdd/state/tests`` needs the same three things: a real git checkout with a
real Control Root, a committed projection written in canonical bytes, and an ephemeral State
Store that touches no developer SQLite. Each wagon had grown its own copy of all three.

They were never *quite* the same copy, which is the actual cost: ``checkout()`` was spelled
three ways that differed in which branch git initialised, what the ``.gitignore`` covered, and
whether an empty projection directory was seeded — differences that read as accidents of who
wrote the wagon rather than as anything a test meant. Here they are the parameters, so a wagon
states the one thing it needs differently and inherits the rest.

Hermetic throughout: a throwaway repo, a throwaway Control Root, no provider and no network —
which is the property the wagons exist to prove (I7, spec §4).

Dependency discipline: stdlib + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Optional, Tuple

from atdd.state.bare_remote import STORE_GITIGNORE, identify
from atdd.state.db import apply_migrations
from atdd.state.projection import PROJECTION_RELATIVE, canonical_bytes
from atdd.state.store import StateStore

#: The store alone, for a checkout that has no reason to hide the CLI's upgrade cache.
STORE_ONLY_GITIGNORE = ".atdd/state/state.sqlite*\n"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return its stdout."""
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True, timeout=60,
    )
    return result.stdout.strip()


def control_root(path: Path) -> Path:
    """A directory the store resolver will accept as a Control Root. No git, no commit."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / ".atdd").mkdir(exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    return path


def make_checkout(path: Path) -> Path:
    """A real git repo carrying a real Control Root marker — nothing committed."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(path)], check=True, capture_output=True)
    return control_root(path)


def checkout(
    path: Path,
    *,
    initial_branch: Optional[str] = "main",
    gitignore: str = STORE_GITIGNORE,
    seed_projection: bool = False,
    extra_files: Optional[Mapping[str, str]] = None,
    message: str = "initial",
) -> Path:
    """A real git repo with a Control Root, a gitignored store, and one commit on it.

    The identity is pinned to a literal, so a fixture's commits never depend on the
    developer's git config. ``initial_branch=None`` leaves the branch name to git — which is
    what a wagon that never names a branch was always (implicitly) doing.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    argv = ["git", "init", "--quiet"]
    if initial_branch:
        argv.append(f"--initial-branch={initial_branch}")
    subprocess.run([*argv, str(path)], check=True, capture_output=True, timeout=60)
    identify(path)
    control_root(path)
    (path / ".gitignore").write_text(gitignore, encoding="utf-8")
    for relative, content in (extra_files or {}).items():
        (path / relative).write_text(content, encoding="utf-8")
    if seed_projection:
        (path / PROJECTION_RELATIVE).mkdir(parents=True, exist_ok=True)
        (path / PROJECTION_RELATIVE / ".gitkeep").write_text("", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "--quiet", "-m", message)
    return path


def projection_dir(repo: Path) -> Path:
    return Path(repo) / PROJECTION_RELATIVE


def write_projection(repo: Path, documents: Iterable[Mapping[str, Any]]) -> Path:
    """Write ``documents`` as the repo's committed projection, in CANONICAL bytes.

    Canonical by construction: the wagons exist to show that canonicality is *not* correctness,
    so a fixture branch that failed canonicality would be arguing the wrong point.
    """
    out = projection_dir(repo)
    out.mkdir(parents=True, exist_ok=True)
    for doc in documents:
        (out / f"{doc['uid']}.yaml").write_bytes(canonical_bytes(doc))
    return out


def commit_all(repo: Path, message: str = "projection", *, author: Optional[str] = None) -> str:
    """Stage everything and commit; return the new HEAD sha.

    ``--allow-empty`` because several acceptances re-commit the *same tree* under a different
    message: the trailer group is the thing under test. ``author`` is ``Name <email>`` for the
    acceptances where who wrote the diff is the point.
    """
    git(repo, "add", "-A")
    args = ["commit", "--quiet", "--allow-empty", "-m", message]
    if author is not None:
        args += ["--author", author]
    git(repo, *args)
    return git(repo, "rev-parse", "HEAD")


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


@contextmanager
def memory_store() -> Iterator[Tuple[sqlite3.Connection, StateStore]]:
    """An ephemeral, migrated State Store held entirely in RAM."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    try:
        yield conn, StateStore(conn)
    finally:
        conn.close()
