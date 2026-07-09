"""``atdd coach issue-review <N> [--passes ...] [--llms ...] [--dimensions ...] [--show] [--force]``
— auto-discovered drop-in (#1382, C5a of umbrella #1303).

DELEGATION-ONLY: the multi-pass LLM issue-review engine (#508) is NOT
reimplemented — it stays on :func:`atdd.coach.commands.issue_review.run` and is
imported and called. This module only parses the verb's argv and delegates.

TOKEN CHOICE — ``issue-review``, NOT ``review``: ``atdd coach review`` already
belongs to the coach disposition / merge-readiness command
(:func:`atdd.coach.commands.coach_review.run_review`), which ``coach.run_cli``
resolves BEFORE the coach_verbs auto-discovery path. The #508 LLM issue-review
therefore lands under its own non-colliding ``issue-review`` token. The deprecated
``atdd issue review <N>`` shim (cli.py) warns on stderr and delegates here.

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse

VERB = "issue-review"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach issue-review",
        description=(
            "Run the multi-pass LLM review of an ATDD issue (the coach-archetype "
            "replacement for `atdd issue review`, #508)."
        ),
    )
    # Kept as a string (not type=int) so an invalid number reports the same
    # friendly error + exit code as the historical `atdd issue review` dispatch,
    # rather than argparse's SystemExit(2).
    parser.add_argument("number", type=str, nargs="?", metavar="N",
                        help="Issue number to review.")
    parser.add_argument("--passes", type=int, default=None,
                        help="Number of independent LLM passes (default from coach config; min 2).")
    parser.add_argument("--llms", type=str, default=None,
                        help="Comma-separated LLM client ids (default from coach config).")
    parser.add_argument("--dimensions", type=str, default=None,
                        help="Comma-separated dimensions to evaluate (default: all).")
    parser.add_argument("--show", action="store_true",
                        help="Show the stored aggregate without re-running.")
    parser.add_argument("--force", action="store_true",
                        help="Re-run passes even if cached results exist.")
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach issue-review <N> [...]`` — parse argv and delegate verbatim.

    Delegates to :func:`atdd.coach.commands.issue_review.run` with the same
    keyword arguments the old ``atdd issue review`` dispatch passed. Imports are
    lazy (at call time) so the coach_verbs package stays a pure registration
    surface and callers/tests that patch ``issue_review.run`` are honoured.
    """
    ns = _build_parser().parse_args(argv)

    if not ns.number:
        print("Error: atdd coach issue-review requires an issue number")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        print(f"Error: invalid issue number '{ns.number}'")
        return 1

    # Side-effect import: registers the production LLM clients (mirrors the old
    # `atdd issue review` dispatch in cli.py). Lazy so the fast coach path is free.
    import atdd.coach.commands.llm_clients  # noqa: F401
    from atdd.coach.commands import issue_review

    return issue_review.run(
        issue_number=issue_number,
        passes=ns.passes,
        llms=[s.strip() for s in ns.llms.split(",") if s.strip()] if ns.llms else None,
        dimensions=[s.strip() for s in ns.dimensions.split(",") if s.strip()] if ns.dimensions else None,
        show=ns.show,
        force=ns.force,
    )
