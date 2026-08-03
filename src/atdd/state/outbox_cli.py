"""``atdd state outbox`` — the surface that makes a stranded outbox loud (#1655).

The outbox is a queue of *decisions* the store has already made: a version to
publish, an issue to file, a body to update. Before this module, a decision that
could not be delivered had nowhere to go and nobody to tell:

- ``atdd state providers`` printed "core runs provider-free (spec §8.1)" and exited
  0 — true, reassuring, and silent about the rows queued behind it;
- ``atdd state sync`` printed a pending count next to the remedy "pass ``--push``" —
  a remedy that cannot work when no registered provider claims those rows' routing
  key.

Zero registered providers stays a **supported** state (ext#40 Phase 2 decision 3).
Core being provider-free is the design, not the bug. The bug was that core reported
that state as healthy while the backlog grew. These verbs report it instead:

- ``atdd state outbox list`` — every row, with the routability core can actually
  compute. Includes discarded rows: a disposition that disappears from the listing
  is indistinguishable from a delete.
- ``atdd state outbox check`` — **exits non-zero when rows are stranded.** The
  primitive a hook, a CI job, or a human can gate on.
- ``atdd state outbox discard <id> --reason ...`` — retire one undeliverable row
  against a recorded reason. One row per invocation, deliberately: a backlog that
  can be cleared in a single sweep is a backlog nobody read.

**No verb here drains anything.** Draining is ``atdd state sync --push``, and it
needs a registered provider. Discarding is the alternative for a row that no
provider will ever accept — and it is never a silent ``DELETE``: the row is kept,
its status becomes ``discarded``, and the reason is stored beside it so "why is this
not in GitHub?" stays answerable.

Dependency discipline: stdlib + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

from atdd.state.cli_support import add_verb, opt
from atdd.state.db import connect, init_state_store
from atdd.state.paths import resolve_control_root
from atdd.state.providers import discover_providers
from atdd.state.store import StateStore, SyncMessage
from atdd.state.sync_engine import DrainabilityReport, assess_drainability

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = ("outbox",)

#: Sub-verbs of ``atdd state outbox``.
ACTIONS = ("list", "check", "discard")


def add_parsers(sub) -> None:
    """Register ``atdd state outbox`` on the ``atdd state`` sub-parser."""
    add_verb(
        sub, "outbox",
        "Inspect the outbox, report rows nothing registered can route, and "
        "retire one against a recorded reason.",
        opt("action", choices=list(ACTIONS),
            help="list: every row + routability. check: exit non-zero if stranded. "
                 "discard: retire one row (requires --reason)."),
        opt("outbox_id", nargs="?", type=int, default=None,
            help="The outbox row id (discard only)."),
        opt("--reason", default=None,
            help="Why this row is being retired. Required by discard, and recorded "
                 "on the row — a discard with no reason is refused."),
        opt("--json", dest="as_json", action="store_true",
            help="Emit machine-readable JSON instead of the operator report."),
    )


def _open_store(args):
    start = Path(getattr(args, "root", None) or Path.cwd()).resolve()
    resolution = resolve_control_root(start)
    db_path = init_state_store(start=resolution.control_root)
    return connect(db_path)


def _assess(store: StateStore) -> DrainabilityReport:
    return assess_drainability(store, discover_providers())


def _summarise(msg: SyncMessage) -> str:
    """One short, non-leaking line about what a row would do. Never dumps a whole body."""
    payload = msg.payload if isinstance(msg.payload, dict) else {}
    for key in ("version", "title", "issue_number"):
        if payload.get(key) not in (None, ""):
            return f"{key}={payload[key]}"
    return f"{len(payload)} payload field(s)"


def _row_as_dict(msg: SyncMessage, routable_keys: set) -> Dict[str, object]:
    """One outbox row as JSON-safe fields.

    ``routable`` is ``None`` for anything not pending: a sent or discarded row has
    no routing question left to answer, and reporting ``false`` for it would read as
    "this could not be delivered" when in fact it already was, or was retired.
    """
    return {
        "id": msg.id,
        "provider": msg.provider,
        "operation": msg.operation,
        "status": msg.status,
        "created_at": msg.created_at,
        "routable": (msg.provider in routable_keys) if msg.status == "pending" else None,
        "disposition": msg.disposition,
    }


def _cmd_list(args, store: StateStore) -> int:
    rows = store.sync.all_outbox()
    report = _assess(store)
    routable_keys = set(report.registered)

    if getattr(args, "as_json", False):
        print(json.dumps({
            "measured_at": _now(store),
            "total": len(rows),
            "pending": report.pending,
            "routable": report.routable,
            "unroutable": report.unroutable,
            "registered_providers": report.registered,
            "rows": [_row_as_dict(m, routable_keys) for m in rows],
        }, indent=2))
        return 0

    if not rows:
        print("outbox: empty.")
        return 0

    print(f"outbox as of {_now(store)} — {len(rows)} row(s):")
    print(f"{'id':>4}  {'status':<10} {'routable':<9} {'provider':<10} "
          f"{'operation':<16} {'created':<20} detail")
    for m in rows:
        if m.status != "pending":
            routable = "-"
        else:
            routable = "yes" if m.provider in routable_keys else "NO"
        detail = m.disposition or _summarise(m)
        print(f"{m.id:>4}  {m.status:<10} {routable:<9} {m.provider:<10} "
              f"{(m.operation or ''):<16} {(m.created_at or ''):<20} {detail}")
    print()
    print(report.render())
    return 0


def _cmd_check(args, store: StateStore) -> int:
    """Exit non-zero while any pending row has no registered receiver.

    This is the verb a hook or CI job gates on, so its exit code carries the whole
    meaning: **0 = nothing is silently accumulating.**
    """
    report = _assess(store)
    if getattr(args, "as_json", False):
        print(json.dumps({
            "measured_at": _now(store),
            "pending": report.pending,
            "routable": report.routable,
            "unroutable": report.unroutable,
            "unroutable_by_provider": report.unroutable_by_provider,
            "oldest_unroutable_at": report.oldest_unroutable_at,
            "registered_providers": report.registered,
            "stranded": report.stranded,
        }, indent=2))
        return 1 if report.stranded else 0
    if report.stranded:
        print(report.render(), file=sys.stderr)
        return 1
    print(report.render())
    return 0


def _cmd_discard(args, store: StateStore) -> int:
    if args.outbox_id is None:
        print("ERROR: discard needs an outbox row id: "
              "atdd state outbox discard <id> --reason '...'", file=sys.stderr)
        return 1
    if not (args.reason or "").strip():
        print(
            f"ERROR: refusing to discard outbox#{args.outbox_id} without --reason. "
            f"The reason is the point: a discard with none is a delete with extra steps. "
            f"Run `atdd state outbox list` first and record why the row is undeliverable.",
            file=sys.stderr,
        )
        return 1
    try:
        store.sync.discard(args.outbox_id, args.reason)
    except ValueError as exc:
        _log.warning(
            "outbox discard refused",
            extra={"outbox_id": args.outbox_id, "error": str(exc)},
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _log.info(
        "outbox row discarded with a recorded reason",
        extra={"outbox_id": args.outbox_id, "reason": args.reason.strip()},
    )
    print(f"outbox#{args.outbox_id} discarded — {args.reason.strip()}")
    report = _assess(store)
    print(report.render())
    return 0


def _now(store: StateStore) -> str:
    """The store's own clock, so a reported count is anchored to when it was true."""
    row = store.conn.execute("SELECT datetime('now')").fetchone()
    return str(row[0]) if row else "unknown"


def dispatch(args) -> int:
    """Run the ``atdd state outbox`` action named by ``args.action``."""
    handlers = {"list": _cmd_list, "check": _cmd_check, "discard": _cmd_discard}
    conn = _open_store(args)
    try:
        return handlers[args.action](args, StateStore(conn))
    finally:
        conn.close()
