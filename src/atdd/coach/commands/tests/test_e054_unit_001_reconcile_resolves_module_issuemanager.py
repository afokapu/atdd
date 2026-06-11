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
onto the module-level name ``atdd.cli.IssueManager`` — not by reading source text.

RED now: two function-local ``import IssueManager`` statements inside ``main()``
make the name local for the whole function, so on the reconcile path (where
neither local-import branch has run) ``manager = IssueManager()`` reads an unbound
local and raises ``UnboundLocalError`` before reconcile() is ever reached. The
patch on the module global has no effect while the local shadow exists, so the
recording fake is never called and this test fails.

GREEN: removing the two local imports makes ``IssueManager`` resolve to the module
global on every path; the patch takes effect, reconcile() is reached exactly once,
and main() returns the sentinel.
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

    # Patch the module-level name. Only resolves on the reconcile path once the
    # function-local shadow is removed (the fix).
    monkeypatch.setattr(cli, "IssueManager", _RecordingIssueManager)
    monkeypatch.setattr(cli.sys, "argv", ["atdd", "issue", "reconcile"])

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
