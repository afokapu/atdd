"""``atdd state`` projection verbs (#1400 project-shared-state).

The operator- and CI-facing surface over :mod:`atdd.state.projection`:

- ``atdd state object create --slug <s>``  — mint an immutable uid (E004).
- ``atdd state object rename <uid>``       — rename display metadata only (Y001).
- ``atdd state project [--out DIR]``       — store → canonical per-uid YAML (E001).
- ``atdd state hydrate [--from DIR]``      — committed projection → store (E002).
- ``atdd state digest [--from DIR]``       — the digest over the canonical bytes (E003).
- ``atdd state canonicality [--from DIR]`` — the CI merge gate (C002): non-zero, and
  a diff naming the offending file, whenever ``project(hydrate(p)) != p``.

Every one of these runs with **zero** sync providers registered: none of them
imports, discovers, or consults a provider, and ``canonicality`` reads neither
GitHub nor a developer SQLite store — it round-trips the committed projection
through an in-memory store. That is what makes the gate runnable against a bare
git remote.

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from atdd.state.db import connect, init_state_store
from atdd.state.projection import (
    PROJECTION_RELATIVE,
    ProjectionError,
    check_canonicality,
    hydrate,
    project,
    projection_digest,
)
from atdd.state.store import StateStore
from atdd.state.work_item_writer import mint_work_item, rename_work_item

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = ("object", "project", "hydrate", "digest", "canonicality")

#: Default owner for a work item minted from the CLI. A literal (never the host's
#: username) so a projection minted on one machine matches one minted on another.
DEFAULT_OWNER = "core"


def add_parsers(sub) -> None:
    """Register the projection verbs on the ``atdd state`` sub-parser."""
    obj = sub.add_parser("object", help="Work-item objects — mint and rename by immutable uid.")
    obj_sub = obj.add_subparsers(dest="object_op")
    create = obj_sub.add_parser("create", help="Mint a work item under a fresh immutable uid.")
    create.add_argument("--slug", required=True, help="Display slug (mutable; never identity).")
    create.add_argument("--title", default=None, help="Display title (mutable).")
    create.add_argument("--body", default=None, help="Body text.")
    create.add_argument("--owner", default=DEFAULT_OWNER, help="Owning actor for `body`.")
    create.add_argument("--phase", default="INIT", help="Initial lifecycle phase.")
    create.add_argument("--root", default=None, help="Starting directory (default: cwd).")
    rename = obj_sub.add_parser("rename", help="Rename display metadata; identity does not move.")
    rename.add_argument("uid", help="The immutable uid of the object to rename.")
    rename.add_argument("--slug", default=None, help="New display slug.")
    rename.add_argument("--title", default=None, help="New display title.")
    rename.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    proj = sub.add_parser("project", help="Project the store to canonical per-uid YAML.")
    proj.add_argument("--out", default=None,
                      help=f"Output directory (default: <control-root>/{PROJECTION_RELATIVE}).")
    proj.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    hyd = sub.add_parser("hydrate", help="Rebuild the store from the committed projection.")
    hyd.add_argument("--from", dest="from_dir", default=None,
                     help=f"Projection directory (default: <control-root>/{PROJECTION_RELATIVE}).")
    hyd.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    dig = sub.add_parser("digest", help="Print the digest over the projection's canonical bytes.")
    dig.add_argument("--from", dest="from_dir", default=None, help="Projection directory.")
    dig.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    canon = sub.add_parser(
        "canonicality",
        help="CI gate: prove project(hydrate(projection)) == projection, byte-for-byte.")
    canon.add_argument("--from", dest="from_dir", default=None, help="Projection directory.")
    canon.add_argument("--root", default=None, help="Starting directory (default: cwd).")


def _control_root(root: Optional[str]) -> Path:
    from atdd.state.paths import resolve_control_root  # local: keeps the import surface small

    start = Path(root).resolve() if root else Path.cwd()
    return resolve_control_root(start).control_root


def _projection_dir(args) -> Path:
    """The projection directory an invocation targets — explicit flag or the default."""
    explicit = getattr(args, "from_dir", None) or getattr(args, "out", None)
    if explicit:
        return Path(explicit).resolve()
    return _control_root(getattr(args, "root", None)) / PROJECTION_RELATIVE


def _open_store(root: Optional[str]):
    db_path = init_state_store(start=_control_root(root))
    conn = connect(db_path)
    return conn, StateStore(conn)


def _cmd_object(args) -> int:
    if args.object_op is None:
        print("usage: atdd state object <create|rename>")
        return 2
    conn, _store = _open_store(args.root)
    try:
        if args.object_op == "create":
            obj = mint_work_item(
                conn, slug=args.slug, owner_actor=args.owner,
                title=args.title, body=args.body, phase=args.phase,
            )
            print(obj.uid)
            return 0
        obj = rename_work_item(conn, args.uid, slug=args.slug, title=args.title)
        print(f"{obj.uid}  slug={obj.data.get('slug')}  title={obj.data.get('title')}")
        return 0
    except (KeyError, ValueError) as exc:
        _log.warning("state object op failed",
                     extra={"op": args.object_op, "error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()


def _cmd_project(args) -> int:
    out_dir = _projection_dir(args)
    conn, store = _open_store(args.root)
    try:
        result = project(store, out_dir)
    except ProjectionError as exc:
        _log.warning("projection refused", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()
    for uid in sorted(result.files):
        print(f"{uid}{'':2}{result.files[uid]}")
    print(f"projected {len(result.files)} object(s) → {out_dir}")
    print(f"digest: {result.digest}")
    return 0


def _cmd_hydrate(args) -> int:
    projection_dir = _projection_dir(args)
    conn, store = _open_store(args.root)
    try:
        result = hydrate(projection_dir, store)
    except ProjectionError as exc:
        _log.warning("hydration refused", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()
    print(f"hydrated {result.hydrated} object(s) from {projection_dir}")
    for uid in result.uids:
        print(f"  {uid}")
    return 0


def _cmd_digest(args) -> int:
    print(projection_digest(_projection_dir(args)))
    return 0


def _cmd_canonicality(args) -> int:
    projection_dir = _projection_dir(args)
    try:
        report = check_canonicality(projection_dir)
    except ProjectionError as exc:
        _log.warning("canonicality check refused the projection", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    print(report.render())
    return 0 if report.ok else 1


def dispatch(args) -> int:
    """Run the projection verb named by ``args.op``."""
    handlers = {
        "object": _cmd_object,
        "project": _cmd_project,
        "hydrate": _cmd_hydrate,
        "digest": _cmd_digest,
        "canonicality": _cmd_canonicality,
    }
    return handlers[args.op](args)
