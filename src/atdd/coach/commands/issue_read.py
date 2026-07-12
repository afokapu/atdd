"""`atdd coach issues` — the coach-archetype READ verb (list + show/enter).

C3 (#1307, child of umbrella #1303 "retire ``atdd issue``, split author/coach").
DELEGATION-ONLY: the list and show/enter logic is NOT reimplemented here — it
stays on :meth:`~atdd.coach.commands.issue.IssueManager.open_issues` (list) and
:meth:`~atdd.coach.commands.issue_lifecycle.IssueLifecycle.enter` (show/enter)
and is imported and called. This module only parses the verb's argv (everything
AFTER the verb) and dispatches to the right existing entry point, so C5 (#1309)
can later drop the ``atdd issue`` monolith without a second implementation to
reconcile.

Two forms, mirroring the old ``atdd issue`` read paths identically:

- ``atdd coach issues [open] [--label L] [--limit N] [--assignee A]``
      → ``IssueManager.open_issues(label, limit, assignee)``  (list open issues)
- ``atdd coach issues <N>``
      → ``IssueLifecycle.enter(N)``  (state-driven show/enter)

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach issues",
        description=(
            "List open issues, or show/enter an existing one (the coach-"
            "archetype replacement for `atdd issue open` / `atdd issue <N>`)."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Issue number to show/enter; omit (or 'open') to list open issues.",
    )
    parser.add_argument(
        "--label", "-l", type=str, help="Filter by label (list mode)."
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=30,
        help="Maximum issues to list (list mode, default: 30).",
    )
    parser.add_argument(
        "--assignee", type=str, help="Filter by assignee (list mode)."
    )
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach issues [open|<N>] [...]`` — the read-verb CLI entry.

    Parses everything AFTER the verb and DELEGATES to the existing read logic:
    a bare invocation or the literal ``open`` lists via
    ``IssueManager.open_issues``; an integer target shows/enters via
    ``IssueLifecycle.enter``. No read logic is reimplemented here — this keeps
    behavior identical to the old ``atdd issue open`` / ``atdd issue <N>`` paths.
    """
    parser = _build_parser()
    ns = parser.parse_args(argv)

    # List mode: bare `atdd coach issues` or the explicit `open` token.
    if ns.target is None or ns.target == "open":
        from atdd.coach.commands.issue import IssueManager

        return IssueManager().open_issues(
            label=ns.label,
            limit=ns.limit,
            assignee=ns.assignee,
        )

    # Show/enter mode: an integer issue number.
    try:
        issue_number = int(ns.target)
    except ValueError:
        parser.error(
            f"invalid issue target {ns.target!r}: expected an issue number or 'open'"
        )  # raises SystemExit(2)

    from atdd.coach.commands.issue_lifecycle import IssueLifecycle

    return IssueLifecycle().enter(issue_number)
