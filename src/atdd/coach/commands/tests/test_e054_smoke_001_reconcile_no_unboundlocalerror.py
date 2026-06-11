# URN: test:govern-lifecycle:fix-issue-reconcile-unbound-local-shadowed-import:E054-SMOKE-001-issue-reconcile-runs-without-unboundlocalerror
# Acceptance: acc:govern-lifecycle:E054-SMOKE-001-issue-reconcile-runs-without-unboundlocalerror
# WMBT: wmbt:govern-lifecycle:E054
# Phase: SMOKE
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E054-SMOKE-001 — the real CLI runs `atdd issue reconcile` without UnboundLocalError.

Against the real installed dispatch (no monkeypatching), ``python -m atdd issue
reconcile`` runs end-to-end as a subprocess. The crash this issue fixes fires at
``manager = IssueManager()`` (cli.py reconcile dispatch) — *before* reconcile()
touches the manifest or git — so it is provable in any working directory.

We run the subprocess in an isolated, throwaway ``tmp_path`` with no
``.atdd/manifest.yaml``. This deterministically drives the real dispatch all the
way to ``manager = IssueManager()`` and ``manager.reconcile()`` (proven by the
"manifest.yaml not found" guard message reconcile emits), while never mutating
the live repo — reconcile bails at the manifest-existence check before any
``gh``/``git`` side effect, so it cannot backfill or commit against the worktree
this test runs from.

RED: the dispatch crashes with
``UnboundLocalError: cannot access local variable 'IssueManager'`` before the
manifest check is ever reached.
GREEN: the local shadow is removed; reconcile dispatches cleanly and the run
reaches its own manifest-not-found guard.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.smoke]


def test_real_reconcile_subprocess_has_no_unboundlocalerror(tmp_path) -> None:
    # Isolated cwd with no .atdd/manifest.yaml: the real reconcile dispatch
    # still constructs IssueManager and calls reconcile(), then bails at the
    # manifest guard — no gh/git side effects against the live worktree.
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "issue", "reconcile"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")

    assert "UnboundLocalError" not in combined, (
        "`atdd issue reconcile` crashed with UnboundLocalError — the function-local "
        f"IssueManager shadow is still present.\n--- output ---\n{combined}"
    )
    assert "cannot access local variable 'IssueManager'" not in combined, (
        "`atdd issue reconcile` hit the unbound-local IssueManager crash.\n"
        f"--- output ---\n{combined}"
    )
    # Guard against a false green: prove the dispatch actually REACHED the
    # reconcile code path (constructing IssueManager + calling reconcile()),
    # rather than bailing earlier. reconcile() emits this when no manifest is
    # present in the isolated cwd — which is only reachable past line 2249.
    assert ".atdd/manifest.yaml not found" in combined, (
        "`atdd issue reconcile` did not reach the reconcile() manifest guard — "
        "the dispatch path constructing IssueManager may not have executed, so "
        f"this run does not exercise the fix.\n--- output ---\n{combined}"
    )
