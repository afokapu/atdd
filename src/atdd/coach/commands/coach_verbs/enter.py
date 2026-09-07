"""``atdd coach enter <N>`` — auto-discovered drop-in (#1382, C5a).

DELEGATION-ONLY: the state-driven show/enter logic stays on
:meth:`atdd.coach.commands.issue_lifecycle.IssueLifecycle.enter` — this module
only parses the verb's argv and returns its exit code.

This is the dedicated coach home for the bare ``atdd issue <N>`` enter. The
#1307 ``atdd coach issues <N>`` read verb already reaches the SAME
``IssueLifecycle.enter`` engine; this verb is the first-class, single-purpose
alias so C5b (#1309) can delete the ``atdd issue`` monolith with every enter path
already living under ``atdd coach``. (The bare ``atdd issue <N>`` shim, unchanged
since #1307, keeps delegating through ``issue_read.run`` to that same engine.)

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "enter"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach enter",
        description=(
            "Show/enter an existing ATDD issue by number (the coach-archetype "
            "replacement for the bare `atdd issue <N>` enter)."
        ),
    )
    parser.add_argument("number", type=str, nargs="?", metavar="N",
                        help="Issue number to show/enter.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach enter <N>`` — parse argv and delegate to IssueLifecycle.enter."""
    ns = _build_parser().parse_args(argv)
    if not ns.number:
        print("Error: atdd coach enter requires an issue number")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        print(f"Error: invalid issue number '{ns.number}'")
        return 1
    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    return IssueLifecycle().enter(issue_number)
