# URN: test:govern-lifecycle:fix-issue-reconcile-unbound-local-shadowed-import:E054-SMOKE-001-issue-reconcile-runs-without-unboundlocalerror
# Acceptance: acc:govern-lifecycle:E054-SMOKE-001-issue-reconcile-runs-without-unboundlocalerror
# WMBT: wmbt:govern-lifecycle:E054
# Phase: SMOKE
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E054-SMOKE-001 — the real CLI runs `atdd issue reconcile` without UnboundLocalError.

Against the real installed dispatch (no monkeypatching), ``python -m atdd issue
reconcile`` runs end-to-end as a subprocess. It may exit non-zero for unrelated
reasons (e.g. no gh auth, no open issues), but the combined stdout/stderr must
NEVER name ``UnboundLocalError`` or the unbound-``IssueManager`` message — those
indicate the function-local shadow is still present.

RED now: the live reconcile path crashes with
``UnboundLocalError: cannot access local variable 'IssueManager'``.
GREEN: the local shadow is removed; reconcile dispatches cleanly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

REPO_ROOT = Path(__file__).resolve().parents[5]


def test_real_reconcile_subprocess_has_no_unboundlocalerror() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "issue", "reconcile"],
        cwd=str(REPO_ROOT),
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
