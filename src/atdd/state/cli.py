"""`atdd state` command surface (#1168 Phase 1, #1177).

Phase 1 ships two enforcement commands described in #1168:

- ``atdd state doctor`` — print the detected layout (Control Root, Git worktree
  root, layout mode, State Store path) and a status line.
- ``atdd state layout --check`` — validate the filesystem layout is legal and
  exit non-zero on a violation (e.g. a per-worktree State Store).
- ``atdd state init`` — create (if needed) and migrate the State Store SQLite
  database at the resolved Control Root (#1181).
- ``atdd state import-manifest`` — import ``.atdd/manifest.yaml`` operational
  state into the State Store and write a backup (#1183).

- ``atdd state migrate-layout`` — consolidate to a single project-root State
  Store by MERGING every per-worktree store into it, de-duplicating work_items on
  their GitHub-issue external ref, and deleting the per-worktree DBs (#1346,
  completing #1315 / #1168 Phase 5).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence, Tuple

from dataclasses import dataclass, field

from atdd.state.db import current_version, init_state_store
from atdd.state.paths import (
    ATDD_DIR,
    OPERATIONAL_ATDD_DIRS,
    STATE_STORE_RELATIVE,
    AmbiguousControlRootError,
    ControlRootNotFoundError,
    ControlRootResolution,
    check_layout,
    is_scratch_atdd,
    resolve_control_root,
)

_log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd state",
        description="ATDD State Store — local operational data (#1168).",
    )
    sub = parser.add_subparsers(dest="op")

    doctor = sub.add_parser("doctor", help="Print and validate the detected State Store layout.")
    doctor.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    layout = sub.add_parser("layout", help="Layout guards.")
    layout.add_argument("--check", action="store_true", help="Validate the layout; non-zero on violation.")
    layout.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    init = sub.add_parser("init", help="Create (if needed) and migrate the State Store SQLite database.")
    init.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    imp = sub.add_parser("import-manifest",
                         help="Import .atdd/manifest.yaml operational state into the State Store (#1183).")
    imp.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    ml = sub.add_parser(
        "migrate-layout",
        help="Consolidate to a single project-root State Store, rebuilt from main's "
             "manifest (#1315 / #1168 Phase 5).")
    ml.add_argument("--project-root", default=None,
                    help="Project root (parent of main/). Default: derived from --root/cwd via git.")
    ml.add_argument("--root", default=None,
                    help="Starting directory used to derive the project root (default: cwd).")

    version = sub.add_parser(
        "version", help="Release version source-of-truth (#1172).")
    version_sub = version.add_subparsers(dest="version_op")
    v_show = version_sub.add_parser("show", help="Print the current release version (with context).")
    v_show.add_argument("--root", default=None)
    v_emit = version_sub.add_parser(
        "emit", help="Print the build-consumable version string (0.0.0+local if no store version).")
    v_emit.add_argument("--root", default=None)
    v_bump = version_sub.add_parser("bump", help="Bump the release version (writes store + appends event).")
    v_bump.add_argument("--class", dest="change_class", required=True,
                        choices=["PATCH", "MINOR", "MAJOR"], help="Semver change class.")
    v_bump.add_argument("--pr", default=None, help="Originating PR number (recorded in the bump event).")
    v_bump.add_argument("--root", default=None)
    v_set = version_sub.add_parser(
        "set", help="Reconcile the current release version to an explicit value "
        "(e.g. the latest git tag) without emitting a version_decided signal.")
    v_set.add_argument("version", help="The version to set as authoritative current (X.Y.Z).")
    v_set.add_argument("--root", default=None)
    v_rb = version_sub.add_parser(
        "reconcile-base",
        help="Print the authoritative release base = max(git tag, PyPI latest) for the "
        "next bump (#1326). Falls back to the git tag if PyPI is unreachable.")
    v_rb.add_argument("--git-tag", dest="git_tag", default=None,
                      help="The latest git tag core (X.Y.Z, without a leading 'v').")
    v_rb.add_argument("--package", default="atdd",
                      help="PyPI package to query for the published latest (default: atdd).")
    v_rb.add_argument("--no-pypi", dest="no_pypi", action="store_true",
                      help="Skip the PyPI query and resolve from the git tag only.")
    v_rb.add_argument("--root", default=None)

    # Projection spine (#1400): object create/rename, project, hydrate, digest,
    # canonicality. Its parsers live next to their implementation.
    from atdd.state.projection_cli import add_parsers as add_projection_parsers

    add_projection_parsers(sub)

    # Reconcile spine (#1400): reconcile, freshness, overlay, author. Its parsers
    # live next to their implementation.
    from atdd.state.reconcile_cli import add_parsers as add_reconcile_parsers

    add_reconcile_parsers(sub)

    trace = sub.add_parser("trace", help="Hub trace export/promotion (#1185).")
    trace_sub = trace.add_subparsers(dest="trace_op")
    t_list = trace_sub.add_parser("list", help="List Hub sessions.")
    t_list.add_argument("--root", default=None)
    t_export = trace_sub.add_parser("export", help="Export a session's trace as JSON.")
    t_export.add_argument("--session", required=True)
    t_export.add_argument("--root", default=None)
    t_promote = trace_sub.add_parser("promote", help="Promote a session's trace to the outbox.")
    t_promote.add_argument("--session", required=True)
    t_promote.add_argument("--root", default=None)

    return parser


def _start_dir(root: Optional[str]) -> Path:
    return Path(root).resolve() if root else Path.cwd()


def _resolve_or_report(start: Path) -> Tuple[Optional[ControlRootResolution], int]:
    """Resolve the Control Root, or log + print the error and return an exit code.

    Returns ``(resolution, 0)`` on success or ``(None, 2)`` on a layout failure
    (ambiguous parent/child ``.atdd/`` or no Control Root found). The error is
    both logged (operational diagnostics) and printed (operator-facing CLI).
    """
    try:
        return resolve_control_root(start), 0
    except (AmbiguousControlRootError, ControlRootNotFoundError) as exc:
        _log.warning(
            "state layout resolution failed",
            extra={"start": str(start), "error": type(exc).__name__},
        )
        print(f"ERROR: {exc}")
        return None, 2


def _cmd_doctor(root: Optional[str]) -> int:
    start = _start_dir(root)
    print("ATDD State Store Doctor")
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    gwr = resolution.git_worktree_root
    print(f"Control Root:       {resolution.control_root}")
    print(f"Git Worktree Root:  {gwr if gwr is not None else '(none — not in a git worktree)'}")
    print(f"Layout Mode:        {resolution.layout_mode.value}")
    print(f"State Store:        {resolution.state_store_path}")

    # Diagnose (do not fail on) a scratch .atdd/ at the worktree parent that the
    # resolver ignored — e.g. a flat-worktree parent tools filled with
    # cache/runtime/diagnostics (#1179).
    parent = resolution.control_root.parent
    if is_scratch_atdd(parent):
        print(f"Note:               ignored scratch .atdd at {parent / '.atdd'} (no Control Root marker)")

    violations = check_layout(resolution.control_root)
    if violations:
        for v in violations:
            print(f"ERROR: {v}")
        print("Status:             INVALID")
        return 1
    if not resolution.state_store_exists:
        # Not created yet — informational, not a failure. Initialize with `atdd state init`.
        print("Status:             OK (State Store not yet created — run `atdd state init`)")
        return 0
    print("Status:             OK")
    return 0


def _cmd_layout_check(root: Optional[str]) -> int:
    start = _start_dir(root)
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    violations = check_layout(resolution.control_root)
    if violations:
        for v in violations:
            print(f"ERROR: {v}")
        return 1
    print(f"Layout OK: {resolution.layout_mode.value} (Control Root: {resolution.control_root})")
    return 0


def _cmd_init(root: Optional[str]) -> int:
    start = _start_dir(root)
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    existed = resolution.state_store_exists
    db_path = init_state_store(db_path=resolution.state_store_path)
    from atdd.state.db import connect  # local import: keep module import surface small

    conn = connect(db_path)
    try:
        version = current_version(conn)
    finally:
        conn.close()
    verb = "already initialized" if existed else "initialized"
    print(f"ATDD State Store {verb}: {db_path}")
    print(f"Control Root: {resolution.control_root}  ({resolution.layout_mode.value})")
    print(f"Schema version: {version}")
    return 0


def _cmd_import_manifest(root: Optional[str]) -> int:
    start = _start_dir(root)
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    from atdd.state.manifest_import import import_manifest  # local: keeps yaml off the hot path

    try:
        result = import_manifest(control_root=resolution.control_root)
    except FileNotFoundError as exc:
        _log.warning("manifest import found no manifest", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    print(f"Imported {result.imported} work item(s) ({result.external_refs} external ref(s)) "
          f"into {result.db_path}")
    print(f"Backup written: {result.backup_path}")
    if result.skipped:
        print(f"Skipped {result.skipped}: {'; '.join(result.skipped_reasons)}")
    if result.collisions:
        print(f"Duplicate issue numbers ({len(result.collisions)}; first-in-manifest wins the ref):")
        for c in result.collisions:
            print(f"  - {c}")
    return 0


@dataclass
class MigrateLayoutResult:
    """Outcome of a single-store consolidation (#1315 / #1346).

    ``merged`` — work_items carried into the control-root store from a
    per-worktree store (rows that did not already exist there).
    ``deduped`` — work_items collapsed onto an existing control-root row because
    both are linked to the same GitHub issue via ``external_refs``.
    ``deleted`` — the per-worktree State Store files removed after their rows
    were folded in (they cannot re-diverge).
    ``extensions_folded`` — substrate install artifacts (extensions/workspaces)
    copied from a per-worktree ``.atdd/`` into the control-root ``.atdd/``.
    ``operational_removed`` — per-worktree operational ``.atdd/`` install dirs and
    lock files removed after being folded into the control root.
    """

    store_path: Path
    merged: int
    deduped: int
    deleted: list
    extensions_folded: int = 0
    operational_removed: list = field(default_factory=list)


#: Lifecycle-phase ordering used to keep the most-advanced state when two rows
#: linked to the same GitHub issue are de-duplicated during consolidation.
_PHASE_RANK = {
    phase: rank
    for rank, phase in enumerate(
        ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]
    )
}


def _more_advanced(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the more-advanced of two lifecycle states (unknown states rank low)."""
    return a if _PHASE_RANK.get(a or "", -1) >= _PHASE_RANK.get(b or "", -1) else b


def _delete_store_files(db_path: Path) -> None:
    """Remove a State Store SQLite file and its WAL/SHM sidecars."""
    for suffix in ("", "-wal", "-shm"):
        sidecar = db_path.parent / (db_path.name + suffix)
        if sidecar.is_file():
            sidecar.unlink()


def _github_issue_ref(refs) -> Optional[str]:
    for r in refs:
        if r.provider == "github" and r.ref_kind == "issue":
            return r.ref_value
    return None


def migrate_layout(
    start: Optional[str] = None,
    *,
    project_root: Optional[str] = None,
) -> MigrateLayoutResult:
    """Consolidate every per-worktree State Store into ONE control-root store.

    The #1346 completion of #1315's deferred consolidation. Unlike the earlier
    rebuild-from-manifest one-shot (which dropped worktree-only rows and left the
    stale DBs on disk to re-diverge), this performs a genuine **merge**:

    - every ``<child>/.atdd/state/state.sqlite`` under the project root is folded
      into the control-root store;
    - ``work_items`` are **de-duplicated on their ``external_refs`` GitHub-issue
      link** — when a row for the same issue already exists at the control root,
      the existing (GitHub-linked authoritative) row wins and keeps the
      most-advanced lifecycle state; otherwise the row (with its external refs and
      events) is carried over verbatim;
    - after a source store's rows are folded in, its per-worktree DB is
      **deleted** so it cannot re-diverge.

    ``project_root`` overrides the derived location (parent of ``main/``); by
    default it is resolved from ``start``/cwd via the git-backed resolver.
    """
    from atdd.state.db import connect  # local: keep the module import surface small
    from atdd.state.store import StateStore

    if project_root is not None:
        root = Path(project_root).resolve()
    else:
        start_dir = _start_dir(start)
        root = resolve_control_root(start_dir).control_root

    shared_store = root / STATE_STORE_RELATIVE
    target = StateStore(connect(init_state_store(db_path=shared_store)))

    sources: list = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        rogue = child / STATE_STORE_RELATIVE
        if rogue.is_file() and rogue.resolve() != shared_store.resolve():
            sources.append(rogue)

    merged = 0
    deduped = 0
    deleted: list = []
    for src_db in sources:
        # Apply migrations to the source first so a partially-initialized or empty
        # per-worktree store (e.g. a bare file) presents the schema and merges as
        # an empty store rather than raising.
        src_conn = connect(init_state_store(db_path=src_db))
        src = StateStore(src_conn)
        try:
            for obj in src.objects.list():
                refs = src.external_refs.for_object(obj.uid)
                events = src.events.list(object_uid=obj.uid)
                issue = _github_issue_ref(refs)
                existing = (
                    target.external_refs.resolve("github", "issue", issue)
                    if issue is not None
                    else None
                )
                if existing is not None:
                    # de-dup: the GitHub-linked control-root row wins; keep the
                    # most-advanced lifecycle state and fold in the source events.
                    survivor = target.objects.get(existing.object_uid)
                    best = _more_advanced(survivor.state if survivor else None, obj.state)
                    if survivor is not None and best != survivor.state:
                        target.objects.set_state(existing.object_uid, best)
                    for ev in events:
                        target.events.append(
                            ev.event_type, object_uid=existing.object_uid, payload=ev.payload
                        )
                    deduped += 1
                    continue
                # carry over: a row that does not yet exist at the control root.
                # noqa: N+1 — a one-time bounded consolidation migration (runs once
                # per project to fold divergent per-worktree stores in), not a hot
                # path; per-row writes are inherent to the merge.
                target.objects.upsert(obj.uid, obj.kind, state=obj.state, data=obj.data)  # noqa: N+1
                for r in refs:
                    target.external_refs.link(
                        r.object_uid, r.provider, r.ref_kind, r.ref_value, data=r.data
                    )
                for ev in events:
                    target.events.append(ev.event_type, object_uid=obj.uid, payload=ev.payload)
                merged += 1
        finally:
            src_conn.close()
        _delete_store_files(src_db)
        deleted.append(src_db)
        _log.info(
            "consolidated per-worktree store into control-root store",
            extra={"source": str(src_db), "control_root_store": str(shared_store)},
        )

    # Fold per-worktree operational .atdd/ installs (extensions/workspaces + lock)
    # into the control-root .atdd/, then remove the per-worktree copies (#1346).
    extensions_folded, operational_removed = _fold_operational_subtrees(root)

    return MigrateLayoutResult(
        store_path=shared_store, merged=merged, deduped=deduped, deleted=deleted,
        extensions_folded=extensions_folded, operational_removed=operational_removed,
    )


_SUBSTRATE_LOCK = "substrate.lock.yaml"


def _fold_operational_subtrees(root: Path) -> tuple:
    """Fold every per-worktree operational ``.atdd/`` install into the control root.

    For each child worktree of ``root`` (other than the control-root ``.atdd/``):
    copy any ``extensions/<id>/<ver>`` or ``workspaces/<id>/<ver>`` install the
    control root lacks (the control-root copy WINS on an id+version conflict — no
    overwrite), union its ``substrate.lock.yaml`` artifacts into the control-root
    lock (dedup by id+version), then remove the per-worktree install dirs and lock
    file. Scratch dirs (runtime/cache/diagnostics) are left untouched. Returns
    ``(artifacts_folded, removed_paths)``.
    """
    import shutil

    folded = 0
    removed: list = []
    control_atdd = root / ATDD_DIR
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        child_atdd = child / ATDD_DIR
        if child_atdd.resolve() == control_atdd.resolve() or not child_atdd.is_dir():
            continue
        touched = False
        for name in OPERATIONAL_ATDD_DIRS:
            src_dir = child_atdd / name
            if not src_dir.is_dir():
                continue
            # copy each <id>/<version> the control root lacks (never overwrite).
            for pid_dir in sorted(p for p in src_dir.iterdir() if p.is_dir()):
                for ver_dir in sorted(p for p in pid_dir.iterdir() if p.is_dir()):
                    dest = control_atdd / name / pid_dir.name / ver_dir.name
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(ver_dir, dest)
                        folded += 1
            shutil.rmtree(src_dir)
            removed.append(src_dir)
            touched = True
        # union the per-worktree substrate lock into the control-root lock.
        src_lock = child_atdd / _SUBSTRATE_LOCK
        if src_lock.is_file():
            _union_substrate_lock(control_atdd / _SUBSTRATE_LOCK, src_lock)
            src_lock.unlink()
            removed.append(src_lock)
            touched = True
        if touched:
            _log.info(
                "consolidated per-worktree operational .atdd/ into control root",
                extra={"source": str(child_atdd), "control_root": str(control_atdd)},
            )
    return folded, removed


def _union_substrate_lock(dest_lock: Path, src_lock: Path) -> None:
    """Union ``src_lock``'s artifacts into ``dest_lock`` (dedup by id+version)."""
    import yaml  # local: keep yaml off the store hot path

    src_data = yaml.safe_load(src_lock.read_text()) or {}
    if dest_lock.is_file():
        dest_data = yaml.safe_load(dest_lock.read_text()) or {}
    else:
        dest_data = {"schema_version": src_data.get("schema_version", "1.0.0"), "artifacts": []}
    seen = {(a.get("id"), a.get("version")) for a in dest_data.get("artifacts", [])}
    for art in src_data.get("artifacts", []):
        key = (art.get("id"), art.get("version"))
        if key not in seen:
            dest_data.setdefault("artifacts", []).append(art)
            seen.add(key)
    dest_lock.parent.mkdir(parents=True, exist_ok=True)
    dest_lock.write_text(yaml.safe_dump(dest_data, sort_keys=False))


def _cmd_migrate_layout(args) -> int:
    result = migrate_layout(start=args.root, project_root=args.project_root)
    print(f"Consolidated into single control-root State Store: {result.store_path}")
    print(
        f"Merged {result.merged} work item(s); de-duplicated {result.deduped} "
        "by GitHub-issue external ref."
    )
    if result.extensions_folded or result.operational_removed:
        print(
            f"Folded {result.extensions_folded} operational install(s) "
            f"(extensions/workspaces) into the control-root .atdd/ and removed "
            f"{len(result.operational_removed)} per-worktree operational path(s)."
        )
    if result.deleted:
        print(f"Deleted {len(result.deleted)} per-worktree store(s):")
        for p in result.deleted:
            print(f"  - {p}")
    else:
        print("No per-worktree stores found to consolidate.")
    return 0


def _open_store(root: Optional[str]):
    """Resolve, init, and open the State Store; return (resolution, conn) or (None, rc)."""
    start = _start_dir(root)
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return None, rc
    from atdd.state.db import connect, init_state_store
    db = init_state_store(start=resolution.control_root)
    return resolution, connect(db)


def _cmd_version(args) -> int:
    from atdd.state import version as ver

    if args.version_op is None:
        print("usage: atdd state version <show|emit|bump --class PATCH|MINOR|MAJOR|set X.Y.Z|"
              "reconcile-base --git-tag X.Y.Z>")
        return 2

    if args.version_op == "reconcile-base":
        # Pure computation + a best-effort PyPI query; no store needed. The base is
        # max(git tag, PyPI latest) so the next bump never regresses below the
        # published latest; PyPI-unreachable falls back to the git tag (#1326).
        pypi_latest = None if args.no_pypi else ver.latest_on_pypi(args.package)
        try:
            base = ver.resolve_release_base(args.git_tag, pypi_latest)
        except ver.VersionError as exc:
            _log.warning("version reconcile-base failed", extra={"error": str(exc),
                                                                 "git_tag": args.git_tag})
            print(f"ERROR: {exc}")
            return 1
        print(base)
        return 0

    resolution, conn_or_rc = _open_store(args.root)
    if resolution is None:
        return conn_or_rc
    conn = conn_or_rc
    try:
        if args.version_op == "emit":
            # Build-consumable string; never fails (matches the build-hook fallback).
            print(ver.emit(conn))
            return 0
        if args.version_op == "show":
            try:
                current = ver.current(conn)
            except ver.VersionError as exc:
                _log.warning("version show: no release version", extra={"error": str(exc)})
                print(f"ERROR: {exc}")
                return 1
            from atdd.state.projections import release_projection
            row = release_projection(conn)
            print(f"Release version: {current}")
            print(f"Bumps recorded:  {row.bump_count if row else 0}")
            print(f"State Store:     {resolution.state_store_path}")
            return 0
        if args.version_op == "bump":
            try:
                new = ver.bump(conn, args.change_class, pr=args.pr)
            except ver.VersionError as exc:
                _log.warning("version bump failed", extra={"error": str(exc),
                                                           "change_class": args.change_class})
                print(f"ERROR: {exc}")
                return 1
            print(f"Bumped release version to {new} ({args.change_class})")
            return 0
        if args.version_op == "set":
            try:
                new = ver.set_version(conn, args.version)
            except ver.VersionError as exc:
                _log.warning("version set failed", extra={"error": str(exc),
                                                          "version": args.version})
                print(f"ERROR: {exc}")
                return 1
            print(f"Set release version to {new} (reconcile; no version_decided signal)")
            return 0
        print(f"unknown version op: {args.version_op}")
        return 2
    finally:
        conn.close()


def _cmd_trace(args) -> int:
    import json as _json

    from atdd.state import hub
    from atdd.state.store import StateStore

    if args.trace_op is None:
        print("usage: atdd state trace <list|export|promote>")
        return 2

    resolution, conn_or_rc = _open_store(args.root)
    if resolution is None:
        return conn_or_rc
    conn = conn_or_rc
    try:
        store = StateStore(conn)
        if args.trace_op == "list":
            rows = hub.hub_session_projection(store)
            if not rows:
                print("(no Hub sessions)")
            for r in rows:
                print(f"{r.uid}  state={r.state}  adapters={len(r.adapters)}  events={r.event_count}")
            return 0
        if args.trace_op == "export":
            try:
                print(_json.dumps(hub.export_trace(store, args.session), indent=2, sort_keys=True))
            except KeyError as exc:
                _log.warning("trace export: session not found",
                             extra={"session": args.session, "error": str(exc)})
                print(f"ERROR: {exc}")
                return 1
            return 0
        if args.trace_op == "promote":
            try:
                outbox_id = hub.promote_trace(store, args.session)
            except KeyError as exc:
                _log.warning("trace promote: session not found",
                             extra={"session": args.session, "error": str(exc)})
                print(f"ERROR: {exc}")
                return 1
            print(f"Promoted trace for {args.session} → outbox#{outbox_id}")
            return 0
        print(f"unknown trace op: {args.trace_op}")
        return 2
    finally:
        conn.close()


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.op == "doctor":
        return _cmd_doctor(args.root)
    if args.op == "layout":
        if not args.check:
            parser.parse_args(["layout", "--help"])
            return 2
        return _cmd_layout_check(args.root)
    if args.op == "init":
        return _cmd_init(args.root)
    if args.op == "import-manifest":
        return _cmd_import_manifest(args.root)
    if args.op == "migrate-layout":
        return _cmd_migrate_layout(args)
    if args.op == "version":
        return _cmd_version(args)
    if args.op == "trace":
        return _cmd_trace(args)

    from atdd.state.projection_cli import OPS as PROJECTION_OPS, dispatch as projection_dispatch

    if args.op in PROJECTION_OPS:
        return projection_dispatch(args)

    from atdd.state.reconcile_cli import OPS as RECONCILE_OPS, dispatch as reconcile_dispatch

    if args.op in RECONCILE_OPS:
        return reconcile_dispatch(args)

    parser.print_help()
    return 2
