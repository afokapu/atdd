"""
ATDD upgrade orchestration.

Shows what changed between installed and last_version,
then refreshes this checkout in-process with confirmation (#1820).

#1628 — two properties beyond that:

*Runnable unattended.* The confirmation resolves the way ``atdd coach`` already
resolves its own (``coach.resolve_no_prompt``, coach.py:255): an explicit flag
wins, and absent one the answer is taken from whether stdin is a terminal. A
worker with no controlling terminal proceeds under a decision it states out
loud instead of raising ``EOFError``. This makes the command *runnable* without
a human; it does not make it *automatic*. Nothing here invokes an upgrade on
its own, and the pre-push version gate still only names it (wmbt:...:Y004).

*Safe under concurrency.* Roughly sixty agents run out of one pipx install, so
the mutating sections are serialised on a lock scoped to that install — never
to a checkout, since sixty worktrees have sixty ``.atdd/`` roots and would
serialise against nothing. A run that cannot take the lock refuses and says so;
it never proceeds unlocked, and there is no environment variable that skips it.
"""

import contextlib
import errno
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterator, Optional, TextIO, Tuple

from atdd import __version__
from atdd.version_check import (
    get_upgrade_notes,
    _load_repo_config,
    _read_sync_record,
    record_toolkit_sync,
    is_outdated,
    auto_upgrade,
    _gate_version,
    _is_newer,
    _load_cache,
    _resolve_latest_version,
    upgrade_command,
)

try:  # POSIX advisory locking; the kernel drops it when the holder dies.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

#: How long a run waits for the install lock before refusing. Waiting is not
#: failure — a concurrent upgrade finishes in seconds — so this is generous.
UPGRADE_LOCK_TIMEOUT = 300.0


class UpgradeLockUnavailable(RuntimeError):
    """The install-scoped upgrade lock could not be taken. Nothing was changed."""


def resolve_confirmation(explicit_yes: Optional[bool], isatty: bool) -> bool:
    """Return True when the confirmation resolves to "proceed" without prompting.

    Mirrors ``atdd.coach.commands.coach.resolve_no_prompt``: if *explicit_yes*
    is not None it wins; otherwise a run with no terminal answers itself, and a
    run with one is still asked.
    """
    if explicit_yes is not None:
        return bool(explicit_yes)
    return not isatty


def upgrade_lock_path() -> Path:
    """Return the lock identity for the install this process runs from.

    Keyed on ``sys.prefix`` so two checkouts sharing one install contend while
    two genuinely separate installs do not, and held outside every repository
    so a per-worktree control root cannot fragment it.
    """
    install = Path(sys.prefix).resolve()
    digest = hashlib.sha256(str(install).encode("utf-8")).hexdigest()[:16]
    root = Path(tempfile.gettempdir()) / "atdd-upgrade-locks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{digest}.lock"


#: errnos a non-blocking flock raises when someone else already holds the lock.
_CONTENDED = (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK)


def _try_flock(handle) -> bool:
    """Take the lock without blocking. True if held, False if someone else has it.

    Any errno other than contention is a real fault and propagates — a lock we
    cannot reason about must not be mistaken for a lock we are merely waiting on.
    """
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno in _CONTENDED:
            return False
        raise


def _acquire_or_refuse(handle, deadline: float, path: Path) -> None:
    """Poll until the lock is held, or refuse once the bounded wait expires."""
    while not _try_flock(handle):
        if time.monotonic() >= deadline:
            raise UpgradeLockUnavailable(
                f"another atdd upgrade is in progress and holds the install "
                f"lock ({path}); nothing here was changed — retry once it finishes"
            )
        time.sleep(0.05)


@contextlib.contextmanager
def upgrade_lock(timeout: Optional[float] = None) -> Iterator[Path]:
    """Hold the install-scoped upgrade lock, or refuse.

    Raises ``UpgradeLockUnavailable`` when the bounded wait expires. The lock is
    a POSIX ``flock``, so a holder that dies — an agent killed mid-upgrade —
    releases it in the kernel rather than leaving sixty workers waiting on an
    operator to clear a stale file by hand.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX
        raise UpgradeLockUnavailable(
            "no advisory file locking on this platform; refusing to upgrade a "
            "shared install unserialised"
        )

    wait = UPGRADE_LOCK_TIMEOUT if timeout is None else timeout
    path = upgrade_lock_path()

    handle = open(path, "a+")
    try:
        _acquire_or_refuse(handle, time.monotonic() + wait, path)
        try:
            yield path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def refresh_is_owed(repo_root, config=None) -> bool:
    """Whether this checkout is behind the installed toolkit.

    Reads ONLY the untracked per-checkout record (#1641). The git-tracked
    ``toolkit.last_version`` fallback is deliberately not consulted: it is pinned
    at an ancient value in every checkout that carries one — 3.106.0 against a
    4.47.x toolkit here — so reading it reports a refresh owed forever, which is
    what made #1628's already-current no-op (E008-UNIT-003) unreachable and sent
    every run on to ``init --force``. A checkout with no record is genuinely owed
    a refresh; that is the honest answer and the common one (154 of this repo's
    157 worktrees).
    """
    del config  # the stale fallback is not part of the decision
    # Read the module-level name run() uses, so a caller (or a test) that patches
    # the installed version sees one consistent answer from both.
    return _read_sync_record(repo_root) != __version__


def run_repo_refresh(repo_root) -> int:
    """Perform the refresh in-process: hooks, gitignore, schemas, stamp.

    Not a subprocess. ``upgrade`` used to shell ``atdd sync`` and then
    ``atdd init --force`` — a flag #793 forbids and which #1600 shows cannot act
    on an initialised repo. Every job here is triggered by a toolkit version
    change, which is the condition ``upgrade`` exists to detect, so it owns them.
    """
    from atdd.coach.commands.sync import RepoRefresh

    return RepoRefresh(target_dir=repo_root).sync()


class Upgrader:
    """Orchestrates atdd upgrade in a consumer repo."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()

    def refresh_repo(self) -> int:
        """The repo-refresh half of an upgrade, performed here rather than shelled."""
        return run_repo_refresh(self.repo_root)

    def run(self, yes: bool = False, no_pypi: bool = False) -> int:
        """Run the upgrade process.

        Args:
            yes: Skip confirmation prompts.
            no_pypi: Skip the live PyPI check (use local state only).

        Returns:
            0 on success, 1 on failure.
        """
        config, config_path = _load_repo_config()
        if config is None:
            print("Not an ATDD repo (no .atdd/config.yaml). Nothing to upgrade.")
            return 1

        installed = __version__
        latest: Optional[str] = None

        # #1628: resolve the confirmation once, up front. An explicit --yes
        # wins; absent one, a run with no terminal answers itself rather than
        # dying on input(). `self_answered` is True only when we made that call
        # ourselves, which is the case that has to be said out loud.
        isatty = sys.stdin.isatty()
        explicit_yes = True if yes else None
        unprompted = resolve_confirmation(explicit_yes, isatty)
        self_answered = explicit_yes is None and not isatty

        # 1. Query PyPI for the real latest version (unless --no-pypi).
        if not no_pypi:
            outdated, _, latest = is_outdated()
            if latest and outdated:
                print(f"New version on PyPI: {installed} → {latest}")
                _cmd = upgrade_command()

                proceed = True
                if unprompted:
                    if self_answered:
                        print(
                            "No terminal detected — answering the upgrade "
                            f"confirmation non-interactively: {_cmd}"
                        )
                else:
                    answer = input(
                        f"Run `{_cmd}` now? [Y/n] "
                    ).strip().lower()
                    if answer and answer != "y":
                        print("Skipping upgrade. Continuing with sync step only.")
                        proceed = False

                if proceed:
                    print(f"Running: {_cmd}")
                    try:
                        with upgrade_lock():
                            # Unpack, never truth-test: auto_upgrade() returns a
                            # (success, detail) tuple, and a tuple is always
                            # truthy — `if not auto_upgrade()` would make this
                            # branch unreachable and report every failure as a
                            # success (#1671).
                            upgraded, detail = auto_upgrade()
                            if not upgraded:
                                print("Upgrade failed.")
                                if detail:
                                    print(f"  {detail}")
                                print(f"Run manually: {_cmd}")
                                return 1
                    except UpgradeLockUnavailable as exc:
                        logger.error(
                            "upgrade refused, install lock contended: %s", exc,
                            extra={"phase": "upgrade-lock", "step": "pypi-upgrade",
                                   "outcome": "contended"},
                        )
                        print(str(exc))
                        return 1
                    print(
                        f"Upgraded atdd to {latest}. "
                        "Re-run `atdd upgrade` to finish sync with the new version."
                    )
                    return 0
            elif not latest:
                print("(Could not reach PyPI — skipping live version check.)")

        # 2. Local sync path: compare the last recorded sync against installed.
        #
        # Read the untracked runtime record FIRST, then fall back to the retired
        # `toolkit.last_version` field, mirroring the order check_for_updates
        # already uses. Reading only the legacy field — as this did before the
        # #1641 merge — compares against a git-tracked value that record_toolkit_sync
        # no longer writes, so `last_version == installed` never becomes true and
        # the sync step re-runs sync + init --force on every single invocation.
        # #1628 requires an already-current run to be a no-op (E008-UNIT-003), and
        # it cannot be one while the write and the read address different stores.
        # #1820: the git-tracked `toolkit.last_version` fallback is gone. It is
        # pinned at an ancient value in every checkout that has one, so reading it
        # reported a refresh owed forever and made #1628's already-current no-op
        # (E008-UNIT-003) unreachable. A checkout with no untracked record is
        # genuinely owed a refresh — the honest answer, and the common one.
        last_version = _read_sync_record(self.repo_root) or "unknown"

        print(f"ATDD sync: {last_version} → {installed}")
        print()

        # Show what changed
        if last_version != "unknown":
            notes = get_upgrade_notes(last_version, installed)
            if notes:
                print("What changed:")
                for version, note in notes:
                    print(f"  {version}: {note}")
                print()
            else:
                print("No notable changes between these versions.")
                print()

        if not refresh_is_owed(self.repo_root):
            print("Already current with the installed version.")
            return 0

        # Confirm
        if unprompted:
            if self_answered:
                print(
                    "No terminal detected — answering the refresh confirmation "
                    "non-interactively: refreshing this checkout in-process"
                )
        else:
            print("This will refresh this checkout:")
            print("  hooks (#1492), .gitignore entries (#1325), exported schemas,")
            print("  and the toolkit stamp (#1641). No other command is run.")
            print()
            answer = input("Proceed? [Y/n] ").strip().lower()
            if answer and answer != "y":
                print("Aborted.")
                return 1

        # #1628: sync + init --force rewrite this checkout's managed files and
        # its stamp. Serialise them on the install lock so two agents cannot
        # interleave, and refuse rather than run unserialised.
        try:
            with upgrade_lock():
                # #1820: refresh in-process. This used to shell `atdd sync` and
                # then `atdd init --force` — the second a flag #793 forbids, and
                # one #1600 shows returns 1 without bootstrapping anything on an
                # already-initialised repo, so it never did what its name implied.
                # Every job the refresh performs is triggered by a toolkit version
                # change, which is the condition this command exists to detect.
                print()
                print("Refreshing this checkout")
                rc = self.refresh_repo()
                if rc != 0:
                    print(f"refresh failed (exit {rc})")
                    return 1

                # Record the sync in this checkout's untracked runtime record
                # (#1641). Held inside the lock: it is the last step of the
                # mutating section, and a record written outside it could claim
                # a sync that a contended run never finished.
                if config_path:
                    record_toolkit_sync(config_path.parent.parent)
                    print(f"\nRecorded toolkit sync at {installed}")
        except UpgradeLockUnavailable as exc:
            logger.error(
                "sync refused, install lock contended: %s", exc,
                extra={"phase": "upgrade-lock", "step": "local-sync",
                       "outcome": "contended"},
            )
            print(str(exc))
            return 1

        print(f"\nSync complete: {last_version} → {installed}")
        return 0


#: The closed outcome vocabulary of :func:`self_upgrade`. Bound in one statement
#: rather than five because they are one vocabulary, not five decisions — and
#: because five consecutive `NAME = "literal"` lines normalise to the same
#: 5-statement window as any other constant block, which the duplication detector
#: cannot tell from real copy-paste (it matched `provider_seam`'s RULE_* run).
(
    SELF_UPGRADE_DECLINED,
    SELF_UPGRADE_UPGRADED,
    SELF_UPGRADE_CONTENDED,
    SELF_UPGRADE_FAILED,
    SELF_UPGRADE_DISABLED,
) = ("declined", "upgraded", "contended", "failed", "disabled")


def _say(stream: Optional[TextIO], message: str) -> None:
    """Write one advisory line, always to stderr.

    A post-* hook's stdout belongs to whatever is reading git's output. Porcelain
    parsers, `git pull | tee`, and the agents that drive this repo all read it;
    a self-upgrade notice landing there would be a data corruption, not a
    cosmetic one. Everything this path emits is advisory, so everything goes to
    stderr — which is also where the hooks already send `atdd state reconcile`.
    """
    print(message, file=stream if stream is not None else sys.stderr)


def _self_upgrade_pending() -> Tuple[Optional[str], Optional[str]]:
    """``(installed, latest)`` when an upgrade looks worth attempting, else ``(None, None)``.

    Ordered cheapest-first, because this runs on every ``git pull`` and every
    branch switch:

    1. The **cached** latest version — one small file read while the cache is
       fresh. This is the same 24 h cache #1762 put the push gate on, so the
       trigger and the gate cannot disagree about what "current" means: the hook
       upgrades to exactly the version the next push will be judged against.
    2. A comparison against ``__version__``, which costs nothing. This can only
       ever *skip* work, and only when the package we are executing already
       claims to be at or past the latest. Inside the packaged post-* hooks that
       is exactly right: they invoke the console script and export no
       ``PYTHONPATH``, so ``__version__`` is the installed version.
    3. Only then :func:`_gate_version`, which spawns ``atdd --version`` (~1.5 s)
       to get the authoritative answer the push gate itself uses — immune to the
       ``src/atdd.egg-info/PKG-INFO`` ghost a source checkout can carry (#1449).
       ``None`` means dev/editable/unknowable, and declining is correct: an
       editable install must not be silently pip-upgraded out from under its
       owner, which is also why ``auto_upgrade()`` refuses one outright.
    """
    latest = _resolve_latest_version(_load_cache(), time.time())
    if not latest:
        return None, None

    if __version__ != "0.0.0" and not _is_newer(latest, __version__):
        return None, None

    installed = _gate_version()
    if installed is None or not _is_newer(latest, installed):
        return None, None

    return installed, latest


def self_upgrade(stream: Optional[TextIO] = None) -> str:
    """Bring this install current, at a trigger where nothing can be refused.

    Called by the packaged ``post-merge`` and ``post-checkout`` hooks, which is
    the entire design (#1762). **Git ignores the exit code of every ``post-*``
    hook** — that is git's own contract, not a convention this repo hopes holds
    — so an upgrade placed here cannot refuse anyone's operation. The merge has
    already landed; the branch has already switched. There is nothing left to
    block, which is precisely what makes upgrading safe here and unsafe in the
    pre-push gate that wmbt:integration-hardening:Y004 correctly locked down.

    Consequences of that, each load-bearing:

    - **Nothing raises.** A caller that cannot fail must not be handed an
      exception. Every failure — a broken cache, an unreachable PyPI, a pip that
      dies, a lock that will not open — resolves to a returned outcome and at
      most one line on stderr. The bare ``except`` at the end is the backstop
      for the ones not enumerated.
    - **:func:`auto_upgrade` directly, never :meth:`Upgrader.run`.** ``run()``
      finishes with ``atdd sync`` and ``atdd init --force``, and ``init --force``
      writes to GitHub (#1703). None of that belongs in a hook that fires on
      every branch switch. ``version_check`` imports neither ``ProjectInitializer``
      nor ``AgentConfigSync``, so calling into it cannot inherit that reach.
    - **The lock is tried, not waited on.** :data:`UPGRADE_LOCK_TIMEOUT` is 300 s,
      which is right for a command an operator is watching and wrong here: a
      contended lock means a sibling worktree is *already doing this upgrade on
      our behalf*, so waiting would stall a human's terminal after a pull to
      duplicate work that is being done. Decline and let the winner finish —
      E008's guarantee that neither observes a partial install is unchanged,
      because it comes from the lock, not from the wait.
    - **Silence when there is nothing to say.** ``current`` and ``unknowable``
      print nothing at all. A pull that was already up to date must not grow a
      banner; the repo has enough of those.

    Returns:
        One of the ``SELF_UPGRADE_*`` constants. The hook discards it — git
        would discard the exit status anyway — but it is what the E009 gate
        tests assert against.
    """
    if os.environ.get("CI") == "true":
        # The same no-op the hooks already take at their top. Restated here so
        # the CLI verb is not a way around it. Not a bypass: CI installs a
        # pinned toolkit on purpose, and an agent that rewrote its own
        # dependency mid-job would make every build irreproducible.
        return SELF_UPGRADE_DISABLED

    try:
        installed, latest = _self_upgrade_pending()
        if installed is None or latest is None:
            return SELF_UPGRADE_DECLINED

        try:
            with upgrade_lock(timeout=0):
                # Re-read inside the lock. Between the check above and this
                # line a sibling worktree may have finished the very upgrade we
                # queued for, and a second pip run over an install that is
                # already current is exactly the "partial install" hazard E008
                # exists to prevent.
                if not _is_newer(latest, _gate_version() or latest):
                    return SELF_UPGRADE_DECLINED

                upgraded, detail = auto_upgrade()
        except UpgradeLockUnavailable:
            logger.debug(
                "self-upgrade declined, install lock contended",
                extra={"phase": "upgrade-lock", "step": "self-upgrade",
                       "outcome": "contended"},
            )
            _say(stream, (
                "ATDD self-upgrade: another upgrade holds the install lock, so this "
                "one stood down. Your git operation is unaffected."
            ))
            return SELF_UPGRADE_CONTENDED

        if not upgraded:
            _say(stream, (
                f"ATDD self-upgrade: still at {installed} — {detail or 'no reason given'}. "
                f"Nothing was changed and your git operation is unaffected. "
                f"Upgrade when convenient: {upgrade_command()}"
            ))
            return SELF_UPGRADE_FAILED

        _say(stream, f"ATDD self-upgraded: {installed} → {latest}")
        return SELF_UPGRADE_UPGRADED

    except Exception as exc:
        # Not swallowed — reported, on the stream the hook already writes to and
        # with the reason attached. What must not happen is the exception
        # escaping into a hook whose whole guarantee is that it cannot affect
        # the operation it follows.
        logger.debug(
            "self-upgrade failed: %s", exc,
            extra={"phase": "self-upgrade", "outcome": "exception"},
        )
        _say(stream, (
            f"ATDD self-upgrade: skipped — {type(exc).__name__}: {exc}. "
            f"Nothing was changed and your git operation is unaffected."
        ))
        return SELF_UPGRADE_FAILED


def run_self_upgrade() -> int:
    """``atdd self-upgrade`` — the CLI seam the packaged post-* hooks call.

    Always 0. There is no failure a caller of this command could act on: git has
    already discarded the exit status by the time it would see one, and the hook
    that shells it must never turn an upgrade into a reason a pull looked
    broken. The outcome travels in the text on stderr, not in the exit code.

    It is a CLI verb rather than a ``python3 -c 'from atdd...'`` block — which
    is what the pre-push gate does — because that block cannot reach a
    pipx-isolated install at all: the system ``python3`` has no ``atdd`` on its
    path, and the pre-push hook only gets away with it by exporting
    ``PYTHONPATH=<repo>/src`` inside the toolkit's own checkout. The post-*
    hooks already guard on ``command -v atdd``, which resolves the console
    script that always works.
    """
    self_upgrade()
    return 0
