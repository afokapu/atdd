"""``atdd coach check <N>`` — auto-discovered drop-in (#1382, C5a).

DELEGATION-ONLY: the ATDD-cycle checkbox / body-compliance check stays on
:meth:`atdd.coach.commands.issue_lifecycle.IssueLifecycle.check` — this module
only parses the verb's argv and returns its exit code. The deprecated
``atdd issue <N> --check`` shim (cli.py) warns on stderr and delegates here.

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "check"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach check",
        description=(
            "Check an ATDD issue's cycle checkboxes / body compliance (the "
            "coach-archetype replacement for `atdd issue <N> --check`)."
        ),
    )
    parser.add_argument("number", type=str, nargs="?", metavar="N",
                        help="Issue number to check.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach check <N>`` — parse argv and delegate to IssueLifecycle.check."""
    ns = _build_parser().parse_args(argv)
    if not ns.number:
        print("Error: atdd coach check requires an issue number")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        print(f"Error: invalid issue number '{ns.number}'")
        return 1
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    return IssueLifecycle().check(issue_number)
