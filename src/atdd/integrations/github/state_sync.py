"""State Store ⇄ GitHub provider sync (#1168 Phase 5, #1184).

Bridges the local State Store (operational truth) with GitHub (external
side-effect truth) through the `outbox` / `inbox` queues and `external_refs`:

- **push** drains the `outbox` (local → GitHub): create issue / add label /
  comment, each dispatched to a :class:`GitHubClient`; a created issue is
  recorded back as an `external_ref`.
- **apply** drains the `inbox` (GitHub → local): apply imported issue state to
  the linked work item via its `external_ref`.

The client is a Protocol so tests inject a fake — no live GitHub in CI. The real
:class:`GhCliClient` shells to ``gh`` via :func:`atdd.integrations.github._gh.run_gh`.

Layer direction: this module lives in ``atdd.integrations.github`` and imports
``atdd.state`` (allowed). ``atdd.state`` never imports back (foundational layer).
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol, Sequence

from atdd.integrations.github._gh import run_gh
from atdd.state.db import connect, init_state_store
from atdd.state.paths import resolve_control_root
from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

GITHUB_PROVIDER = "github"


class GitHubClient(Protocol):
    """Minimal GitHub operations the outbox dispatches to."""

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> str:
        """Create an issue; return its number as a string."""

    def add_label(self, issue_number: str, label: str) -> None: ...

    def add_comment(self, issue_number: str, body: str) -> None: ...


class GhCliClient:
    """Real :class:`GitHubClient` backed by the ``gh`` CLI (not used in tests)."""

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> str:
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args += ["--label", label]
        url = run_gh(args)
        return url.rstrip("/").rsplit("/", 1)[-1]  # trailing path segment = issue number

    def add_label(self, issue_number: str, label: str) -> None:
        run_gh(["issue", "edit", str(issue_number), "--add-label", label])

    def add_comment(self, issue_number: str, body: str) -> None:
        run_gh(["issue", "comment", str(issue_number), "--body", body])


@dataclass
class PushResult:
    pending: int
    pushed: int
    failed: int
    errors: List[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    pending: int
    applied: int
    skipped: int
    notes: List[str] = field(default_factory=list)


def push_outbox(store: StateStore, client: GitHubClient, *, dry_run: bool = False) -> PushResult:
    """Drain the outbox to GitHub. A message stays pending if its op fails."""
    pending = store.sync.pending_outbox()
    pushed = failed = 0
    errors: List[str] = []
    for msg in pending:
        if dry_run:
            continue
        try:
            _dispatch_outbox(store, client, msg)
            store.sync.mark_sent(msg.id)  # noqa: N+1 — one provider op per queued message
            pushed += 1
        except Exception as exc:  # noqa: BLE001 — per-message isolation; one failure must not abort the drain
            failed += 1
            errors.append(f"outbox#{msg.id} {msg.operation}: {exc}")
            _log.warning("outbox push failed",
                         extra={"outbox_id": msg.id, "operation": msg.operation, "error": str(exc)})
    return PushResult(pending=len(pending), pushed=pushed, failed=failed, errors=errors)


def _dispatch_outbox(store: StateStore, client: GitHubClient, msg) -> None:
    op, p = msg.operation, msg.payload
    if op == "create_issue":
        number = client.create_issue(p.get("title", ""), p.get("body", ""), p.get("labels", []) or [])
        object_uid = p.get("object_uid")
        if object_uid:
            store.external_refs.link(object_uid, GITHUB_PROVIDER, "issue", str(number),
                                     data={"source": "outbox-create"})
    elif op == "add_label":
        client.add_label(str(p["issue_number"]), p["label"])
    elif op == "comment":
        client.add_comment(str(p["issue_number"]), p.get("body", ""))
    else:
        raise ValueError(f"unknown outbox operation: {op!r}")


def apply_inbox(store: StateStore, *, dry_run: bool = False) -> ApplyResult:
    """Drain the inbox (GitHub → local), applying each event to local state."""
    pending = store.sync.pending_inbox()
    applied = skipped = 0
    notes: List[str] = []
    for msg in pending:
        kind = msg.payload.get("kind")
        try:
            handled = _apply_inbox_message(store, msg)
        except Exception as exc:  # noqa: BLE001 — per-message isolation
            skipped += 1
            notes.append(f"inbox#{msg.id} {kind}: {exc}")
            continue
        if handled:
            applied += 1
        else:
            skipped += 1
            notes.append(f"inbox#{msg.id}: {kind} not applicable (no local object?)")
        if not dry_run:
            store.sync.mark_processed(msg.id)  # noqa: N+1 — one event per queued message
    return ApplyResult(pending=len(pending), applied=applied, skipped=skipped, notes=notes)


def _apply_inbox_message(store: StateStore, msg) -> bool:
    """Return True if the message changed local state."""
    p = msg.payload
    kind = p.get("kind")
    if kind == "issue_state":
        ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", str(p["issue_number"]))
        if ref is None:
            return False
        store.objects.set_state(ref.object_uid, p.get("state"))
        return True
    if kind == "issue_imported":
        uid = p.get("slug") or f"github-issue-{p['issue_number']}"
        store.objects.upsert(uid, "work_item", state=p.get("state"),
                             data={"title": p.get("title")})
        store.external_refs.link(uid, GITHUB_PROVIDER, "issue", str(p["issue_number"]),
                                 data={"source": "inbox-import"})
        return True
    return False


# --------------------------------------------------------------------------- #
# CLI entry — routed from `atdd state sync` by the top-level cli.py.
# --------------------------------------------------------------------------- #
def run_sync_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="atdd state sync",
        description="Sync the State Store with GitHub via outbox/inbox (#1184).",
    )
    parser.add_argument("--root", default=None, help="Starting directory (default: cwd).")
    parser.add_argument("--push", action="store_true",
                        help="Actually push the outbox to GitHub (default: report only).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report pending work without mutating local or remote state.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    start = Path(args.root).resolve() if args.root else Path.cwd()
    resolution = resolve_control_root(start)
    db_path = init_state_store(start=resolution.control_root)

    conn = connect(db_path)
    try:
        store = StateStore(conn)
        applied = apply_inbox(store, dry_run=args.dry_run)
        print(f"inbox: {applied.applied} applied, {applied.skipped} skipped (of {applied.pending} pending)")
        for n in applied.notes:
            print(f"  - {n}")

        if args.push:
            pushed = push_outbox(store, GhCliClient(), dry_run=args.dry_run)
            print(f"outbox: {pushed.pushed} pushed, {pushed.failed} failed (of {pushed.pending} pending)")
            for e in pushed.errors:
                print(f"  - {e}")
            return 1 if pushed.failed else 0
        pending = len(store.sync.pending_outbox())
        print(f"outbox: {pending} pending (pass --push to send to GitHub)")
        return 0
    finally:
        conn.close()
