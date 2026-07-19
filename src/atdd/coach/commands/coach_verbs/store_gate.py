"""``atdd coach store-gate`` — run the Store-as-source-of-truth check on demand (#1503).

DELEGATION-ONLY: the gate lives in :mod:`atdd.coach.store_mirror_gate`, which the
``pre-push`` hook dispatches to directly. This module only parses argv and
renders, so the hook and the CLI cannot report the same Store differently.

WHY A CLI SURFACE AT ALL
    Without it the *only* way to run this gate is to attempt a push and be
    refused — you cannot ask "would this push be blocked, and why?" before
    provoking it. That also makes the gate un-runnable in any context that has
    no git remote (CI diagnostics, a fresh clone, an operator triaging drift).

Exit codes match the hook, so the two are interchangeable in a script:
    0 — allowed (advisories may still print)
    1 — blocked
    2 — usage error

Convention: src/atdd/coach/commands/coach_verbs/__init__.py (the #1304 pattern).
"""
from __future__ import annotations

import argparse
import sys

VERB = "store-gate"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach store-gate",
        description=(
            "Check that the Store — not GitHub — is the source of truth for the "
            "work_item bound to a branch, and report repo-wide drift."
        ),
    )
    parser.add_argument(
        "--branch", type=str, default=None,
        help="Branch to check (default: the current branch).",
    )
    parser.add_argument(
        "--no-provider", action="store_true",
        help="Skip the GitHub label-divergence check (offline / no gh).",
    )
    return parser


def run(argv: list[str]) -> int:
    """``atdd coach store-gate [--branch B] [--no-provider]`` — parse and delegate.

    Lazy imports so this package stays a pure registration surface.
    """
    ns = _build_parser().parse_args(argv)

    from atdd.coach.store_mirror_gate import (
        EXIT_ALLOW,
        _current_branch,
        evaluate,
        render,
    )
    from atdd.state.db import connect, init_state_store

    branch = ns.branch or _current_branch()
    if not branch or branch == "HEAD":
        print("Error: no branch to check (detached HEAD); pass --branch")
        return 2

    conn = connect(init_state_store())
    result = evaluate(conn, branch, check_provider=not ns.no_provider)

    for line in render(result):
        print(line, file=sys.stderr)
    if not result.blocked:
        print(f"store-mirror gate: OK for branch {branch!r}")
    return EXIT_ALLOW if not result.blocked else result.exit_code
