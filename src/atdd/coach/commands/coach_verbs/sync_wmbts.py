"""``atdd coach sync-wmbts <N>`` — auto-discovered drop-in (#1382, C5a).

DELEGATION-ONLY: the WMBT sub-issue synchronisation logic stays on
:meth:`atdd.coach.commands.issue.IssueManager.sync_wmbts` — this module only
parses the verb's argv and maps the engine's return code to a process exit code
exactly as the old ``atdd issue <N> --sync-wmbts`` dispatch did (``rc >= 0`` → 0,
otherwise 1). The deprecated ``atdd issue <N> --sync-wmbts`` shim (cli.py) warns
on stderr and delegates here.

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "sync-wmbts"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach sync-wmbts",
        description=(
            "Synchronise an ATDD parent issue's WMBT sub-issues (the coach-"
            "archetype replacement for `atdd issue <N> --sync-wmbts`)."
        ),
    )
    parser.add_argument("number", type=str, nargs="?", metavar="N",
                        help="Parent issue number.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach sync-wmbts <N>`` — parse argv and delegate to sync_wmbts."""
    ns = _build_parser().parse_args(argv)
    if not ns.number:
        print("Error: atdd coach sync-wmbts requires an issue number")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        print(f"Error: invalid issue number '{ns.number}'")
        return 1
    from atdd.coach.commands.issue import IssueManager

    rc = IssueManager().sync_wmbts(issue_number)
    return 0 if rc >= 0 else 1
