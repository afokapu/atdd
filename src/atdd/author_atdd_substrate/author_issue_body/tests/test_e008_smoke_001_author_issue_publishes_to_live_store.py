# URN: test:author-atdd-substrate:author-issue-body:E008-SMOKE-001-author-issue-publishes-to-live-store
# Acceptance: acc:author-atdd-substrate:E008-SMOKE-001-author-issue-publishes-to-live-store
# WMBT: wmbt:author-atdd-substrate:E008
# Phase: SMOKE
# Layer: integration
"""E008-SMOKE-001 — `atdd author issue` publishes to a live State Store.

Real end-to-end via the installed CLI (``python -m atdd``) against a real ATDD
Control Root + State Store, with a stubbed ``gh`` on PATH returning a canned
issue URL (so the projection resolves without touching production GitHub). The
authored issue lands as a work_item plus exactly one github external_ref — the
command CREATES, it does not merely author.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._helpers import run_cli
from ._publish_helpers import open_store, path_with_stub_gh, work_item

_STUB_NUMBER = 555001


@pytest.mark.smoke
def test_e008_smoke_001_author_issue_publishes_to_live_store(tmp_path):
    control = tmp_path / "control"
    env = {
        "ATDD_CONTROL_ROOT": str(control),
        "PATH": path_with_stub_gh(tmp_path, _STUB_NUMBER),
    }

    proc = run_cli(
        "author", "issue",
        "--title", "Live store publish smoke",
        "--type", "implementation",
        "--status", "INIT",
        "--slug", "e008-live-store-smoke",
        "--branch", "feat/e008-live-store-smoke",
        "--train", "0003-author-substrate",
        "--feature", "feature:author-atdd-substrate:author-issue-body",
        env=env,
    )
    assert proc.returncode == 0, (
        f"`atdd author issue` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    store, conn = open_store(Path(control))
    try:
        obj = work_item(store, "e008-live-store-smoke")
        refs = store.external_refs.for_object(obj.uid) if obj is not None else []
    finally:
        conn.close()

    assert obj is not None and obj.kind == "work_item", "no work_item published to the live store"
    assert obj.state == "INIT"
    assert obj.data.get("title") == "Live store publish smoke"
    assert obj.data.get("body"), "the authored body must be stored in the work_item"

    assert len(refs) == 1, f"expected exactly one github external_ref (one-per-issue, #1220), got {len(refs)}"
    assert refs[0].provider == "github"
    assert refs[0].ref_kind == "issue"
    assert refs[0].ref_value == str(_STUB_NUMBER)
