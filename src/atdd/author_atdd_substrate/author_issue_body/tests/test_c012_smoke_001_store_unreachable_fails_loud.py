# URN: test:author-atdd-substrate:author-issue-body:C012-SMOKE-001-store-unreachable-fails-loud
# Acceptance: acc:author-atdd-substrate:C012-SMOKE-001-store-unreachable-fails-loud
# WMBT: wmbt:author-atdd-substrate:C012
# Phase: SMOKE
# Layer: integration
"""C012-SMOKE-001 — store unreachable ⇒ CLI fails loud, no body-only.

Real end-to-end via the installed CLI in a real checkout: with the State Store
made unreachable (ATDD_CONTROL_ROOT pointed at a regular file, so the
``.atdd/state`` directory can never be created), `atdd author issue` exits
non-zero and emits NO schema-valid body to stdout — it does not silently degrade
to a body-only string. This is the recurrence guard: the store-unaware,
orphaned-#1271 authoring path cannot recur.
"""
from __future__ import annotations

import pytest

from ._helpers import run_cli


@pytest.mark.smoke
def test_c012_smoke_001_store_unreachable_fails_loud(tmp_path):
    unreachable = tmp_path / "not-a-dir"
    unreachable.write_text("i am a file, not a control root")

    proc = run_cli(
        "author", "issue",
        "--title", "Store unreachable smoke",
        "--type", "implementation",
        "--status", "INIT",
        env={"ATDD_CONTROL_ROOT": str(unreachable)},
    )

    assert proc.returncode != 0, (
        "author issue must FAIL LOUD when the store is unreachable, not exit 0\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "### Graph Context" not in proc.stdout, (
        "no schema-valid body may be emitted to stdout on a store failure "
        "(no body-only degrade — #1271 cannot recur)"
    )
    assert "store" in proc.stderr.lower(), "the failure should name the store as the unreachable dependency"
