"""``atdd coach is-registered <branch>`` — auto-discovered drop-in (#1382, C5a).

DELEGATION-ONLY: the store-backed branch-registration gate (#1270 slice C) stays
on :meth:`atdd.coach.commands.issue.IssueManager.branch_is_registered` — this
module only parses the verb's argv and returns its exit code.

Exit codes (identical to the old ``atdd issue is-registered``):
    0 — branch registered, or nothing to check (repo not atdd-managed)
    1 — repo IS atdd-managed but the branch's slug is absent from store + manifest
    2 — usage error (no branch given)

This is the verb the pre-commit hook invokes (``atdd coach is-registered
"$BRANCH"``), so C5b's deletion of the ``atdd issue`` monolith cannot break the
commit gate. The deprecated ``atdd issue is-registered`` shim (cli.py) warns on
stderr and delegates here.

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "is-registered"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach is-registered",
        description=(
            "Store-backed branch-registration check (exit 0 registered / 1 "
            "unregistered / 2 usage) — the coach-archetype replacement for "
            "`atdd issue is-registered`."
        ),
    )
    parser.add_argument("branch", type=str, nargs="?",
                        help="Branch name to check for work-item registration.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach is-registered <branch>`` — parse argv and delegate.

    Lazy import so the coach_verbs package stays a pure registration surface and
    callers/tests that patch ``IssueManager.branch_is_registered`` are honoured.
    """
    ns = _build_parser().parse_args(argv)
    if not ns.branch:
        print("Error: atdd coach is-registered requires a branch name")
        return 2
    from atdd.coach.commands.issue import IssueManager

    return 0 if IssueManager().branch_is_registered(ns.branch) else 1
