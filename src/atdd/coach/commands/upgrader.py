"""
ATDD upgrade orchestration.

Shows what changed between installed and last_version,
then runs sync + init --force with confirmation.

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
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterator, Optional

from atdd import __version__
from atdd.version_check import (
    get_upgrade_notes,
    _load_repo_config,
    _get_last_toolkit_version,
    _read_sync_record,
    record_toolkit_sync,
    is_outdated,
    auto_upgrade,
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


class Upgrader:
    """Orchestrates atdd upgrade in a consumer repo."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()

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
                            if not auto_upgrade():
                                print(
                                    f"Upgrade failed. Run manually: "
                                    f"{_cmd}"
                                )
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
        last_version = (
            _read_sync_record(self.repo_root)
            or _get_last_toolkit_version(config)
            or "unknown"
        )

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

        if last_version == installed:
            print("Already in sync with installed version.")
            return 0

        # Confirm
        if unprompted:
            if self_answered:
                print(
                    "No terminal detected — answering the sync confirmation "
                    "non-interactively: atdd sync, then atdd init --force"
                )
        else:
            print("This will run:")
            print("  1. atdd sync       (update agent config files)")
            print("  2. atdd init --force (update GitHub infrastructure)")
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
                # Run sync
                print()
                print("Running: atdd sync")
                rc = subprocess.run(
                    [sys.executable, "-m", "atdd", "sync"],
                    cwd=str(self.repo_root),
                ).returncode
                if rc != 0:
                    print(f"atdd sync failed (exit {rc})")
                    return 1

                # Run init --force
                print()
                print("Running: atdd init --force")
                rc = subprocess.run(
                    [sys.executable, "-m", "atdd", "init", "--force"],
                    cwd=str(self.repo_root),
                ).returncode
                if rc != 0:
                    print(f"atdd init --force failed (exit {rc})")
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
