"""``atdd coach sync-labels [<N>|--all] [--dry-run]`` — auto-discovered drop-in (#1308).

C4 (child of umbrella #1303 "retire ``atdd issue``, split author/coach"), the
sync-labels sibling of the C1 (#1304) ``atdd coach transition`` extraction.

DELEGATION-ONLY. Unlike C1 — which *moved* the transition orchestration into a
new engine — this verb re-implements NOTHING. The substantive label
re-derivation + GitHub delta logic stays on
:meth:`~atdd.coach.commands.issue.IssueManager.sync_labels` /
:meth:`~atdd.coach.commands.issue.IssueManager.sync_labels_all` (issue.py), and
the delta presentation stays on :func:`atdd.cli._print_sync_labels_delta`. This
module only parses its own argv and delegates — the thin coach-archetype CLI
surface required by the ``coach_verbs`` convention (see ``coach_verbs/__init__.py``).

The deprecated ``atdd issue sync-labels`` form in cli.py now warns on stderr and
delegates to :func:`run` here; C5 (#1309) removes the ``atdd issue`` barrier.

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
from __future__ import annotations

import argparse

VERB = "sync-labels"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach sync-labels",
        description=(
            "Re-derive an ATDD issue's labels from its body metadata and apply "
            "the delta (the coach-archetype replacement for "
            "`atdd issue sync-labels`)."
        ),
    )
    # Kept as a string (not type=int) so an invalid number reports the same
    # friendly error + exit code as the historical `atdd issue sync-labels`
    # dispatch, rather than argparse's SystemExit(2).
    parser.add_argument(
        "number",
        type=str,
        nargs="?",
        metavar="N",
        help="Issue number to sync (omit when using --all).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_issues",
        help="Re-derive labels across every atdd-issue (and atdd-wmbt) in the repo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Report the sync-labels delta without mutating GitHub.",
    )
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach sync-labels [<N>|--all] [--dry-run]`` — the canonical CLI entry.

    Delegates verbatim to the CURRENT logic: ``IssueManager.sync_labels`` /
    ``sync_labels_all`` (the unchanged re-derivation + delta) and
    ``cli._print_sync_labels_delta`` (the unchanged presentation). Nothing here
    re-implements sync-labels — the dispatch shape is the one moved out of
    ``atdd issue sync-labels``, byte-for-byte.
    """
    ns = _build_parser().parse_args(argv)

    # Imported at dispatch time (not module import) so the coach_verbs package
    # stays a pure registration surface and the fast `atdd coach <N>` path pays
    # no cost. `_print_sync_labels_delta` is imported — not copied — per the
    # delegation-only contract (#1308); it is the current presentation logic.
    from atdd.coach.commands.issue import IssueManager
    from atdd.cli import _print_sync_labels_delta

    manager = IssueManager()
    dry_run = ns.dry_run

    if ns.all_issues:
        results = manager.sync_labels_all(dry_run=dry_run)
        drifted = [
            (num, delta) for num, delta in results
            if delta["to_add"] or delta["to_remove"]
        ]
        for num, delta in drifted:
            _print_sync_labels_delta(num, delta, dry_run=dry_run)
        if not drifted:
            print(
                f"sync-labels: every atdd-issue already matches "
                f"body metadata ({len(results)} checked)"
            )
        else:
            suffix = " (dry-run)" if dry_run else ""
            print(
                f"sync-labels: {len(drifted)}/{len(results)} "
                f"issue(s) drifted{suffix}"
            )
        return 0

    if not ns.number:
        print("Error: atdd coach sync-labels requires an issue number or --all")
        return 1
    try:
        issue_number = int(ns.number)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        print(f"Error: invalid issue number '{ns.number}'")
        return 1

    delta = manager.sync_labels(issue_number, dry_run=dry_run)
    _print_sync_labels_delta(issue_number, delta, dry_run=dry_run)
    return 0
