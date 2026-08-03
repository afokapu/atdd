# URN: test:drive-state-machine:record-agent-session-identity:E009-UNIT-003-store-failure-does-not-fail-the-mint
# Acceptance: acc:drive-state-machine:E009-UNIT-003-store-failure-does-not-fail-the-mint
# WMBT: wmbt:drive-state-machine:E009
# Phase: RED
# Harness: unit
# Layer: application
"""E009-UNIT-003 — a failing identity write degrades to a no-op, never a failed mint.

Issue #1540. Distinct from E009-UNIT-002: there the session is ABSENT, here it is
present and the WRITE ITSELF FAILS. Both must leave the operator with their issue.

Capture is observability bolted onto a chokepoint; it is never the reason the
chokepoint exists. A recorder that can take down `atdd author issue` has
inverted that, so the fault is injected at the recorder and the command is
asserted to survive it.
"""
from __future__ import annotations

import pytest

from atdd.state import agent_session

from ._publish_helpers import open_store, run_author_issue, stub_github_create

pytestmark = [pytest.mark.platform]

SLUG = "e009-fault-probe"


def test_e009_unit_003_store_failure_does_not_fail_the_mint(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "6453e644-64cd-4254-add5-fa30135b52b1")
    stub_github_create(monkeypatch)

    calls = {"n": 0}

    def _exploding_record_creator(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("store is on fire")

    monkeypatch.setattr(agent_session, "record_creator", _exploding_record_creator)

    code, _ = run_author_issue([
        "--title", "Fault probe",
        "--slug", SLUG,
        "--type", "implementation",
        "--status", "INIT",
    ])

    # the fault must actually have been injected — otherwise this test passes
    # for the wrong reason, having exercised nothing.
    assert calls["n"] > 0, "record_creator was never called; the mint is not wired to capture"
    assert code == 0, "a failing identity write must not fail the mint"

    store, conn = open_store(tmp_path)
    try:
        assert store.objects.get(SLUG) is not None, "the work item must still exist"
    finally:
        conn.close()
