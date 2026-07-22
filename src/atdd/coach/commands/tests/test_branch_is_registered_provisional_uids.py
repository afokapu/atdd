# URN: test:govern-lifecycle:branch-gate:tolerates-provisional-uids
# Issue: #1583 (#1579 backfill minted provisional uids)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1583 — the branch gate must not block when the slug index is unusable.

After the store backfill (#1579) every work item is keyed on a provisional
``unverified:issue-<N>`` uid rather than its semantic slug. ``branch_is_registered``
resolves a branch to a slug and does a direct uid lookup, so on such a store the
lookup can never hit while the store is non-empty — and the gate returned False
for *every* branch, hard-failing ``pre-commit`` repo-wide.

The function already documents the right principle for this ("nothing to check ⇒
don't block"); it simply recognised only an *empty* store, not an *untrustworthy*
one. Any provisional uid makes the slug index incomplete, so a miss cannot tell
"not registered" from "registered under a provisional uid" — ambiguous evidence,
which must not block. The live store is mixed, so a rule requiring an *entirely*
provisional store would never fire.

These tests pin the tolerance and — critically — that a store with ZERO provisional
uids still blocks an unregistered branch, which is the proof this is not a disabled
gate but a suspended one that self-restores when #1579 promotes the uids.
"""
from __future__ import annotations

import logging

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

# Emitted only by the store-read failure path. If this appears, a True result came
# from the exception fallback rather than from the tolerance under test.
_STORE_UNAVAILABLE = "store read unavailable"


def _root(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def _seed(tmp_path, uids):
    """Upsert one work item per uid."""
    conn = connect(init_state_store(start=tmp_path))
    try:
        store = StateStore(conn)
        for uid in uids:
            store.objects.upsert(uid, WORK_ITEM_KIND, state="INIT", data={})
        conn.commit()
    finally:
        conn.close()


def _store_facts(tmp_path, slug):
    """Return (work_item_count, slug_present) read straight from the store.

    Used to prove *why* a call returned what it did, rather than trusting the
    return value alone.
    """
    conn = connect(init_state_store(start=tmp_path))
    try:
        store = StateStore(conn)
        return len(store.objects.list(kind=WORK_ITEM_KIND)), store.objects.get(slug) is not None
    finally:
        conn.close()


_PROVISIONAL = [f"unverified:issue-{n}" for n in (1527, 1530, 1579)]


def test_all_provisional_store_does_not_block_unmatched_branch(tmp_path, caplog):
    """The regression pin: an all-provisional store must not block.

    Guarded so it cannot pass for the wrong reason — a True here must come from
    the tolerance branch, not from an empty store or a swallowed store error.
    """
    root = _root(tmp_path)
    _seed(root, _PROVISIONAL)

    count, slug_present = _store_facts(root, "config-yaml-comment-preservation")
    # The two preconditions that make this the tolerance path and nothing else:
    assert count == len(_PROVISIONAL), "store must be populated, else the empty-store branch answers"
    assert slug_present is False, "slug must be absent, else the direct-hit branch answers"

    with caplog.at_level(logging.DEBUG, logger="atdd.coach.commands.issue"):
        result = IssueManager(root).branch_is_registered("fix/config-yaml-comment-preservation")

    assert result is True
    assert _STORE_UNAVAILABLE not in caplog.text, (
        "the store read failed and the exception fallback returned True — "
        "the tolerance branch was never exercised"
    )


def test_real_slug_store_still_blocks_unregistered_branch(tmp_path):
    """The gate is not disabled: a usable slug index still blocks an unknown branch."""
    root = _root(tmp_path)
    _seed(root, ["some-real-slug", "another-real-slug"])

    assert IssueManager(root).branch_is_registered("feat/never-registered") is False


def test_mixed_store_does_not_block(tmp_path):
    """The real-world shape: provisional items alongside slugs authored after recovery.

    This is the case that actually matters — the live store is mixed, so a rule
    keyed on an *entirely* provisional store would never fire. While any provisional
    uid exists the index is incomplete, so a miss cannot tell "not registered" from
    "registered under a provisional uid". Ambiguous → must not block.
    """
    root = _root(tmp_path)
    _seed(root, _PROVISIONAL + ["a-real-slug"])

    assert IssueManager(root).branch_is_registered("feat/not-in-there") is True


def test_provisional_store_still_matches_a_present_slug(tmp_path):
    """Tolerance never masks a real hit: a slug that IS present still returns True."""
    root = _root(tmp_path)
    _seed(root, _PROVISIONAL + ["a-real-slug"])

    assert IssueManager(root).branch_is_registered("feat/a-real-slug") is True
