# URN: test:govern-lifecycle:reliable-manifest-registration:C016-UNIT-003-records-predating-the-binding-are-not-newly-stranded
# Acceptance: acc:govern-lifecycle:C016-UNIT-003-records-predating-the-binding-are-not-newly-stranded
# WMBT: wmbt:govern-lifecycle:C016
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C016-UNIT-003 — adding the binding index must not strand what answers today.

Issue #1720. ``data.branch`` is only written from ``_record_binding_in_store``
(#1347) onward: measured on the live Control Root 2026-08-03, 572 of 876 work
items carry no branch at all. If the fix REPLACED the uid-slug probe with the
binding lookup, every one of those whose branch name does happen to equal its
uid — the case the current gate answers correctly — would start being refused.
A fix for a false-refusal defect must not introduce false refusals of its own.

So the uid-slug probe is retained as a SECONDARY index. This is one source with
two indexes over it, not the dual-source `.atdd/manifest.yaml` fallback #1400
CORE-034 retired: both legs read the State Store, so they cannot disagree about
what is registered the way a store and a manifest could.

Unlike UNIT-001 and UNIT-002 this is a no-regression guard — it passes both
before and after the change. That is the point: it fails only if the fix is
written as a replacement rather than an addition.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]

# A record predating the binding: no data.branch, but its uid IS the branch slug.
_LEGACY_UID = "worktree-precommit-hook"
_LEGACY_BRANCH = "feat/worktree-precommit-hook"


def _control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def test_c016_unit_003_pre_binding_record_still_resolves_through_the_uid_index(tmp_path):
    root = _control_root(tmp_path)
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        # No "branch" key at all — exactly the shape of the 572 live records.
        store.objects.upsert(_LEGACY_UID, WORK_ITEM_KIND, state="GREEN", data={"issue_number": 102})
        store.objects.upsert(
            "an-unrelated-item", WORK_ITEM_KIND, state="COMPLETE", data={"issue_number": 103}
        )
        conn.commit()
    finally:
        conn.close()

    assert IssueManager(target_dir=root).branch_is_registered(_LEGACY_BRANCH) is True, (
        "a record predating the data.branch binding, whose uid is the branch "
        "slug, must still resolve — the binding index is added alongside the "
        "uid index, not in place of it"
    )


def test_c016_unit_003_empty_store_still_never_blocks(tmp_path):
    """A barely-initialised repo has nothing to check against and must not block."""
    root = _control_root(tmp_path)
    conn = connect(init_state_store(start=root))
    conn.close()

    assert IssueManager(target_dir=root).branch_is_registered("feat/anything-at-all") is True, (
        "an empty store holds nothing to check against — the gate must not "
        "block a repo that is not yet atdd-managed"
    )
