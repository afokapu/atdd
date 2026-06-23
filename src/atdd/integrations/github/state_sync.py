"""GitHub sync provider for the State Store (#1184, refactored by #1201).

GitHub is **one provider** behind the core provider-agnostic sync engine
(:mod:`atdd.state.sync_engine`). This module holds only the GitHub-specific
*remote* operations — `GhCliClient` (shells to ``gh``) and `GitHubSyncProvider`
(maps outbox operations onto it and returns the external ref to record). The
drain/apply/record machinery lives in core and has no GitHub knowledge.

Layer direction: ``atdd.integrations.github`` imports ``atdd.state``; never the
reverse (enforced by the layer-imports gate).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from atdd.integrations.github._gh import run_gh
from atdd.state.db import connect, init_state_store
from atdd.state.paths import resolve_control_root
from atdd.state.store import StateStore
from atdd.state.sync_engine import PushOutcome, apply_inbox, push_outbox

_log = logging.getLogger(__name__)

PROVIDER_NAME = "github"


class GitHubClient:
    """Minimal GitHub operations (real ``gh``-backed; subbed by a fake in tests)."""

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> str:
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args += ["--label", label]
        url = run_gh(args)
        return url.rstrip("/").rsplit("/", 1)[-1]

    def add_label(self, issue_number: str, label: str) -> None:
        run_gh(["issue", "edit", str(issue_number), "--add-label", label])

    def add_comment(self, issue_number: str, body: str) -> None:
        run_gh(["issue", "comment", str(issue_number), "--body", body])


# The real ``gh``-backed client (alias kept for callers/tests).
GhCliClient = GitHubClient


class GitHubSyncProvider:
    """A :class:`atdd.state.sync_engine.SyncProvider` for GitHub."""

    name = PROVIDER_NAME

    def __init__(self, client: Optional[GitHubClient] = None) -> None:
        self._client = client or GhCliClient()

    def push(self, operation: str, payload: Dict[str, Any]) -> Optional[PushOutcome]:
        if operation == "create_issue":
            number = self._client.create_issue(
                payload.get("title", ""), payload.get("body", ""), payload.get("labels", []) or [])
            return PushOutcome(object_uid=payload.get("object_uid"), ref_kind="issue",
                               ref_value=str(number), ref_data={"source": "outbox-create"})
        if operation == "add_label":
            self._client.add_label(str(payload.get("issue_number") or payload["ref_value"]),
                                   payload["label"])
            return None
        if operation == "comment":
            self._client.add_comment(str(payload.get("issue_number") or payload["ref_value"]),
                                     payload.get("body", ""))
            return None
        raise ValueError(f"unknown github outbox operation: {operation!r}")


# --------------------------------------------------------------------------- #
# CLI — routed from `atdd state sync` by the top-level cli.py. Builds the GitHub
# provider and calls the CORE engine (apply is provider-agnostic; push uses the
# provider registry).
# --------------------------------------------------------------------------- #
def run_sync_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="atdd state sync",
        description="Sync the State Store with providers via outbox/inbox (#1184/#1201).",
    )
    parser.add_argument("--root", default=None, help="Starting directory (default: cwd).")
    parser.add_argument("--push", action="store_true",
                        help="Push the outbox to providers (default: report only).")
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
            providers = {PROVIDER_NAME: GitHubSyncProvider()}
            pushed = push_outbox(store, providers, dry_run=args.dry_run)
            print(f"outbox: {pushed.pushed} pushed, {pushed.failed} failed, "
                  f"{pushed.skipped_no_provider} skipped-no-provider (of {pushed.pending} pending)")
            for e in pushed.errors:
                print(f"  - {e}")
            return 1 if pushed.failed else 0
        pending = len(store.sync.pending_outbox())
        print(f"outbox: {pending} pending (pass --push to send via registered providers)")
        return 0
    finally:
        conn.close()
