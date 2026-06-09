# URN: test:consolidate-coach-workspace:enforce-surface-conformance:C001-SMOKE-001-live-never-collapse
# Acceptance: acc:consolidate-coach-workspace:C001-SMOKE-001-live-never-collapse
# WMBT: wmbt:consolidate-coach-workspace:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — live never-collapse headline (issue #865).

Spawn N>=2 real per-workspace surfaces on live cmux, run the real conformance
layout pass, then read ``surface.list`` per worker-workspace and assert each still
yields exactly ONE worker identity — no worker migrated into another worker's or
the coach's workspace. A layout that makes two workers share a daemon scope FAILS.
Runs wherever cmux is on PATH; skips otherwise."""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("cmux") is None,
    reason="live cmux not available; run where the cmux CLI is installed",
)


def test_c001_smoke_001_live_never_collapse(tmp_path):
    from atdd.consolidate_coach_workspace.enforce_surface_conformance.live_smoke import (
        never_collapse_live_smoke,
    )

    evidence = never_collapse_live_smoke(
        evidence_path=str(tmp_path / "evidence.txt"), worker_count=2
    )

    # each worker resolved to its own workspace, single identity each
    identities = evidence["identities_by_workspace"]
    assert len(identities) >= 2, "expected >=2 distinct worker workspaces"
    for workspace_id, ids in identities.items():
        assert len(ids) == 1, (
            f"workspace {workspace_id} holds {len(ids)} identities — "
            f"never-collapse violated (#865/#1013)"
        )
    # no two workers share a workspace (no daemon-scope collapse)
    all_ids = [i for ids in identities.values() for i in ids]
    assert len(all_ids) == len(set(all_ids))
