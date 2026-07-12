"""``atdd coach reconcile`` — auto-discovered drop-in (#1305, child of #1303).

C2 of umbrella #1303 ("retire ``atdd issue``, split author/coach"). This is a
**delegation-only** extraction: the backfill-from-GitHub reconcile engine already
lives on :meth:`IssueManager.reconcile` (``issue.py``) — the self-heal that
synthesises every open ``atdd-issue`` missing from the manifest/store, WITH the
merged E054 module-resolution fixes. This verb does NOT reimplement any of that;
it parses its own (empty) argv and calls that engine.

Follows the coach-verb registration convention documented in
``coach_verbs/__init__.py`` (the #1304 LEAD pattern): one drop-in file declaring
``VERB`` + ``run(argv)``, touching nothing shared, so the parallel children C3/C4
(#1307/#1308) never merge-conflict on wiring. The deprecated ``atdd issue
reconcile`` shim (``cli.py``) warns on stderr and delegates here.
"""
from __future__ import annotations

import argparse

VERB = "reconcile"


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="atdd coach reconcile",
        description=(
            "Backfill every open GitHub atdd-issue missing from the manifest/"
            "State Store (the coach-archetype replacement for `atdd issue "
            "reconcile`). Idempotent — re-running on a complete manifest is a "
            "no-op."
        ),
    )


def run(argv: list[str]) -> int:
    """``atdd coach reconcile`` — parse argv (no positional args) and delegate.

    Delegation-only: constructs :class:`IssueManager` and returns its existing
    ``reconcile()`` exit code unchanged. The import is deliberately lazy (at call
    time, not module import) so the drop-in stays cheap to import on the fast
    ``atdd coach <N>`` dispatch path, and so callers/tests that patch
    ``atdd.coach.commands.issue.IssueManager`` are honoured.
    """
    _build_parser().parse_args(argv)  # reject stray args; handle -h/--help
    from atdd.coach.commands.issue import IssueManager

    return IssueManager().reconcile()
