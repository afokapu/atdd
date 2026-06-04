"""CLI controller: run the autonomous Feed daemon (DG-1 entrypoint).

Thin shell (``atdd-feed-daemon``) — it parses args into a ``DaemonConfig``,
builds the daemon from the repo via the composition root, and runs the loop.
All wiring lives in ``composition.py``; this layer only parses args and starts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - thin shell
    parser = argparse.ArgumentParser(prog="atdd-feed-daemon")
    parser.add_argument("--workspace", required=True, help="cmux workspace id")
    parser.add_argument(
        "--interval", type=float, default=2.0, help="poll interval seconds"
    )
    parser.add_argument(
        "--lock",
        default=".atdd/runtime/feed-daemon.lock",
        help="single-instance pidfile path",
    )
    parser.add_argument(
        "--escalations",
        default=".atdd/runtime/feed-daemon/escalations.jsonl",
        help="durable human-escalation ledger",
    )
    parser.add_argument(
        "--verdicts",
        default=".atdd/runtime/feed-daemon/verdicts.jsonl",
        help="durable auto-applied-verdict ledger",
    )
    args = parser.parse_args(argv)

    from atdd.mediate_worker_decisions.feed_daemon.composition import (
        build_feed_daemon_from_repo,
    )
    from atdd.mediate_worker_decisions.feed_daemon.src.domain.daemon_config import (
        DaemonConfig,
    )

    config = DaemonConfig(
        workspace_id=args.workspace,
        lock_path=Path(args.lock),
        escalations_path=Path(args.escalations),
        verdicts_path=Path(args.verdicts),
        poll_interval_s=args.interval,
    )
    build_feed_daemon_from_repo(config=config).run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
