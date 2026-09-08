# URN: test:govern-lifecycle:reliable-manifest-registration:C016-UNIT-001-divergent-branch-name-resolves-through-the-populated-binding
# Acceptance: acc:govern-lifecycle:C016-UNIT-001-divergent-branch-name-resolves-through-the-populated-binding
# WMBT: wmbt:govern-lifecycle:C016
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C016-UNIT-001 — a branch whose name is not its work item's uid still resolves.

Issue #1720. ``branch_is_registered`` strips the ``prefix/`` segment and asks the
object store for that string as a uid. A work item's uid is its TITLE slug
(#1272) while its branch name is chosen separately, so the two coincide only by
accident — and when they diverge the gate answers "not registered" for work that
is fully registered, and the pre-commit hook blocks every commit on the branch.

Measured on the live Control Root 2026-08-03: 876 work items, 304 carrying a
populated ``data.branch``, and 206 of those 304 — the majority — have a branch
slug that is not their uid. The refusal is the common case, not an edge.

The binding this resolves through is already written: ``_record_binding_in_store``
(#1347) populates ``data.branch`` at worktree-create time and ``atdd worktree
list`` already reads exactly that field. ``branch_is_registered`` is the one
consumer that never looks.

The store is seeded through the real storage API under an isolated Control Root,
so the resolution is exercised against a real store rather than a fake — nothing
on the path is monkeypatched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

# The live #1376 divergence, reproduced exactly: the uid is the title slug, the
# branch is named separately, and stripping `feat/` does not yield the uid.
_UID = "resolve-approval-token-path-via-shared-control-root"
_BRANCH = "feat/resolve-approval-token-control-root"


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def test_c016_unit_001_divergent_branch_name_resolves_through_the_populated_binding(tmp_path):
    root = _control_root(tmp_path)
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            _UID,
            WORK_ITEM_KIND,
            state="RED",
            data={"issue_number": 1376, "branch": _BRANCH},
        )
        store.external_refs.link(_UID, GITHUB_PROVIDER, "issue", "1376")
        # Further work items, so the store is populated and the "nothing to
        # check ⇒ do not block" escape cannot be what carries the assertion.
        for n, uid in enumerate(("some-other-registered-item", "a-third-item"), start=1):
            store.objects.upsert(uid, WORK_ITEM_KIND, state="COMPLETE", data={"issue_number": 9000 + n})
        conn.commit()
    finally:
        conn.close()

    manager = IssueManager(target_dir=root)

    # The defect: the branch-derived slug is NOT a uid in this store, so the
    # lookup the gate performs today misses and the branch is refused.
    assert manager.branch_is_registered(_BRANCH) is True, (
        "a registered work item whose branch name differs from its uid must "
        "resolve through the populated data.branch binding"
    )

    # It resolves on the full branch name as stored, not on the prefix-stripped
    # slug: `data.branch` holds the branch verbatim. The stripped slug is bound
    # to no work item here and is not a uid either, so it must NOT resolve —
    # which also pins that the pass above came from the binding and not from
    # some laxer match.
    with_prefix_stripped = _BRANCH.split("/", 1)[-1]
    assert manager.branch_is_registered(with_prefix_stripped) is False, (
        "the prefix-stripped slug is bound to no work item and is no uid — it "
        "must not resolve, or the binding match is too loose to mean anything"
    )
