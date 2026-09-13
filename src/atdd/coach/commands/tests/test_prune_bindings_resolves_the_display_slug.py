# Phase: REGRESSION
# Layer: backend.unit
# Assertion: behavioral

"""``worktree prune-bindings`` clears a stale binding it addresses by DISPLAY slug (#1622).

Not an acceptance-bound test: this pins a defect found while rebasing #1622 onto
main, and there is no WMBT that owns "downstream writers resolve identity" yet.

The defect is only visible through the real producer chain, which is why this test
drives it rather than handing ``write_worktree_binding`` a slug of its own
invention:

    all_work_items()  ->  entry["slug"] = _slug_of(obj)   # the DISPLAY slug
      -> stale_bindings()  ->  StaleBinding.slug
        -> write_worktree_binding(repo_root, binding.slug, "")

``create_work_item`` mints ``wi_<ULID>`` and keeps the slug in ``data.slug`` (#1622),
so ``_slug_of`` returns a key the store is no longer keyed by. The old
``objects.get(slug)`` therefore missed and every stale binding failed to clear with
``no work item ... to bind`` — with ``--apply`` reporting the failure per binding and
retiring none of them.

The second assertion guards the other half of the fix: the write must land on the
row that was read. Upserting at the caller's display slug would leave the original
work item untouched and mint a SECOND object beside it.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach.commands.worktree_bindings import stale_bindings
from atdd.coach.commands.worktree_placement import write_worktree_binding
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.state.work_item_reader import WorkItemReader
from atdd.state.work_item_writer import create_work_item

SLUG = "a-work-item-whose-worktree-is-gone"


def _control_root(tmp_path: Path) -> Path:
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\ngithub:\n  repo: owner/repo\n  default_branch: main\n"
    )
    return root


def test_prune_bindings_clears_a_binding_addressed_by_its_display_slug(tmp_path) -> None:
    root = _control_root(tmp_path)
    absent = tmp_path / "worktrees" / "long-since-deleted"

    # Seed through the real authoring writer, so identity is minted the way
    # production mints it — not upserted at the slug by the fixture.
    conn = connect(init_state_store(start=root))
    try:
        created = create_work_item(
            conn, SLUG, state="RED",
            data={"title": "Gone", "worktree_path": str(absent)},
        )
        conn.commit()
        minted_uid = created.uid
    finally:
        conn.close()

    assert minted_uid != SLUG, "fixture is void unless the writer actually minted a uid"

    with WorkItemReader(control_root=root) as reader:
        items = reader.all_work_items()
    stale = list(stale_bindings(items))
    assert [b.slug for b in stale] == [SLUG], "the survey addresses the DISPLAY slug"

    # The defect: this raised ValueError("no work item ... to bind").
    write_worktree_binding(root, stale[0].slug, "")

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        work_items = store.objects.list(kind=WORK_ITEM_KIND)
        assert len(work_items) == 1, "the write must not mint a second object at the slug"
        assert work_items[0].uid == minted_uid
        assert (work_items[0].data or {}).get("worktree_path") == ""
    finally:
        conn.close()
