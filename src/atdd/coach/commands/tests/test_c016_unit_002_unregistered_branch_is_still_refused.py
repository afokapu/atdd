# URN: test:govern-lifecycle:reliable-manifest-registration:C016-UNIT-002-unregistered-branch-is-still-refused
# Acceptance: acc:govern-lifecycle:C016-UNIT-002-unregistered-branch-is-still-refused
# WMBT: wmbt:govern-lifecycle:C016
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C016-UNIT-002 — the gate is repaired, not widened into a pass.

Issue #1720. The cheapest way to stop a commit gate refusing registered work is
to make it stop refusing anything. That would satisfy UNIT-001 and destroy the
control, so this acceptance holds the other edge: a branch bound to no work item
in a POPULATED store must still be refused.

Both legs run against the SAME store, so the refusal is proved discriminating
rather than blanket — a gate that answered False for everything would fail the
bound leg, and a gate that answered True for everything would fail the unbound
one. Only a gate that actually resolves passes both.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

_BOUND_UID = "a-registered-title-slug"
_BOUND_BRANCH = "feat/a-branch-named-differently"
_UNBOUND_BRANCH = "feat/never-registered-anywhere"


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def test_c016_unit_002_unregistered_branch_is_still_refused(tmp_path):
    root = _control_root(tmp_path)
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            _BOUND_UID,
            WORK_ITEM_KIND,
            state="RED",
            data={"issue_number": 4242, "branch": _BOUND_BRANCH},
        )
        store.external_refs.link(_BOUND_UID, GITHUB_PROVIDER, "issue", "4242")
        store.objects.upsert(
            "an-unrelated-completed-item", WORK_ITEM_KIND, state="COMPLETE", data={"issue_number": 4243}
        )
        conn.commit()
    finally:
        conn.close()

    manager = IssueManager(target_dir=root)

    # Neither bound in data.branch nor equal to any uid: genuinely unregistered.
    assert manager.branch_is_registered(_UNBOUND_BRANCH) is False, (
        "a branch bound to no work item in a populated store must still be "
        "refused — the fix must repair the resolution, not remove the gate"
    )

    # Same store, same call: a bound branch resolves. This is the leg that fails
    # before the fix, and it is what proves the refusal above is discriminating.
    assert manager.branch_is_registered(_BOUND_BRANCH) is True, (
        "a branch bound through data.branch must resolve in the same store that "
        "refuses the unbound one"
    )
