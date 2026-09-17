"""``atdd state`` migration verbs (#1400 migrate-projection-authority).

The operator- and CI-facing surface over M8:

- ``atdd state migrate-store`` — mint identity for every work item **in the store**. The live
  migration (CORE-036). Refuses the whole run before any write (C001/E002).
- ``atdd state shadow`` — the drift report against the committed projection. **Exits 0 always**:
  shadow mode measures, it does not gate (M001).
- ``atdd state hot-path`` — no lifecycle decision, validator, or gate calls the GitHub API (Y001).
- ``atdd state manifest-fallback`` — no core reader consults ``.atdd/manifest.yaml`` (Y002).
- ``atdd state cutover`` — the three M8 exit criteria. Non-zero while any one is unmet (K001).
- ``atdd state runbook-check`` / ``atdd state rollout-check`` — the runbook covers every step the
  code ships and cites real invariants (D001); the rollout plan stages shadow before blocking and
  every one-way door carries a rollback (P001).

Two exit codes here will look wrong at a glance, and both are the invariant rather than a bug:

``shadow`` **exits 0 even when it finds drift.** A shadow check that could fail a build is a
blocking check with a misleading name — it would demand the trust the shadow window exists to earn.
``atdd state canonicality`` is the one that blocks.

``migrate-store`` **exits non-zero having written nothing.** A migration that half-succeeds
leaves a tree that is neither the old truth nor the new one, and the operator's next move depends on
facts the tool destroyed on its way out.

``mint-uids`` and ``migrate-manifest`` are **gone** (#2023). Both resolved their input through
``manifest_path(root)``, and ``decommission-manifest`` deleted that file — so both failed with
``no legacy manifest to migrate`` against any real repo. That runbook step says the readers are
"removed, not deprecated in place, because a deprecated reader still reads"; a reader that cannot
even succeed is the same state, louder. ``migrate-store`` is the live replacement. The module
:mod:`atdd.state.manifest_migration` is kept: its acceptances still pin the refuse-before-write
contract it established, and :data:`~atdd.state.manifest_migration.UNATTRIBUTED_OWNER` is still the
shared default owner.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from . import cutover, hot_path, manifest_fallback, rollout, runbook, shadow
# Kept for UNATTRIBUTED_OWNER alone — the shared default owner, which `store_migration` imports
# from here too. No manifest READ path remains: #2023 removed the verbs that resolved
# manifest_path(root). Do not reintroduce one (Y002).
from atdd.state import manifest_migration as migration
from atdd.state.cli_support import add_verb, opt

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = (
    "migrate-store", "shadow", "hot-path",
    "manifest-fallback", "cutover", "runbook-check", "rollout-check",
)


def add_parsers(sub) -> None:
    """Register the migration verbs on the ``atdd state`` sub-parser."""
    _add_migration_verbs(sub)
    _add_check_verbs(sub)


def _add_migration_verbs(sub) -> None:
    """The verbs that WRITE: they move a corpus from one identity scheme to the next."""
    add_verb(
        sub, "migrate-store",
        "Mint an immutable uid and an owner_actor for every work item IN THE STORE. "
        "Refuses the whole run before any write if an object cannot be migrated. "
        "This is the live migration; the manifest-era verbs it replaced were removed in #2023.",
        opt("--owner-actor", default=migration.UNATTRIBUTED_OWNER,
            help="The owner an unattributed object takes "
                 f"(default: {migration.UNATTRIBUTED_OWNER})."),
        opt("--dry-run", action="store_true",
            help="Report what the run would refuse or migrate; write nothing."),
    )

    add_verb(
        sub, "shadow",
        "Report projection drift against the committed projection. "
        "NON-BLOCKING: exits 0 even when it finds drift, or cannot run at all (M001).",
    )


def _add_check_verbs(sub) -> None:
    """The verbs that only REPORT: they answer whether the migration may or did happen."""
    add_verb(
        sub, "hot-path",
        "Prove no core lifecycle decision, validator, or gate calls the GitHub API (I7).",
        opt("--package", default=None,
            help="The atdd package directory to walk (default: the running one)."),
    )

    add_verb(
        sub, "manifest-fallback",
        "Prove no core reader opens, globs, or parses .atdd/manifest.yaml (Y002).",
        opt("--package", default=None,
            help="The atdd package directory to scan (default: the running one)."),
    )

    add_verb(
        sub, "cutover",
        "Evaluate the three M8 exit criteria. Non-zero while any one is unmet.",
        opt("--package", default=None, help="The atdd package directory to scan."),
        opt("--from", dest="from_dir", default=None, help="Projection directory."),
    )

    add_verb(
        sub, "runbook-check",
        "The migration runbook covers every step the code ships and cites real invariants.",
    )

    add_verb(
        sub, "rollout-check",
        "The rollout plan stages shadow before blocking and every one-way door has a rollback.",
    )


def _root(args) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _package(args) -> Optional[Path]:
    package = getattr(args, "package", None)
    return Path(package).resolve() if package else None


def _fail(report: str) -> int:
    print(report, file=sys.stderr)
    return 1


def _report_store_migration_plan(conn) -> int:
    """``--dry-run``: name what would refuse the run, and write nothing.

    Same verdict as the real run, reached the same way — :func:`inspect_store` is the one
    judge — so a clean dry run is a real statement about the next write rather than a
    second opinion that might disagree with it.
    """
    from atdd.state.store import StateStore
    from atdd.state.store_migration import inspect_store

    defects = inspect_store(StateStore(conn))
    if defects:
        return _fail(
            f"{len(defects)} object(s) cannot be migrated; nothing was written:\n"
            + "\n".join(f"  {d.render()}" for d in defects)
        )
    print("every work item in the store can be migrated (nothing was written)")
    return 0


def _cmd_migrate_store(args) -> int:
    """Mint contract-shaped identity for every work item in the store (CORE-036).

    The operator-facing half of :func:`~atdd.state.store_migration.migrate_store_durably`,
    and deliberately only that: the durability contract — immutable backup, separate mutable
    scratch, sidecar-safe swap, all under an exclusive fence — is migration semantics and
    lives with the migration (#2024). This verb resolves the store, chooses dry-run or live,
    and turns the three typed refusals into operator-facing exits.

    It is the verb that runs. Its predecessor ``migrate-manifest`` could not be invoked at all
    once ``decommission-manifest`` deleted the file it read, and was removed in #2023 — a migration
    nobody can invoke is not shipped.

    ``--dry-run`` reports the same refusal without touching the store, so an operator can see
    what stands in the way before committing to a write against the only surviving source of
    truth.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store_migration import (
        MigrationNotCleanError, StoreChangedDuringMigrationError, migrate_store_durably,
    )

    root = _root(args)
    db_path = init_state_store(start=root)

    if args.dry_run:
        conn = connect(db_path)
        try:
            return _report_store_migration_plan(conn)
        finally:
            conn.close()

    try:
        result = migrate_store_durably(db_path, owner_actor=args.owner_actor)
    except StoreChangedDuringMigrationError as exc:
        # Logged at the raise site too, but only with the db path: this is the layer that
        # knows which command the operator ran and against which root
        # (coder.logging.coach-silent-swallow — observably react, do not merely return).
        _log.warning(
            "migrate-store refused: the store was written while the migration prepared",
            extra={"command": "migrate-store", "root": str(root), "error": str(exc)},
        )
        return _fail(f"refusing to migrate: {exc}")
    except migration.LossyMigrationError as exc:
        # The refusal IS the feature: the store was not touched, every offender named.
        _log.warning(
            "refused a lossy store migration; no object was mutated",
            extra={"command": "migrate-store", "root": str(root), "defects": len(exc.defects)},
        )
        return _fail(f"{exc}\n\nThe store is unchanged.")
    except MigrationNotCleanError as exc:
        _log.warning(
            "migrate-store refused: the migrated copy did not inspect clean, so it was not "
            "swapped in",
            extra={"command": "migrate-store", "root": str(root), "defects": len(exc.defects)},
        )
        return _fail(f"{exc}\n\nThe store is unchanged.")

    print(result.report.render())
    print(f"\nBackup (pre-migration store): {result.backup}")
    return 0


def _cmd_shadow(args) -> int:
    """Report drift and exit 0. The exit code is the invariant, not an oversight (M001)."""
    report = shadow.compare_repo(_root(args))
    print(report.render())
    return report.exit_code


def _cmd_hot_path(args) -> int:
    try:
        report = hot_path.check(_package(args))
    except hot_path.ImportBoundaryError as exc:
        _log.warning(
            "the hot-path guard could not run",
            extra={"command": "hot-path", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_manifest_fallback(args) -> int:
    try:
        report = manifest_fallback.check(_package(args))
    except manifest_fallback.ManifestScanError as exc:
        _log.warning(
            "the manifest-fallback scan could not run",
            extra={"command": "manifest-fallback", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_cutover(args) -> int:
    report = cutover.check(
        _root(args),
        package=_package(args),
        projection_dir=Path(args.from_dir).resolve() if args.from_dir else None,
    )
    if not report.met:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_runbook_check(args) -> int:
    try:
        report = runbook.check(_root(args))
    except FileNotFoundError as exc:
        _log.warning(
            "the runbook check could not run",
            extra={"command": "runbook-check", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_rollout_check(args) -> int:
    try:
        report = rollout.check(_root(args))
    except rollout.RolloutError as exc:
        _log.warning(
            "the rollout check could not run",
            extra={"command": "rollout-check", "error": str(exc)},
        )
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def dispatch(args) -> int:
    """Run the migration verb named by ``args.op``."""
    handlers = {
        "migrate-store": _cmd_migrate_store,
        "shadow": _cmd_shadow,
        "hot-path": _cmd_hot_path,
        "manifest-fallback": _cmd_manifest_fallback,
        "cutover": _cmd_cutover,
        "runbook-check": _cmd_runbook_check,
        "rollout-check": _cmd_rollout_check,
    }
    return handlers[args.op](args)
