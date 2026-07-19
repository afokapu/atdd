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
from typing import Optional

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


def _reject(ns) -> Optional[str]:
    """The argv combinations the verb declines, or None when the invocation is sane.

    Kept separate from :func:`run` so the safety posture reads as a list rather
    than as branches interleaved with the work.
    """
    if ns.all_issues and ns.number:
        return "pass an issue number OR --all, not both."
    if not ns.all_issues and not ns.number:
        return "atdd coach reconcile-state requires an issue number or --all"
    if ns.all_issues and ns.apply:
        return (
            "--all is report-only. Repairing 236 drifted records in one run is "
            "an operator-gated data migration, not a verb invocation (#1338 "
            "Decision 4). Review the report, then --apply per issue."
        )
    if ns.number and not ns.number.lstrip("-").isdigit():
        return f"invalid issue number '{ns.number}'"
    return None


def run(argv: list) -> int:
    """``atdd coach reconcile-state [<N>|--all] [--apply] [--allow-legacy-undriven]``."""
    ns = _build_parser().parse_args(argv)

    rejection = _reject(ns)
    if rejection is not None:
        print(f"Error: {rejection}")
        return 1

    # Imported at dispatch time so the coach_verbs package stays a pure
    # registration surface and the fast `atdd coach <N>` path pays no cost.
    from atdd.coach.commands.issue_reconcile_state import apply_repair, build_report

    numbers = [int(ns.number)] if ns.number else None
    report = build_report(numbers)
    if report is None:
        return 1

    # Always render the plan first, as a plan. Under --apply it is what is about
    # to be attempted, not what happened — a repair that then refuses must not
    # have been announced as applied.
    print(report.render(dry_run=True))
    if not ns.apply:
        return 0

    if not report.repairs:
        print(f"reconcile-state: #{numbers[0]} is not an atdd-issue on GitHub.")
        return 1

    print("")
    return apply_repair(
        report.repairs[0],
        allow_legacy_undriven=ns.allow_legacy_undriven,
    )
