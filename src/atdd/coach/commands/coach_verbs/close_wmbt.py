"""``atdd coach close-wmbt <N> <ID> [--force]`` — auto-discovered drop-in (#1382, C5a).

DELEGATION-ONLY: the WMBT sub-issue close logic stays on
:meth:`atdd.coach.commands.issue_lifecycle.IssueLifecycle.close_wmbt` — this
module only parses the verb's argv and returns its exit code. The deprecated
``atdd issue <N> --close-wmbt <ID>`` shim (cli.py) warns on stderr and delegates
here.

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "close-wmbt"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach close-wmbt",
        description=(
            "Close a WMBT sub-issue of an ATDD parent issue (the coach-archetype "
            "replacement for `atdd issue <N> --close-wmbt <ID>`)."
        ),
    )
    parser.add_argument("number", type=str, nargs="?", metavar="N",
                        help="Parent issue number.")
    parser.add_argument("wmbt_id", type=str, nargs="?", metavar="ID",
                        help="WMBT id to close (e.g. D005, E003).")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Close even if ATDD cycle checkboxes are unchecked.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach close-wmbt <N> <ID> [--force]`` — parse argv and delegate."""
    ns = _build_parser().parse_args(argv)
    if not ns.number or not ns.wmbt_id:
        print("Error: atdd coach close-wmbt requires an issue number and a WMBT id")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        print(f"Error: invalid issue number '{ns.number}'")
        return 1
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    return IssueLifecycle().close_wmbt(issue_number, ns.wmbt_id, force=ns.force)
