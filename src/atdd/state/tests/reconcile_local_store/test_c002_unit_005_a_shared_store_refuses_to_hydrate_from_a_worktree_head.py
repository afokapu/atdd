# URN: test:reconcile-local-store:guard-dirty-store:C002-UNIT-005-a-shared-store-refuses-to-hydrate-from-a-worktree-head
# Acceptance: acc:reconcile-local-store:C002-UNIT-005-a-shared-store-refuses-to-hydrate-from-a-worktree-head
# WMBT: wmbt:reconcile-local-store:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: a Control Root that is not itself a git checkout (the flat-sibling shared project-root store) refuses to reconcile against any worktree's HEAD, naming the layout, while a single-repo Control Root reconciles unchanged. Refs #1580.
"""A shared store has no HEAD of its own, so it will not borrow one (C002-UNIT-005).

wagon: reconcile-local-store | feature: guard-dirty-store | phase: RED
WMBT: wmbt:reconcile-local-store:C002

The interim ownership guard, ahead of the daemon work in #1580's Priority 2.

In the flat-sibling layout the Control Root resolves to the *project root* — the parent
of the primary ``main/`` checkout — and every worktree shares the one store beneath it
(``paths.resolve_control_root`` rule 1.5). That directory is not a git repository. It has
no HEAD, no branch, and no commits; the ~130 worktrees around it each have their own.

Reconcile is defined against a commit: ``store == hydrate(projection @ base) + overlay``.
For a store whose Control Root is not a checkout, there is no such commit — so reconcile
was resolving one from whichever worktree happened to invoke it. That is not a detail: it
means the shared store's contents depended on which of a hundred-odd arbitrary HEADs moved
last, and an older feature branch could roll every other worktree's view backward.

The store must not answer to a HEAD that does not describe it. Whether ownership ends up
per-worktree or single-daemon is the open architectural question; *this* is true either
way, so it is guarded now rather than waiting for that decision.

The rule is deliberately shaped as "the Control Root must itself be the checkout whose
HEAD it is reconciled against", which is exactly the single-repo case that ships to
consumers — so nothing legitimate is refused. Refs #1580.
"""
from __future__ import annotations

import pytest

from atdd.state import metadata
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.reconcile import SharedStoreReconcileRefused, hydrate_store, reconcile
from atdd.state.store import StateStore

from ._helpers import UID_A, UID_B, checkout, commit_all, document, store, store_bytes, write_projection


def test_c002_unit_005_a_single_repo_control_root_reconciles_unchanged(tmp_path) -> None:
    """The shipping layout — Control Root *is* the checkout — is untouched by the guard."""
    repo = checkout(tmp_path / "repo")
    write_projection(repo, [document(UID_A), document(UID_B)])
    commit_all(repo, "base projection")

    assert hydrate_store(repo)[0] == 2
    result = reconcile(repo)
    assert result.mode == "hydrate"


def test_c002_unit_005_a_shared_store_refuses_to_hydrate_from_a_worktree_head(tmp_path) -> None:
    """A Control Root that is not a checkout refuses, and says which layout it is in."""
    # The flat-sibling shape: <project>/main/ is the primary checkout, <project>/ holds the
    # shared store, and <project>/ is NOT a git repository.
    project = tmp_path / "project"
    project.mkdir()
    main = checkout(project / "main")
    write_projection(main, [document(UID_A)])
    commit_all(main, "base projection")

    # The shared store lives at the project root, beside the checkouts rather than inside one.
    (project / ".atdd").mkdir(exist_ok=True)
    (project / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    write_projection(project, [document(UID_A), document(UID_B)])

    conn = store(project)
    try:
        state_store = StateStore(conn)
        for uid in (UID_A, UID_B):
            state_store.objects.upsert(uid, WORK_ITEM_KIND, state="GREEN", data={"state": "ACTIVE"})
        # Anchored to a commit borrowed from a worktree — which is the defect itself.
        metadata.stamp_base_commit(conn, commit_all(main, "a worktree moves HEAD"))
    finally:
        conn.close()

    before = store_bytes(project)

    with pytest.raises(SharedStoreReconcileRefused) as refused:
        reconcile(project, head="0" * 40)

    message = str(refused.value)
    assert str(project) in message, "the refusal must name the Control Root it refused for"
    assert "not a git" in message.lower() or "checkout" in message.lower()

    # Nothing touched, and both objects still there.
    assert store_bytes(project) == before
    conn = store(project)
    try:
        assert len(StateStore(conn).objects.list(kind=WORK_ITEM_KIND)) == 2
    finally:
        conn.close()


def test_c002_unit_005_the_guard_refuses_the_overwrite_path_too(tmp_path) -> None:
    """hydrate is the path that actually replaces state, so it is guarded at the same point."""
    project = tmp_path / "project"
    project.mkdir()
    checkout(project / "main")
    (project / ".atdd").mkdir(exist_ok=True)
    (project / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    write_projection(project, [document(UID_A)])

    with pytest.raises(SharedStoreReconcileRefused):
        hydrate_store(project)
