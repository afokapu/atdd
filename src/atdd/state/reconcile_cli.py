"""``atdd state`` reconcile verbs (#1400 reconcile-local-store).

The operator- and hook-facing surface over :mod:`atdd.state.reconcile`:

- ``atdd state reconcile [--head H]`` — hydrate incoming, replay the local overlay,
  re-project, advance ``store_base_commit``; or stop with a conflict report, keep
  the backup, and exit non-zero (CORE-013).
- ``atdd state freshness``           — is the store still anchored to HEAD? Detects a
  bypassed HEAD-change hook (M001).
- ``atdd state overlay``             — list the local overlay events and their status.
- ``atdd state author <command>``    — the seven local authoring commands, each of
  which appends exactly one typed overlay event (CORE-011).

Exit codes are the contract the hooks and CI rely on: ``0`` reconciled, ``1`` a
conflict or a refusal (dirty store, absent base commit) with an actionable report.

Every verb here runs with **zero** sync providers registered — the whole reconcile
path is satisfiable by ``git`` alone, which is what makes it work against a bare
remote with no GitHub API reachable (I7).

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from atdd.state import authoring, overlay, reconcile as rec
from atdd.state.cli_support import START_DIR_HELP, add_verb, opt
from atdd.state.db import connect, init_state_store
from atdd.state.metadata import StoreBaseCommitError
from atdd.state.reconcile import DirtyStoreError, ReplayConflictError

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = ("reconcile", "freshness", "overlay", "author")


def add_parsers(sub) -> None:
    """Register the reconcile verbs on the ``atdd state`` sub-parser."""
    add_verb(
        sub, "reconcile",
        "Reconcile the local store with the projection at HEAD (hydrate + replay overlay).",
        opt("--head", default=None, help="Target commit (default: the repo's HEAD)."),
        opt("--check-dirty", action="store_true",
            help="Report whether the store carries uncommitted overlay; change nothing."),
        root=START_DIR_HELP,
    )

    add_verb(
        sub, "freshness",
        "Report whether store_base_commit still agrees with HEAD (bypassed-hook check).",
        opt("--head", default=None, help="Compare against this commit (default: HEAD)."),
        root=START_DIR_HELP,
    )

    add_verb(
        sub, "overlay", "List the local overlay events and their status.",
        opt("--all", action="store_true",
            help="Include committed/discarded events, not just the replayable ones."),
        root=START_DIR_HELP,
    )

    auth = sub.add_parser(
        "author", help="Local authoring commands — each appends one typed overlay event.")
    auth_sub = auth.add_subparsers(dest="author_op")

    # Every authoring verb names the object it appends an event for, then says what changed.
    add_verb(auth_sub, "body", "Rewrite the body (body_updated).",
             opt("uid"), opt("--body", required=True), root=None)

    add_verb(
        auth_sub, "transition", "Request a phase transition (phase_transition_requested).",
        opt("uid"),
        opt("--to", dest="to_phase", required=True),
        opt("--from", dest="from_phase", default=None,
            help="Phase moved from (default: the store's current phase)."),
        root=None,
    )

    add_verb(auth_sub, "train", "Set the train (train_updated).",
             opt("uid"), opt("--train", required=True), root=None)

    add_verb(auth_sub, "wmbt", "Attach a WMBT (wmbt_added).",
             opt("uid"), opt("--wmbt", required=True), root=None)

    add_verb(auth_sub, "tombstone", "Retire an object (tombstone_requested).",
             opt("uid"), opt("--reason", required=True), root=None)

    add_verb(auth_sub, "external-ref", "Record a provider ref (external_ref_applied).",
             opt("uid"), opt("--provider", required=True), opt("--ref", required=True), root=None)


def _control_root(root: Optional[str]) -> Path:
    from atdd.state.paths import resolve_control_root  # local: keeps the import surface small

    start = Path(root).resolve() if root else Path.cwd()
    return resolve_control_root(start).control_root


def _open(root: Optional[str]):
    control_root = _control_root(root)
    return control_root, connect(init_state_store(start=control_root))


def _cmd_reconcile(args) -> int:
    control_root = _control_root(args.root)

    if args.check_dirty:
        # pre-rebase's dirty-store protection: report, change nothing.
        conn = connect(init_state_store(start=control_root))
        try:
            events = overlay.replayable_events(conn)
        finally:
            conn.close()
        if not events:
            print("store is clean (no uncommitted overlay events)")
            return 0
        print(f"store is DIRTY: {len(events)} uncommitted overlay event(s)")
        for event in events:
            print(f"  {event.kind} on {event.object_uid} ({event.status})")
        print("Reconcile will back it up and replay the overlay — it will not be overwritten.")
        return 0

    try:
        result = rec.reconcile(control_root, head=args.head)
    except StoreBaseCommitError as exc:
        _log.warning("reconcile refused: store not anchored", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    except ReplayConflictError as exc:
        _log.warning("reconcile stopped with a conflict; the backup is kept",
                     extra={"conflicts": len(exc.report.conflicts)})
        print(exc.report.render())
        return 1
    except DirtyStoreError as exc:
        _log.warning("reconcile refused: dirty store", extra={"error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    print(result.render())
    return 0


def _cmd_freshness(args) -> int:
    report = rec.freshness(_control_root(args.root), head=args.head)
    print(report.render())
    return 1 if report.stale else 0


def _cmd_overlay(args) -> int:
    _root, conn = _open(args.root)
    try:
        events = overlay.all_events(conn) if args.all else overlay.replayable_events(conn)
    finally:
        conn.close()
    if not events:
        print("no overlay events")
        return 0
    for event in events:
        print(f"{event.seq:>4}  {event.status:<10} {event.kind:<28} {event.object_uid}  "
              f"{event.event_id}")
    print(f"{len(events)} overlay event(s)")
    return 0


_AUTHOR_COMMANDS = {
    "body": lambda conn, a: authoring.update_body(conn, a.uid, a.body),
    "transition": lambda conn, a: authoring.request_transition(
        conn, a.uid, a.to_phase, from_phase=a.from_phase),
    "train": lambda conn, a: authoring.update_train(conn, a.uid, a.train),
    "wmbt": lambda conn, a: authoring.add_wmbt(conn, a.uid, a.wmbt),
    "tombstone": lambda conn, a: authoring.request_tombstone(conn, a.uid, a.reason),
    "external-ref": lambda conn, a: authoring.apply_external_ref(
        conn, a.uid, a.provider, a.ref),
}


def _cmd_author(args) -> int:
    if args.author_op is None:
        print(f"usage: atdd state author <{'|'.join(sorted(_AUTHOR_COMMANDS))}>")
        return 2
    _root, conn = _open(args.root)
    try:
        event = _AUTHOR_COMMANDS[args.author_op](conn, args)
    except (KeyError, ValueError, overlay.OverlayLogError) as exc:
        _log.warning("authoring command failed",
                     extra={"op": args.author_op, "error": str(exc)})
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()
    print(f"{event.kind} on {event.object_uid} (overlay event {event.event_id})")
    return 0


def dispatch(args) -> int:
    """Run the reconcile verb named by ``args.op``."""
    handlers = {
        "reconcile": _cmd_reconcile,
        "freshness": _cmd_freshness,
        "overlay": _cmd_overlay,
        "author": _cmd_author,
    }
    return handlers[args.op](args)
