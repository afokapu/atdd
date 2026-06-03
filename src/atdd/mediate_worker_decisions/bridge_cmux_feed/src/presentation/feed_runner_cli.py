"""CLI controller: poll the cmux Feed and drive each pending item.

Thin entry point — it builds the runner from the repo via the composition root
and runs one polling pass, printing one line of evidence per handled item. The
real wiring lives in ``composition.py``; this layer only parses args and prints.
"""
from __future__ import annotations

import argparse
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - thin shell
    parser = argparse.ArgumentParser(prog="atdd-feed-runner")
    parser.add_argument("--workspace", required=True, help="cmux workspace id")
    args = parser.parse_args(argv)

    from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import (
        build_feed_runner_from_repo,
    )

    runner = build_feed_runner_from_repo(workspace_id=args.workspace)
    for outcome in runner.run_once():
        if outcome.escalation is not None:
            print(f"escalated {outcome.request_id}: {outcome.escalation.cause}")
        else:
            print(f"replied {outcome.request_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
