"""``atdd coach reconcile-state`` — auto-discovered drop-in (#1338).

The lifecycle REPAIR verb, sibling of ``coach reconcile`` (which backfills
existence) and ``coach transition`` (which advances the lifecycle). This one
repairs a record whose ``atdd:<PHASE>`` label drifted away from the
``objects.state`` it is supposed to project.

DELEGATION-ONLY, per the ``coach_verbs`` convention: the classification, the
evidence gathering, the report and the apply path all live in the sibling
``issue_reconcile_state`` engine. This module parses its own argv and delegates.

SAFETY POSTURE — the defaults are deliberate, not cautious-by-accident:

- ``--all`` is **report-only, always**. ``--all --apply`` is refused. Bulk
  repair of the 236 drifted records is an operator-gated data migration, not
  something a verb does because it was asked nicely once (#1338 Decision 4).
- A single issue is **report-only until ``--apply``** is passed.
- Class 4 (legacy-undriven) **refuses**, and its operator flag only authorises
  re-projecting the label down to the honest floor — never a replay.
"""
from __future__ import annotations

import argparse

VERB = "reconcile-state"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach reconcile-state",
        description=(
            "Reconcile an ATDD issue's atdd:<PHASE> label with the objects.state "
            "it projects. The store is the survivor; the label is re-derived from "
            "it. Reports by default — mutating requires --apply on a single issue."
        ),
    )
    parser.add_argument(
        "number",
        type=str,
        nargs="?",
        metavar="N",
        help="Issue number to reconcile (omit when using --all).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_issues",
        help="Classify every atdd-issue. Report-only: --apply is refused with --all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Report without writing (the default; accepted for explicitness).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Actually perform the repair. Single issue only.",
    )
    parser.add_argument(
        "--allow-legacy-undriven",
        action="store_true",
        dest="allow_legacy_undriven",
        help=(
            "Operator decision for a class-4 (legacy-undriven) record. Authorises "
            "re-projecting its label DOWN to the honest store floor. It does NOT "
            "authorise replaying a history the record never had — no flag does."
        ),
    )
    return parser


def run(argv: list) -> int:
    """``atdd coach reconcile-state [<N>|--all] [--apply] [--allow-legacy-undriven]``."""
    ns = _build_parser().parse_args(argv)

    # Imported at dispatch time so the coach_verbs package stays a pure
    # registration surface and the fast `atdd coach <N>` path pays no cost.
    from atdd.coach.commands.issue_reconcile_state import apply_repair, build_report

    if ns.all_issues and ns.number:
        print("Error: pass an issue number OR --all, not both.")
        return 1
    if not ns.all_issues and not ns.number:
        print("Error: atdd coach reconcile-state requires an issue number or --all")
        return 1

    if ns.all_issues and ns.apply:
        print(
            "Error: --all is report-only. Repairing 236 drifted records in one "
            "run is an operator-gated data migration, not a verb invocation "
            "(#1338 Decision 4). Review the report, then --apply per issue."
        )
        return 1

    numbers = None
    if ns.number:
        try:
            numbers = [int(ns.number)]
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-30
            print(f"Error: invalid issue number '{ns.number}'")
            return 1

    report = build_report(numbers)
    if report is None:
        return 1

    if not ns.apply:
        print(report.render(dry_run=True))
        return 0

    if not report.repairs:
        print(f"reconcile-state: #{numbers[0]} is not an atdd-issue on GitHub.")
        return 1

    print(report.render(dry_run=True))
    print("")
    return apply_repair(
        report.repairs[0],
        allow_legacy_undriven=ns.allow_legacy_undriven,
    )
