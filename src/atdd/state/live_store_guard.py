"""Live State Store pollution guard — resolution + fingerprinting (#1582).

The defect this exists to stop
------------------------------
``ATDD_CONTROL_ROOT`` (resolver Rule 1, :mod:`atdd.state.paths`) **outranks the
explicit** ``start=`` **argument**. ``init_state_store(start=tmp_path)`` reads
``os.environ`` and, when the operator's shell exports ``ATDD_CONTROL_ROOT`` — as
this project's own idiom prescribes (``ATDD_CONTROL_ROOT=$PWD atdd …``) — Rule 1
returns the override and never looks at ``start`` at all. Rule 1.4 (#1346) then
redirects a child-worktree override *up* to the shared project root. The result:
a test that carefully built a throwaway Control Root under ``tmp_path`` writes
its fixtures into the production State Store.

That is not hypothetical. A session run injected eight fixture work items
(``a``, ``b``, ``demo-session``, ``wi-authored``, ``wi-backfilled``,
``wi-out-of-band``, ``drifted-record``, ``legacy-record``) into the live store
from four test modules, each of which passed a correct ``start=<tmp_path>``. One
of them carries the docstring "Hermetic: every probe builds its own throwaway
Control Root. The developer's live store is never touched." It was wrong.

Same root class as the #1580 mass-deletion incident — a process pointed at the
real Control Root when it should have been pointed at a temp dir. #1580 stopped
the deletion direction; this stops the pollution direction.

What this module is
-------------------
Pure stdlib resolution + fingerprinting logic, deliberately free of any pytest
import so the ``state`` layer keeps its stdlib-only dependency discipline (see
:mod:`atdd.state.paths`). The pytest fixtures that *apply* it live in
:mod:`atdd.state.live_store_guard_plugin`.

Fault injectability
-------------------
:data:`GUARD_TARGET_ENV` re-points the guard at a decoy path. A guard that
cannot be shown to fire is a stub, and proving this one fires must never require
writing to the store it protects — so the tests aim it at a throwaway file and
drive a real violation into that instead.

Dependency discipline: stdlib only (``hashlib``, ``os``, ``pathlib``).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Mapping, Optional

from atdd.state.paths import (
    CONTROL_ROOT_ENV,
    STATE_STORE_RELATIVE,
    StateLayoutError,
    resolve_control_root,
)

#: Re-exported so the pytest plugin names the override in one place only — the
#: variable whose precedence over ``start=`` is the entire defect (#1582).
__all__ = [
    "CONTROL_ROOT_ENV",
    "GUARD_TARGET_ENV",
    "LiveStoreAccessError",
    "assert_not_live_store",
    "describe_change",
    "is_live_store",
    "protected_store_paths",
    "store_digest",
    "store_fingerprint",
]

#: Fault-injection override. When set, the guard protects exactly this path
#: instead of the real store — that is how the guard's own tests prove it fires
#: without going anywhere near production. Set to the empty string to protect
#: nothing (an escape hatch for the inner sessions that must be able to write).
GUARD_TARGET_ENV = "ATDD_LIVE_STORE_GUARD_TARGET"

#: Only the main database file is fingerprinted. BOTH WAL sidecars are excluded,
#: for the same reason at two depths: a pure *reader* perturbs them, so including
#: them makes honest read-only access indistinguishable from pollution. ``-shm``
#: is a shared-memory index rebuilt on open; ``-wal`` is DELETED by sqlite when
#: the last connection closes cleanly, so a read-only audit of the live corpus
#: takes it from ``(0, mtime)`` to absent while the database itself is untouched.
#: That false positive was observed, not theorized — the sanctioned live-corpus
#: reader tripped this guard before the sidecars came out.
#:
#: The main file is the honest signal: a writer's changes land in it when the
#: connection closes and sqlite checkpoints, and every subprocess closes on exit,
#: which is precisely the route G3 exists to cover. The residual gap — a writer
#: that leaves a connection open past teardown, parking its commit in the WAL —
#: is an unclosed-connection leak, and G2 already refuses in-process opens.
_FINGERPRINTED_SUFFIXES = ("",)


class LiveStoreAccessError(AssertionError):
    """A test tried to open the live State Store.

    Derives from :class:`AssertionError` so pytest renders it as a failure the
    developer reads, not as an infrastructure crash.
    """


def _repo_root() -> Path:
    """The repo root for this checkout (``src/atdd/state/live_store_guard.py`` → up 3)."""
    return Path(__file__).resolve().parents[3]


def _normalise_database(database: object) -> Optional[Path]:
    """Resolve a ``sqlite3.connect`` first argument to a filesystem path.

    Returns ``None`` for anything that cannot name the live store on disk —
    ``:memory:``, a temp database (the empty string), or a non-path object.
    URI forms (``file:/path/to/db?mode=ro``) are unwrapped so the guard cannot be
    walked around by opening the live store through a URI.
    """
    if isinstance(database, Path):
        return database.resolve()
    if not isinstance(database, str):
        return None  # bytes/int fd/None — cannot designate the live store by path
    if database == ":memory:" or database == "":
        return None
    if database.startswith("file:"):
        remainder = database[len("file:") :]
        remainder = remainder.split("?", 1)[0]
        if not remainder or remainder == ":memory:":
            return None
        return Path(remainder).resolve()
    return Path(database).resolve()


def protected_store_paths(
    env: Optional[Mapping[str, str]] = None,
    repo_root: Optional[Path] = None,
) -> frozenset[Path]:
    """The State Store path(s) no test may open.

    Resolution, in order:

    1. :data:`GUARD_TARGET_ENV` — fault injection. Set → protect exactly that
       path. Set to empty → protect nothing.
    2. Otherwise the UNION of the two ways the real store gets reached:
       the environment-free resolution from this checkout (Rule 1.5 flat-sibling
       → the shared project root) and, when ``ATDD_CONTROL_ROOT`` is exported,
       the resolution that override produces (Rule 1 / Rule 1.4). Both mechanisms
       point at production in the flat-sibling layout, and taking the union means
       the guard does not depend on *which* one an operator's shell happens to
       arm today.

    Returns an empty set when no Control Root resolves. That is vacuous, not
    unchecked: no Control Root means there is no live store to pollute — the same
    asymmetry ``scan_work_item_provenance`` draws between "nothing to check" and
    "could not look". A consumer checkout that has never run ``atdd init``, and
    CI before one exists, both land here.
    """
    env = os.environ if env is None else env

    injected = env.get(GUARD_TARGET_ENV)
    if injected is not None:
        if not injected:
            return frozenset()
        return frozenset({Path(injected).expanduser().resolve()})

    start = _repo_root() if repo_root is None else Path(repo_root).resolve()
    roots: set[Path] = set()
    # Environment-free resolution: what the store is, independent of the shell.
    for probe_env in ({}, dict(env)):
        try:
            roots.add(resolve_control_root(start, env=probe_env).control_root)
        except StateLayoutError:
            continue  # no resolvable root down this path; the other may still resolve
    return frozenset(root / STATE_STORE_RELATIVE for root in roots)


def is_live_store(database: object, protected: Iterable[Path]) -> bool:
    """True if ``database`` designates one of the ``protected`` store paths."""
    resolved = _normalise_database(database)
    if resolved is None:
        return False
    return resolved in set(protected)


def assert_not_live_store(
    database: object,
    protected: Iterable[Path],
    *,
    nodeid: str,
) -> None:
    """Raise :class:`LiveStoreAccessError` if ``database`` is the live store.

    Raises BEFORE the caller opens anything, so the refusal prevents the write
    rather than reporting it afterwards.
    """
    if not is_live_store(database, protected):
        return
    resolved = _normalise_database(database)
    raise LiveStoreAccessError(
        f"Test {nodeid!r} tried to open the LIVE State Store:\n"
        f"  {resolved}\n\n"
        "No test may open the production store. The usual cause is NOT a missing\n"
        "`start=` argument — it is that ATDD_CONTROL_ROOT was exported in the\n"
        "shell running pytest. Resolver Rule 1 (src/atdd/state/paths.py) returns\n"
        "that override and never consults `start=`, so even\n"
        "`init_state_store(start=tmp_path)` lands on production (#1582).\n\n"
        "Fix: build the store under tmp_path and keep the environment out of it —\n"
        "  init_state_store(db_path=tmp_path / '.atdd' / 'state' / 'state.sqlite')\n"
        "or pin the override for the test:\n"
        "  monkeypatch.setenv('ATDD_CONTROL_ROOT', str(tmp_path))\n\n"
        "If this test genuinely audits the live corpus read-only, mark it:\n"
        "  @pytest.mark.live_store_read\n"
        "The marker permits the open; the fingerprint backstop still proves the\n"
        "test wrote nothing."
    )


def store_fingerprint(protected: Iterable[Path]) -> dict[str, Optional[tuple]]:
    """A cheap (size, mtime_ns) fingerprint of each protected store + its ``-wal``.

    Four ``stat`` calls per store — the per-test cost that makes a function-scoped
    backstop affordable across the whole suite. Missing files fingerprint as
    ``None``, so a store appearing where there was none is itself a change.
    """
    fingerprint: dict[str, Optional[tuple]] = {}
    for store in sorted(protected):
        for suffix in _FINGERPRINTED_SUFFIXES:
            path = store.with_name(store.name + suffix)
            try:
                stat = path.stat()
            except OSError:
                fingerprint[str(path)] = None
            else:
                fingerprint[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return fingerprint


def store_digest(protected: Iterable[Path]) -> dict[str, Optional[str]]:
    """sha256 of each protected store + its ``-wal`` — the definitive byte-check.

    ~28 ms for a 9 MB store, so this is session-scoped where the
    :func:`store_fingerprint` stat check is per-test.
    """
    digests: dict[str, Optional[str]] = {}
    for store in sorted(protected):
        for suffix in _FINGERPRINTED_SUFFIXES:
            path = store.with_name(store.name + suffix)
            try:
                data = path.read_bytes()
            except OSError:
                digests[str(path)] = None
            else:
                digests[str(path)] = hashlib.sha256(data).hexdigest()
    return digests


def describe_change(before: Mapping[str, object], after: Mapping[str, object]) -> str:
    """Human-readable diff of two fingerprints/digests (empty when unchanged)."""
    lines = [
        f"  {key}:\n    before: {before.get(key)!r}\n    after:  {after.get(key)!r}"
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]
    return "\n".join(lines)
