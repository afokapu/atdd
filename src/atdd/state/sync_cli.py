"""Provider-agnostic ``atdd state sync`` CLI (#1364, ext#40 Phase 2 core seam).

This is the CORE sync entry point. It contains **no provider knowledge** — it
resolves the store, asks :mod:`atdd.state.providers` for the registered providers,
and drives the provider-agnostic engine:

- ``--ingest`` — ask each registered provider to fill the inbox from its remote
  (a no-op if no provider implements ``ingest``);
- always ``apply_inbox`` — drain the inbox onto local state (fully generic);
- ``--push`` — drain the outbox to registered providers.

With zero providers installed, sync is pure-local: ``--ingest`` does nothing, the
inbox drains, and ``--push`` leaves the outbox pending. Provider-specific syncing
(e.g. the GitHub ingester) lives in an extension and plugs in via the registry —
core never imports it.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from atdd.state.db import connect, init_state_store
from atdd.state.paths import resolve_control_root
from atdd.state.providers import discover_providers
from atdd.state.store import StateStore
from atdd.state.sync_engine import apply_inbox, ingest_inbox, push_outbox


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd state sync",
        description=(
            "Sync the State Store with registered providers "
            "(provider-agnostic; #1364 / ext#40 Phase 2)."
        ),
    )
    parser.add_argument("--root", default=None, help="Starting directory (default: cwd).")
    parser.add_argument(
        "--ingest", action="store_true",
        help="Ask registered providers to fill the inbox from their "
             "remote before draining (no-op with no provider).",
    )
    parser.add_argument(
        "--push", action="store_true",
        help="Push the outbox to registered providers (default: report only).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report pending work without mutating local or remote state.",
    )
    return parser


def run_sync_cli(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    start = Path(args.root).resolve() if args.root else Path.cwd()
    resolution = resolve_control_root(start)
    db_path = init_state_store(start=resolution.control_root)

    conn = connect(db_path)
    try:
        store = StateStore(conn)
        providers = discover_providers()

        if args.ingest and not args.dry_run:
            ing = ingest_inbox(store, providers)
            print(f"ingest: {ing.ingested} provider(s) ran, "
                  f"{ing.skipped_no_ingest} skipped-no-ingest (of {ing.providers})")
            for e in ing.errors:
                print(f"  - {e}")

        applied = apply_inbox(store, dry_run=args.dry_run)
        print(f"inbox: {applied.applied} applied, {applied.skipped} skipped "
              f"(of {applied.pending} pending)")
        for n in applied.notes:
            print(f"  - {n}")

        if args.push:
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
