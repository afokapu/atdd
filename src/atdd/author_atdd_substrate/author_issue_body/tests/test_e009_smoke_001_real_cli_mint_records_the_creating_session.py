# URN: test:drive-state-machine:record-agent-session-identity:E009-SMOKE-001-real-cli-mint-records-the-creating-session
# Acceptance: acc:drive-state-machine:E009-SMOKE-001-real-cli-mint-records-the-creating-session
# WMBT: wmbt:drive-state-machine:E009
# Phase: SMOKE
# Harness: smoke
# Layer: integration
"""E009-SMOKE-001 — the REAL `atdd author issue` CLI records the creating session.

Issue #1540. E009-UNIT-001 runs the command in-process, which proves the publish
path calls the recorder but not that the wiring survives the real entry point.
This one spawns the actual CLI as a subprocess against a real on-disk store,
with a stub `gh` on PATH so no network is touched and no real issue is minted.

That distinction is not academic: the first GREEN of this feature had a recorder
that nothing called, and only an end-to-end invocation makes that visible.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state.agent_session import (
    KIND_AGENT_SESSION,
    REF_KIND_SESSION,
    REL_SESSION_CREATED_WORK_ITEM,
)

from ._helpers import run_cli
from ._publish_helpers import open_store, path_with_stub_gh

pytestmark = [pytest.mark.platform]

_STUB_NUMBER = 555940
SLUG = "e009-live-session-smoke"
SESSION_ID = "6453e644-64cd-4254-add5-fa30135b52b1"


@pytest.mark.smoke
def test_e009_smoke_001_real_cli_mint_records_the_creating_session(tmp_path):
    control = tmp_path / "control"
    env = {
        "ATDD_CONTROL_ROOT": str(control),
        "PATH": path_with_stub_gh(tmp_path, _STUB_NUMBER),
        "CLAUDE_CODE_SESSION_ID": SESSION_ID,
    }

    proc = run_cli(
        "author", "issue",
        "--title", "Agent session capture smoke",
        "--type", "implementation",
        "--status", "INIT",
        "--slug", SLUG,
        "--branch", f"feat/{SLUG}",
        env=env,
    )
    assert proc.returncode == 0, (
        f"`atdd author issue` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    store, conn = open_store(Path(control))
    try:
        assert store.objects.get(SLUG) is not None, "the mint itself must have landed"

        refs = [r for r in store.external_refs.all() if r.ref_kind == REF_KIND_SESSION]
        assert len(refs) == 1, (
            f"the real CLI must record the creating session; got {refs}"
        )
        assert refs[0].provider == "claude"
        assert refs[0].ref_value == SESSION_ID
        assert refs[0].data.get("last_seen_at"), "recency must be stamped at the mint"

        session_uid = refs[0].object_uid
        assert store.objects.get(session_uid).kind == KIND_AGENT_SESSION

        creator = [r for r in store.relationships.list(src_uid=session_uid)
                   if r.rel_type == REL_SESSION_CREATED_WORK_ITEM]
        assert len(creator) == 1 and creator[0].dst_uid == SLUG
    finally:
        conn.close()
