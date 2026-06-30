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

``atdd state migrate-layout`` and later-phase commands are #1168 Phases 5+.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence, Tuple

from atdd.state.db import current_version, init_state_store
from atdd.state.paths import (
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
        print("usage: atdd state version <show|emit|bump --class PATCH|MINOR|MAJOR>")
        return 2

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
                print(f"ERROR: {exc}")
                return 1
            print(f"Bumped release version to {new} ({args.change_class})")
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
    if args.op == "version":
        return _cmd_version(args)
    if args.op == "trace":
        return _cmd_trace(args)

    parser.print_help()
    return 2
