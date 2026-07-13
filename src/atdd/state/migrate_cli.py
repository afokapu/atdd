"""``atdd state`` migration verbs (#1400 migrate-projection-authority).

The operator- and CI-facing surface over M8:

- ``atdd state mint-uids`` — backfill an immutable uid into every legacy manifest entry. Its own
  recorded step, so :func:`migrate` stays idempotent (E001).
- ``atdd state migrate-manifest [--mint-uids]`` — the legacy manifest → the uid-keyed committed
  projection. **Refuses before writing anything** when an entry cannot be faithfully projected,
  and reports every offending entry, not the first (C001).
- ``atdd state shadow`` — the drift report against the committed projection AND the
  manifest-derived one. **Exits 0 always**: shadow mode measures, it does not gate (M001).
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

``migrate-manifest`` **exits non-zero having written nothing.** A migration that half-succeeds
leaves a tree that is neither the old truth nor the new one, and the operator's next move depends on
facts the tool destroyed on its way out.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from atdd.state import cutover, hot_path, manifest_fallback, rollout, runbook, shadow
from atdd.state import manifest_migration as migration

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = (
    "mint-uids", "migrate-manifest", "shadow", "hot-path", "manifest-fallback", "cutover",
    "runbook-check", "rollout-check",
)


def add_parsers(sub) -> None:
    """Register the migration verbs on the ``atdd state`` sub-parser."""
    mu = sub.add_parser(
        "mint-uids",
        help="Backfill an immutable uid into every legacy manifest entry (its own recorded step).")
    mu.add_argument("--root", default=None, help="Repository root (default: cwd).")

    mm = sub.add_parser(
        "migrate-manifest",
        help="Migrate .atdd/manifest.yaml into the uid-keyed committed projection. "
             "Refuses before writing anything if an entry cannot be projected.")
    mm.add_argument("--mint-uids", dest="mint", action="store_true",
                    help="Backfill missing uids into the manifest first (a recorded write).")
    mm.add_argument("--owner-actor", default=migration.UNATTRIBUTED_OWNER,
                    help="The owner a legacy entry does not record "
                         f"(default: {migration.UNATTRIBUTED_OWNER}).")
    mm.add_argument("--out", default=None, help="Projection directory (default: the repo's).")
    mm.add_argument("--root", default=None, help="Repository root (default: cwd).")

    sh = sub.add_parser(
        "shadow",
        help="Report projection drift against the committed AND manifest-derived projections. "
             "NON-BLOCKING: exits 0 even when it finds drift (M001).")
    sh.add_argument("--root", default=None, help="Repository root (default: cwd).")

    hp = sub.add_parser(
        "hot-path",
        help="Prove no core lifecycle decision, validator, or gate calls the GitHub API (I7).")
    hp.add_argument("--package", default=None,
                    help="The atdd package directory to walk (default: the running one).")
    hp.add_argument("--root", default=None, help="Repository root (default: cwd).")

    mf = sub.add_parser(
        "manifest-fallback",
        help="Prove no core reader opens, globs, or parses .atdd/manifest.yaml (Y002).")
    mf.add_argument("--package", default=None,
                    help="The atdd package directory to scan (default: the running one).")
    mf.add_argument("--root", default=None, help="Repository root (default: cwd).")

    co = sub.add_parser(
        "cutover", help="Evaluate the three M8 exit criteria. Non-zero while any one is unmet.")
    co.add_argument("--package", default=None, help="The atdd package directory to scan.")
    co.add_argument("--from", dest="from_dir", default=None, help="Projection directory.")
    co.add_argument("--root", default=None, help="Repository root (default: cwd).")

    rb = sub.add_parser(
        "runbook-check",
        help="The migration runbook covers every step the code ships and cites real invariants.")
    rb.add_argument("--root", default=None, help="Repository root (default: cwd).")

    rc = sub.add_parser(
        "rollout-check",
        help="The rollout plan stages shadow before blocking and every one-way door has a rollback.")
    rc.add_argument("--root", default=None, help="Repository root (default: cwd).")


def _root(args) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _package(args) -> Optional[Path]:
    package = getattr(args, "package", None)
    return Path(package).resolve() if package else None


def _fail(report: str) -> int:
    print(report, file=sys.stderr)
    return 1


def _cmd_mint_uids(args) -> int:
    try:
        minted, path = migration.mint_uids(migration.manifest_path(_root(args)))
    except migration.MigrationError as exc:
        _log.warning("uids could not be minted into the legacy manifest",
                     extra={"command": "mint-uids", "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    print(
        f"minted {minted} uid(s) into {path}" if minted
        else f"every entry in {path} already carries a uid (nothing to do)"
    )
    return 0


def _cmd_migrate_manifest(args) -> int:
    root = _root(args)
    try:
        if args.mint:
            minted, path = migration.mint_uids(migration.manifest_path(root))
            print(f"minted {minted} uid(s) into {path}")
        report = migration.migrate(
            root,
            out_dir=Path(args.out).resolve() if args.out else None,
            owner_actor=args.owner_actor,
        )
    except migration.LossyMigrationError as exc:
        # The refusal is the feature: nothing was written, and every offending entry is named.
        _log.warning("refused a lossy migration; the projection directory is untouched",
                     extra={"command": "migrate-manifest", "root": str(root),
                            "defects": len(exc.defects)})
        return _fail(str(exc))
    except migration.MigrationError as exc:
        _log.warning("the manifest could not be migrated",
                     extra={"command": "migrate-manifest", "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    print(report.render())
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
        _log.warning("the hot-path guard could not run",
                     extra={"command": "hot-path", "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_manifest_fallback(args) -> int:
    try:
        report = manifest_fallback.check(_package(args))
    except manifest_fallback.ManifestScanError as exc:
        _log.warning("the manifest-fallback scan could not run",
                     extra={"command": "manifest-fallback", "error": str(exc)})
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
        _log.warning("the runbook check could not run",
                     extra={"command": "runbook-check", "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_rollout_check(args) -> int:
    try:
        report = rollout.check(_root(args))
    except rollout.RolloutError as exc:
        _log.warning("the rollout check could not run",
                     extra={"command": "rollout-check", "error": str(exc)})
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def dispatch(args) -> int:
    """Run the migration verb named by ``args.op``."""
    handlers = {
        "mint-uids": _cmd_mint_uids,
        "migrate-manifest": _cmd_migrate_manifest,
        "shadow": _cmd_shadow,
        "hot-path": _cmd_hot_path,
        "manifest-fallback": _cmd_manifest_fallback,
        "cutover": _cmd_cutover,
        "runbook-check": _cmd_runbook_check,
        "rollout-check": _cmd_rollout_check,
    }
    return handlers[args.op](args)
