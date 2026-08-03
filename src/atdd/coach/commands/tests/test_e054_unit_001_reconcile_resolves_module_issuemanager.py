# URN: test:govern-lifecycle:fix-issue-reconcile-unbound-local-shadowed-import:E054-UNIT-001-issuemanager-resolves-to-module-import-on-reconcile-path
# Acceptance: acc:govern-lifecycle:E054-UNIT-001-issuemanager-resolves-to-module-import-on-reconcile-path
# WMBT: wmbt:govern-lifecycle:E054
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E054-UNIT-001 — the reconcile dispatch path resolves IssueManager to the module import.

Behavioral contract: invoking ``atdd issue reconcile`` reaches
``IssueManager.reconcile()`` without raising ``UnboundLocalError`` and returns the
exit code that reconcile() produced. We prove this with a recording fake patched
onto the canonical source name ``atdd.coach.commands.issue.IssueManager`` — not by
reading source text.

The original E054 fix removed two function-local ``import IssueManager`` statements
inside ``main()`` that made the name local for the whole function, so on the
reconcile path ``manager = IssueManager()`` read an unbound local and raised
``UnboundLocalError`` before reconcile() was ever reached (the structural guard for
that fix lives in E054-UNIT-002).

Since #1305, ``atdd issue reconcile`` is a deprecated shim that delegates to the
``atdd coach reconcile`` drop-in, whose ``run()`` lazy-imports
``atdd.coach.commands.issue.IssueManager`` and calls ``reconcile()``. Patching that
canonical source proves the dispatch still reaches ``IssueManager.reconcile()``
exactly once through the delegation and returns its sentinel — with no
``UnboundLocalError``.
"""
from __future__ import annotations

import pytest

import atdd.cli as cli

pytestmark = [pytest.mark.platform]

_SENTINEL_EXIT = 0


def test_reconcile_path_reaches_issuemanager_reconcile_without_unbound_local(
    monkeypatch,
) -> None:
    calls = {"count": 0}

    class _RecordingIssueManager:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def reconcile(self, *args, **kwargs) -> int:
            calls["count"] += 1
            return _SENTINEL_EXIT

    # Patch IssueManager at its source module. Since #1305, `atdd issue reconcile`
    # is a deprecated shim that delegates to the `atdd coach reconcile` drop-in,
    # whose run() lazy-imports `atdd.coach.commands.issue.IssueManager` and calls
    # reconcile(). Patching the canonical source (not the cli.py alias) proves the
    # dispatch still reaches IssueManager.reconcile() exactly once through the
    # delegation, with no UnboundLocalError.
    monkeypatch.setattr("atdd.coach.commands.issue.IssueManager", _RecordingIssueManager)
    monkeypatch.setattr(cli.sys, "argv", ["atdd", "coach", "reconcile"])

    try:
        result = cli.main()
    except UnboundLocalError as exc:  # pragma: no cover - RED failure path
        pytest.fail(
            "reconcile dispatch raised UnboundLocalError — IssueManager is still "
            f"shadowed by a function-local import in main(): {exc}"
        )

    assert calls["count"] == 1, (
        "IssueManager.reconcile() was not reached exactly once on the reconcile path"
    )
    assert result == _SENTINEL_EXIT, (
        "main() did not return the exit code produced by reconcile()"
    )
