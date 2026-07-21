# URN: test:place-worktrees:place-worktrees:Y001-UNIT-002-unbound-worktree-declines-rather-than-guessing
# Acceptance: acc:place-worktrees:Y001-UNIT-002-unbound-worktree-declines-rather-than-guessing
# WMBT: wmbt:place-worktrees:Y001
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""Y001-UNIT-002 — an unbound worktree gets no offer, and no guess.

Issue #1524, Decision 5 (revised) and Decision 6. This is the acceptance that
un-gated the whole issue. The Phase 0(b) audit measured 77 of 113 live worktrees
with no store binding at all, and 56 of those UNRECOVERABLE — never `atdd`-created,
with no work item to bind to. The original scope claimed that drift blocked
config-driven placement, because the relocation offer could not identify "your
worktree".

It does not block it, and this test is why: the offer DECLINES for an unbound
worktree rather than guessing. An unbound worktree simply gets no offer, so the
36 coherent worktrees are relocatable today and the drift is a data-hygiene
problem — split to #1529 as a sibling, not a prereq.

The decline must also be legible. "Relocation failed" and "there is nothing here
to relocate" are different facts, and reporting the second as the first is what
would send an operator hunting a bug that does not exist.

Phase RED: fails on the import — the relocation seam does not exist.
Phase GREEN: unbound worktrees are declined, by reason, without being moved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

BOUND_SLUG = "config-driven-worktree-placement"
BOUND_ISSUE = 1524


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A control root with ONE bound worktree and one entirely unbound one."""
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        "worktree_root: worktrees\n"
    )

    bound = root.parent / f"feat-{BOUND_SLUG}"
    bound.mkdir(parents=True)

    # Modelled on the real unrecoverable population: an ad-hoc checkout that
    # atdd never created and that matches no work item by branch or slug.
    unbound = root.parent / "cw-phase0"
    unbound.mkdir(parents=True)
    (unbound / "scratch.txt").write_text("ad-hoc work\n")

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            BOUND_SLUG,
            WORK_ITEM_KIND,
            state="RED",
            data={
                "issue_number": BOUND_ISSUE,
                "type": "implementation",
                "branch": f"feat/{BOUND_SLUG}",
                "worktree_path": str(bound),
            },
        )
        store.external_refs.link(BOUND_SLUG, GITHUB_PROVIDER, "issue", str(BOUND_ISSUE))
        conn.commit()
    finally:
        conn.close()
    return root, bound, unbound


def test_y001_unit_002_unbound_worktree_declines_rather_than_guessing(tmp_path):
    from atdd.coach.commands.worktree_placement import relocation_offer

    root, bound, unbound = _repo(tmp_path)

    offer = relocation_offer(root, unbound)

    # Nothing is offered, and nothing is moved.
    assert offer.offered is False, (
        f"an offer was made for the unbound worktree {unbound}; with 56 "
        "unrecoverable worktrees on this repo alone, guessing is how real work "
        "gets moved out from under someone"
    )
    assert unbound.exists() and (unbound / "scratch.txt").exists(), (
        "the unbound worktree was touched despite no offer being made"
    )

    # The decline is legible: unbound, not failed.
    assert offer.reason == "unbound", (
        f"declined with reason {offer.reason!r}; an unbound worktree is not a "
        "relocation failure and must not be reported as one"
    )

    # Guard against a vacuous pass: the same call on a BOUND worktree must
    # offer. A `relocation_offer` that declined everything would satisfy every
    # assertion above while making the feature useless.
    bound_offer = relocation_offer(root, bound)
    assert bound_offer.offered is True, (
        "the bound worktree was also declined — declining everything is not "
        "the same as declining what cannot be identified"
    )
    assert bound_offer.destination == root / "worktrees" / f"feat-{BOUND_SLUG}"
