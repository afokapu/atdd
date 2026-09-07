"""``atdd coach backfill-bindings`` — auto-discovered drop-in (#1689).

DELEGATION-ONLY: the backfill engine already shipped with #1635 as
:func:`atdd.coach.commands.issue_feature_binding.backfill_feature_bindings`.
It was tested and referenced by ``coach.issue.feature-binding-must-resolve``'s
fix_hint, but wired to no CLI — so the only way to run the repair the rule told
operators to run was to import the module by hand. This verb is that wiring and
nothing more; it adds no derivation logic of its own.

Why a drop-in rather than a shared dispatch edit: the coach-verb registration
convention (``coach_verbs/__init__.py``, the #1304 LEAD pattern) exists so
parallel children never collide on wiring. #1661 is in flight against
``author.py`` / ``author_publish.py`` — the ``--revise`` write path — so this
change deliberately touches neither.

Safe to run ahead of #1661: the backfill calls ``revise_work_item_issue``
directly and never goes through the ``--revise`` CLI, so the flag-plumbing
defect #1661 fixes cannot reach it.
"""
from __future__ import annotations

import argparse

VERB = "backfill-bindings"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach backfill-bindings",
        description=(
            "Populate work_item.data.feature from the issue body's Feature row, "
            "for issue-backed work items whose binding does not resolve against "
            "plan/. Derives ONLY from a body Feature row that resolves; anything "
            "else is reported and left alone rather than guessed at. Never "
            "overwrites a binding that already resolves, so re-running writes "
            "nothing."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be written without writing it.",
    )
    parser.add_argument(
        "--show-unresolved", action="store_true",
        help="List the issue numbers left alone, not just the counts.",
    )
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach backfill-bindings`` — parse argv and delegate to the engine.

    The import is lazy (at call time) so this drop-in stays cheap to import on
    the fast ``atdd coach <N>`` dispatch path, matching the sibling verbs.
    """
    ns = _build_parser().parse_args(argv)

    from atdd.coach.commands.issue_feature_binding import backfill_feature_bindings

    report = backfill_feature_bindings(dry_run=ns.dry_run)

    verb = "would write" if ns.dry_run else "wrote"
    print(f"atdd coach backfill-bindings: {verb} {len(report.written)} binding(s)")
    print(
        f"  left NULL (no resolvable Feature row): {len(report.unresolved)} "
        "— these declare no feature, or name one plan/ does not contain"
    )
    # Always printed, including as a zero: this count used to be invisible, and
    # an operator who cannot see it cannot know the store holds bindings that
    # resolve to nothing (#1689). Read as a plain attribute, not via a
    # defaulting getattr — a getattr default would print 0 forever if the field
    # were ever renamed, which is the silent-success failure this issue is about.
    unrepairable = report.unrepairable
    print(
        f"  broken binding, body offers no better: {len(unrepairable)} "
        "— a stored value that does not resolve in plan/ (e.g. 'TBD'); needs "
        "authoring, not backfilling"
    )

    if ns.show_unresolved:
        for number in report.unresolved:
            print(f"    #{number} (no binding)")
        for number in unrepairable:
            print(f"    #{number} (broken binding)")

    if report.written and not ns.dry_run:
        print(
            "  verify: atdd coach issues <N> now resolves WMBTs for a backfilled issue"
        )

    return 0
