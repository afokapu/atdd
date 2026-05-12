"""`atdd coach watch` — rate-limit-aware batched PR status watcher.

Public surface:
  ``run_watch(argv)`` — entry point called by coach.run_cli.
  ``_build_watch_parser()`` — argparse surface.

CLI examples::

    atdd coach watch                  # status of all open PRs (1 API call)
    atdd coach watch 101 102          # specific PRs
    atdd coach watch --wait CLEAN     # block until any PR is CLEAN
    atdd coach watch --failures 101   # diagnostics for one PR (expensive)
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from atdd.coach.runtime.pr_watcher import PRWatcher, failures as pr_failures


def _build_watch_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd coach watch",
        description=(
            "Batched PR status watcher. Uses a single gh pr list call per cycle "
            "to avoid GitHub secondary rate-limit hits."
        ),
    )
    p.add_argument(
        "prs",
        nargs="*",
        type=int,
        metavar="N",
        help="PR numbers to watch (default: all open PRs).",
    )
    p.add_argument(
        "--wait",
        default=None,
        metavar="STATE",
        help="Block until any watched PR reaches STATE (e.g. CLEAN).",
    )
    p.add_argument(
        "--failures",
        type=int,
        default=None,
        metavar="N",
        dest="failures_pr",
        help="Fetch statusCheckRollup diagnostics for PR N (expensive — use sparingly).",
    )
    p.add_argument(
        "--repo",
        default="afokapu/atdd",
        help="GitHub repo (owner/repo). Default: afokapu/atdd.",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=180,
        metavar="SECONDS",
        help="Poll interval in seconds (default 180, min 60).",
    )
    return p


def run_watch(argv: list[str]) -> int:
    """Entry point for `atdd coach watch`."""
    parser = _build_watch_parser()
    args = parser.parse_args(argv)
    interval = max(60, args.interval)

    if args.failures_pr is not None:
        failed = pr_failures(pr=args.failures_pr, repo=args.repo)
        if failed:
            for name in failed:
                print(f"FAILURE: {name}")
        else:
            print(f"#{args.failures_pr}: no failing checks")
        return 0

    watcher = PRWatcher(repo=args.repo, poll_interval=interval)

    if args.wait:
        target = args.wait.upper()
        pr_number = watcher.wait_any(prs=args.prs or [], target_state=target)
        if pr_number is not None:
            print(f"{target}: #{pr_number}")
        return 0

    states = watcher.poll(prs=args.prs or [])
    if not states:
        print("(no open PRs or rate-limit budget exhausted)")
        return 0

    for pr_num, state in sorted(states.items()):
        print(f"#{pr_num} [{state}]")
    return 0
