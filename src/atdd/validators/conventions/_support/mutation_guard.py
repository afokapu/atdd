# URN: component:validate-conventions:tune-convention-suite:filesystem-mutation-guard:backend:domain
# Runtime: python
# Purpose: Observe real filesystem mutation of the checkout per test, so the serial marker cannot rot (#1418, E036).
"""Runtime detector for the one thing that makes ``-n auto`` unsafe: a test that writes the
shared checkout (#1418).

The convention suite is partitioned by mutation class so the non-mutating majority can run
under ``pytest-xdist``. That partition is only sound while the
``convention_filesystem_mutation`` marker is *complete*: xdist workers share one checkout,
so a single unmarked writer landing in the parallel subset corrupts its siblings' view of
the tree, and the damage surfaces as a phantom red somewhere else entirely.

A static scan for ``write_text`` / ``unlink`` / ``rmtree`` cannot carry that weight. The
suite mutates through family ``_parity.patch_file`` helpers and through ``python -m pytest``
subprocesses, and neither names a write at the call site. So the guard observes instead of
inferring: a ``sys.addaudithook`` records, for the test currently executing,

  * every path *inside the checkout* opened for write, created, removed, renamed or copied;
  * every subprocess spawned with its cwd inside the checkout — and, for those, whether the
    tree ACTUALLY changed across the call.

The direct write is the obvious hazard. The subprocess is the subtle one: what it does to the
tree is opaque from here, and the E032-E036 smoke tests each spawn a whole ``pytest`` over the
repo. Calling every spawner serial is sound but far too blunt — after #1458 root-redirected the
fault families most of those nested runs write nothing at all, and one of them
(``test_migrated_families_write_nothing_to_the_tracked_tree``) is *the test that asserts so*;
marking it serial then collided with the session-graph guard below and failed a correct test.

So the spawn is not the verdict. The ``subprocess.Popen`` audit event fires BEFORE the child is
exec'd, which is a free moment to fingerprint the tree and diff it at teardown — an observation
instead of an assumption, and it costs nothing for the tests that never spawn one.

The fingerprint is (mtime_ns, size), NOT content: a fault test writes a file and reverts it in a
``finally``, so the bytes match again by the time anyone looks and ``git status`` reports a clean
tree. The tree was still dirty in between, and that window is exactly what corrupts a parallel
worker. mtime survives the revert; content does not.

Writes *outside* the checkout (``tmp_path``, site-packages) are not a hazard — workers share
the checkout, not the temp dirs — and neither are the per-run regenerable paths in
``_IGNORED_PATH_PARTS``. Both are ignored, so the guard has no false positives to suppress.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pytest

SERIAL = "convention_filesystem_mutation"
INMEMORY = "convention_inmemory_fault"
READONLY = "convention_readonly"

# Written by every run whatever the tests do (bytecode and tool caches, runtime scratch,
# git's own index). Regenerable or per-process — not a shared-tree hazard.
_IGNORED_PATH_PARTS = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".atdd",
        "node_modules",
        ".venv",
    }
)

# open() modes that can change bytes on disk. "r" alone cannot; "r+" can.
_MUTATING_MODE_CHARS = frozenset("wxa+")

# Audit events that mutate a path without going through open(), mapped to the argument
# positions of (the paths they act on, the dir_fds those paths may be relative to).
#
# The dir_fd column is load-bearing. `shutil.rmtree` walks a tree through an open directory
# fd and emits `os.remove('_do_thing.yaml', dir_fd=5)` — a path relative to *that fd*, not to
# the process cwd. Resolving it against cwd instead turns a tempdir cleanup into an apparent
# write at the repo root, which is exactly the false positive that had the whole boundary
# family (which only ever writes under `tempfile.mkdtemp()`) looking like a mutator.
#
# POSIX ignores dir_fd when the path is absolute, so the rule is: absolute paths always count;
# a relative path counts only when no dir_fd is in play, in which case it IS cwd-relative.
_EVENT_PATH_ARGS: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    # event: (path arg indices, dir_fd arg indices)
    "os.mkdir": ((0,), (2,)),
    "os.remove": ((0,), (1,)),
    "os.rmdir": ((0,), (1,)),
    "os.truncate": ((0,), ()),
    "os.rename": ((0, 1), (2, 3)),
    "os.link": ((0, 1), (2, 3)),
    "os.symlink": ((0, 1), (2,)),
    "shutil.copyfile": ((0, 1), ()),
    "shutil.copymode": ((0, 1), ()),
    "shutil.copystat": ((0, 1), ()),
    "shutil.move": ((0, 1), ()),
    "shutil.rmtree": ((0,), (1,)),
}


@dataclass
class MutationRecord:
    """What one test did to the checkout."""

    writes: set[str] = field(default_factory=set)
    # Subprocesses that PROVABLY changed the tree. A spawn on its own is not here: the audit
    # hook cannot see inside the child, so the tree is fingerprinted instead (below).
    subprocesses: set[str] = field(default_factory=set)
    # The paths whose (mtime, size) moved across a subprocess — so the failure names a culprit.
    changed_paths: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.writes or self.subprocesses)

    def reasons(self) -> str:
        parts = []
        if self.writes:
            parts.append("wrote " + ", ".join(sorted(self.writes)[:6]))
        if self.subprocesses:
            parts.append(
                "its subprocess (" + ", ".join(sorted(self.subprocesses)[:3]) + ") changed "
                + ", ".join(sorted(self.changed_paths)[:6])
            )
        return "; ".join(parts)


def _describe_argv(argv: object, executable: object) -> str:
    """A short, stable label for a spawned command — it lands in the guard's failure
    message, so it should name the culprit, not dump a full argv."""
    if isinstance(argv, (list, tuple)) and argv:
        parts = [os.fsdecode(a) for a in argv[:3] if isinstance(a, (str, bytes, os.PathLike))]
        if parts:
            parts[0] = Path(parts[0]).name
            return " ".join(parts)
    if isinstance(executable, (str, bytes, os.PathLike)):
        return Path(os.fsdecode(executable)).name
    return "<subprocess>"


class _Recorder:
    def __init__(self) -> None:
        self.root: Path | None = None
        self.current: MutationRecord | None = None
        # (path -> (mtime_ns, size)) of the tracked surface, captured on this test's FIRST
        # subprocess spawn, plus the commands spawned since. None until a test spawns one.
        self.pre_spawn: dict[str, tuple[int, int]] | None = None
        self.spawned: list[str] = []

    def fingerprint(self) -> dict[str, tuple[int, int]]:
        """(mtime_ns, size) of every path in the checkout — the whole thing, not a shortlist.

        Narrowing this to the areas the convention suite happens to write today (plan/, src/atdd/,
        pyproject.toml) saves ~30ms and silently stops noticing a subprocess that writes anywhere
        else. The whole tree is 4.5k entries in ~43ms, and only the handful of tests that spawn a
        subprocess ever pay it, so there is nothing to buy by guessing.

        mtime, NOT content: a fault test writes a file and reverts it in a ``finally``, so the
        bytes match again by the time anyone looks and ``git status`` reports a clean tree. The
        tree WAS dirty in between, and that window is exactly what corrupts a parallel worker.
        mtime survives the revert; content does not.

        Directories, not just files: a test that CREATES a probe file and deletes it again leaves
        no trace in a file-only fingerprint — the file is absent from both snapshots — but it does
        bump its parent directory's mtime. ``plan/validate_conventions/E996.yaml`` is that shape.
        """
        assert self.root is not None
        out: dict[str, tuple[int, int]] = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORED_PATH_PARTS]
            for p in [dirpath] + [os.path.join(dirpath, n) for n in filenames]:
                # lexists, not try/except: a dangling symlink is the only thing os.walk can hand
                # us that cannot be stat'd, and swallowing a real OSError here would hide exactly
                # the kind of tree damage this function exists to notice.
                if not os.path.lexists(p):
                    continue
                st = os.stat(p, follow_symlinks=False)
                out[os.path.relpath(p, self.root)] = (st.st_mtime_ns, st.st_size)
        return out

    def repo_relative(self, path: object, *, cwd_relative: bool = True) -> str | None:
        """Repo-relative path, or None when the path is outside the checkout, ignored, or not
        resolvable — audit args carry dir_fd ints and already-open fds as well as paths.

        ``cwd_relative=False`` says a relative path here is relative to some open directory fd
        we cannot see, so it must not be resolved against the process cwd.
        """
        # Audit args are positional and untyped: a dir_fd or an already-open fd arrives as an
        # int, and a length as an int too. Ask what the value IS rather than catching what
        # fsdecode throws — a bare `except: return None` on this hot path would swallow real
        # bugs as silently as it swallows the ints.
        if self.root is None or not isinstance(path, (str, bytes, os.PathLike)):
            return None
        p = Path(os.fsdecode(path))
        if not p.is_absolute():
            if not cwd_relative:
                return None
            p = Path.cwd() / p
        # normpath, not resolve(): resolve() stats every component and this runs on the audit
        # hot path. The suite never reaches the tree through a symlink.
        p = Path(os.path.normpath(p))
        if not p.is_relative_to(self.root):
            return None  # outside the checkout — xdist workers do not share it
        rel = p.relative_to(self.root)
        if _IGNORED_PATH_PARTS.intersection(rel.parts):
            return None
        return str(rel)

    def audit(self, event: str, args: tuple) -> None:
        rec = self.current
        if rec is None:  # outside a test: collection, session fixtures, teardown of the run
            return
        if event == "open":
            # io.open carries a str mode; os.open (which is what rmtree's fd walk uses, with a
            # dir_fd) carries None. Only the former can be a cwd-relative write, so filtering on
            # a mutating str mode leaves no fd-relative path to misresolve here.
            mode = args[1] if len(args) > 1 else None
            if not isinstance(mode, str) or not _MUTATING_MODE_CHARS.intersection(mode):
                return
            rel = self.repo_relative(args[0])
            if rel is not None:
                rec.writes.add(rel)
        elif event in _EVENT_PATH_ARGS:
            path_args, dir_fd_args = _EVENT_PATH_ARGS[event]
            fd_relative = any(
                isinstance(args[i], int) and args[i] >= 0
                for i in dir_fd_args
                if i < len(args)
            )
            for i in path_args:
                if i >= len(args):
                    continue
                rel = self.repo_relative(args[i], cwd_relative=not fd_relative)
                if rel is not None:
                    rec.writes.add(rel)
        elif event == "subprocess.Popen":
            # args = (executable, args, cwd, env). cwd None means "inherit", and pytest runs
            # from the repo root, so None counts as inside the checkout.
            cwd = args[2] if len(args) > 2 else None
            if cwd is not None and self.repo_relative(cwd) is None:
                return
            self.spawned.append(
                _describe_argv(args[1] if len(args) > 1 else None, args[0] if args else None)
            )
            # This event fires BEFORE the child is exec'd, so the tree is still pristine here —
            # fingerprint it now and diff at teardown. That turns "spawned a subprocess" (an
            # assumption) into "its subprocess changed the tree" (an observation), and it costs
            # nothing for the ~90% of tests that never spawn one.
            if self.pre_spawn is None:
                self.pre_spawn = self.fingerprint()


_RECORDER = _Recorder()
_INSTALLED = False


def install(root: Path) -> None:
    """Arm the audit hook for this process, rooted at ``root``.

    Idempotent: audit hooks cannot be removed once added, so a second call only re-points
    the root. xdist forks each worker with its own interpreter, so each arms its own.

    Bytecode writing is disabled here — for this process and for every subprocess it spawns. That
    is not tidiness, it is what makes the fingerprint mean anything. Importing a module creates
    ``<pkg>/__pycache__/``, and creating that directory bumps ``<pkg>``'s OWN mtime. The
    ``__pycache__`` entry itself is pruned from the fingerprint; its parent is not. So on a
    checkout that has never been imported — which is CI, every single time — a purely READ-ONLY
    nested pytest run is indistinguishable from a tree mutation. It passed locally for precisely
    the reason it had to: the caches were already there.

    Every spawn site in the suite builds its child env from ``os.environ``, so the variable reaches
    the children. ``sys.dont_write_bytecode`` covers this process, whose own imports continue well
    past collection.
    """
    global _INSTALLED
    _RECORDER.root = Path(os.path.normpath(root))
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if not _INSTALLED:
        sys.addaudithook(_RECORDER.audit)
        _INSTALLED = True


def begin() -> None:
    """Start recording for the test about to run."""
    _RECORDER.current = MutationRecord()
    _RECORDER.pre_spawn = None
    _RECORDER.spawned = []


def end() -> MutationRecord:
    """Stop recording and return what the test did to the checkout.

    If the test spawned a subprocess over the checkout, the tree is re-fingerprinted and diffed
    against the snapshot taken at spawn time. Only a subprocess that ACTUALLY disturbed the tree
    makes the test serial — a nested `pytest --collect-only`, a `git status`, or a suite that
    provably writes nothing (which is what #1458 made the fault families) stays parallel.
    """
    record = _RECORDER.current or MutationRecord()
    if _RECORDER.pre_spawn is not None:
        before = _RECORDER.pre_spawn
        after = _RECORDER.fingerprint()
        changed = sorted(
            k for k in set(before) | set(after) if before.get(k) != after.get(k)
        )
        if changed:
            record.subprocesses.update(_RECORDER.spawned)
            # Name what moved. A verdict of "your subprocess changed the tree" with no path is
            # undebuggable from a CI log — which is exactly how the __pycache__ false positive
            # above cost a round-trip to diagnose.
            record.changed_paths.update(changed[:6])
    _RECORDER.current = None
    _RECORDER.pre_spawn = None
    _RECORDER.spawned = []
    return record


def assign_default_class(items: list[pytest.Item], base_dir: Path) -> None:
    """Put every convention test in exactly one mutation class.

    Only the two non-default classes are authored. ``convention_readonly`` is the residue,
    so a newly added test is parallel-by-default and it is the guard — not an author's
    memory — that has to prove the default true.
    """
    for item in items:
        path = getattr(item, "path", None)
        if path is None or base_dir not in Path(path).parents:
            continue  # a whole-repo run also reaches this hook; only classify our own
        if not any(item.get_closest_marker(m) for m in (SERIAL, INMEMORY)):
            item.add_marker(READONLY)


@pytest.fixture(autouse=True)
def mutation_class_guard(request: pytest.FixtureRequest) -> Iterator[None]:
    """The two guards that keep the ``-n auto`` split honest.

    Imported into ``conventions/conftest.py``, where being autouse scopes it to the suite.
    """
    install(Path(request.config.rootpath))
    marked_serial = request.node.get_closest_marker(SERIAL) is not None

    # Guard 2 — a serial test may never take the session graph. `clean_convention_graph` is
    # composed once and shared; a test that writes the tree has to re-read it to see its own
    # injection and to prove the revert left no residue, so handing it the session graph
    # makes exactly those assertions vacuous.
    if marked_serial and "clean_convention_graph" in request.fixturenames:
        pytest.fail(
            f"{request.node.nodeid} is marked `{SERIAL}` but requests `clean_convention_graph`.\n"
            "A filesystem-mutating test must observe the tree it mutated, and the session graph "
            "was composed before the mutation — the assertions would be vacuous.\n"
            f"Either compose your own graph (load_composed_graph), or — better — inject into a "
            f"cloned graph (_support.graph_mutations) and take the `{INMEMORY}` class."
        )

    begin()
    yield
    record = end()

    # Guard 1 — an unmarked test that mutated the checkout would run under `-n auto` against
    # the tree its siblings are reading.
    if record and not marked_serial:
        pytest.fail(
            f"{request.node.nodeid} mutated the checkout but is not marked `{SERIAL}`: "
            f"{record.reasons()}.\n"
            f"CI runs everything NOT marked `{SERIAL}` under `-n auto` against one shared "
            "checkout, so this test would corrupt its siblings.\n"
            f"Either add `@pytest.mark.{SERIAL}`, or inject the fault into a cloned graph "
            f"(_support.graph_mutations) and stay in the `{INMEMORY}` class."
        )
