# URN: test:govern-lifecycle:govern-lifecycle:C024-SMOKE-001-the-repository-own-store-and-registry-agree
# Acceptance: acc:govern-lifecycle:C024-SMOKE-001-the-repository-own-store-and-registry-agree
# WMBT: wmbt:govern-lifecycle:C024
# Phase: SMOKE
# Layer: application
"""C024-SMOKE-001 — the two readers of one directory agree, in this repository.

The constructed cases in UNIT-001/002 can only approximate this. The defect is a
DISAGREEMENT BETWEEN TWO READERS of `plan/_trains/`, and a fixture would have to
reproduce that disagreement faithfully in order to find it — which is to say the
fixture would be asserting the thing it was built from.

So this reads both sides for real: the registry through `_registered_train_ids`,
and the train values the State Store actually records for its work items.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.utils.train_identity import normalize_train_id, normalize_train_ids

def _recorded_trains(repo_root: Path) -> dict[str, str]:
    """`{slug: train}` for every work item that records one."""
    from atdd.state.work_item_reader import WorkItemReader

    with WorkItemReader(control_root=repo_root) as reader:
        items = reader.all_work_items()
    return {
        str(item.get("slug")): str(item["train"])
        for item in items
        if item.get("train")
    }


@pytest.mark.coder
@pytest.mark.platform
def test_every_registered_train_resolves_in_both_vocabularies():
    """Over this repository's real registry, not a constructed pair.

    The registry genuinely mixes both shapes, so iterating it is what proves the
    normalization is symmetric — a one-way strip passes for one half of it.
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self check — reads this repository's own registry")

    repo_root = Path(find_repo_root())
    mgr = IssueManager(target_dir=repo_root)
    registered = IssueManager._registered_train_ids(repo_root / "plan")

    assert len(registered) > 10, (
        f"only {len(registered)} trains registered — this check would be nearly "
        "vacuous; the registry is expected to hold both shapes"
    )

    unresolved = [
        (train_id, spelling)
        for train_id in sorted(registered)
        for spelling in (train_id, f"train:{normalize_train_id(train_id)}")
        if not mgr._validate_train_against_trains_yaml(spelling)[0]
    ]

    assert not unresolved, (
        "every REGISTERED train must resolve however it is spelled — the store "
        f"may record either shape: {unresolved[:10]}"
    )


@pytest.mark.coder
@pytest.mark.platform
def test_no_work_item_is_wedged_by_a_spelling():
    """The wedge condition, stated precisely, over the real store.

    A work item is wedged BY A SPELLING when the train it records is one the
    registry declares and the gate rejects anyway. That is the whole of what this
    WMBT fixes.

    It is deliberately NOT "every recorded train resolves". Measured on this
    store, 41 live work items record `0001-self-compliance-validate`,
    `0002-coach-drives-lifecycle` or `0003-author-substrate` — trains RETIRED from
    the registry. Those items are wedged too, by a missing train rather than a
    misspelled one, and asserting them here would make this test fail for a
    defect it does not fix and cannot fix by normalizing anything.
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self check — reads this repository's own store and registry")

    repo_root = Path(find_repo_root())
    mgr = IssueManager(target_dir=repo_root)
    registered = normalize_train_ids(IssueManager._registered_train_ids(repo_root / "plan"))
    recorded = _recorded_trains(repo_root)

    assert recorded, (
        "no work item in the store records a train, so this check observed "
        "nothing — it must not report a pass over an empty reading"
    )

    wedged = {
        slug: train
        for slug, train in recorded.items()
        if normalize_train_id(train) in registered
        and not mgr._validate_train_against_trains_yaml(train)[0]
    }

    assert not wedged, (
        "these work items record a train the registry DOES declare, and the gate "
        f"rejects it anyway — wedged purely by spelling: {sorted(wedged.items())[:10]}"
    )


@pytest.mark.coder
@pytest.mark.platform
def test_the_legacy_numbered_family_is_retired():
    """Formerly: the seven legacy trains resolve in the shape the graph mints.

    That assertion invited its own retirement -- "if it was deliberately retired,
    retire this assertion with it" -- and #1986 retired the family it named. All
    seven now carry typed `train:extension-conventions:<slug>` identities and live
    in a subject directory, so no train file sits loose under `plan/_trains/` and
    the `train:<stem>` shape `graph_builder` minted for one cannot arise.

    Its sibling docstring guarded against "fixing" C024 by quietly dropping the
    legacy family from the registry. That is worth keeping, so the guard is kept
    and inverted: the family must be GONE, and gone by migration rather than by
    deletion -- every one of the seven still resolves, under its typed id, with a
    registry row and a document. A silent drop fails this just as loudly.
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self check — reads this repository's own registry")

    repo_root = Path(find_repo_root())
    mgr = IssueManager(target_dir=repo_root)
    registered = IssueManager._registered_train_ids(repo_root / "plan")

    loose = sorted(
        p.stem for p in (repo_root / "plan" / "_trains").glob("*.yaml")
        if not p.name.startswith("_")
    )
    assert not loose, (
        f"a train file sits loose under plan/_trains/, reviving the ambiguity "
        f"C024 is about: {loose}"
    )

    from atdd.planner.migration.train_urn_migration import LEGACY_TRAIN_ALIASES

    retyped = {
        legacy: f"train:{subject}:{slug}"
        for legacy, (subject, slug) in LEGACY_TRAIN_ALIASES.items()
        if subject == "extension-conventions"
    }
    assert len(retyped) == 7, f"expected the seven, found {len(retyped)}"

    missing = sorted(t for t in retyped.values() if t not in registered)
    assert not missing, (
        "the legacy family must be retired BY MIGRATION, not by deletion — these "
        f"typed trains are absent from the registry: {missing}"
    )

    unresolved = [
        (typed, messages)
        for typed in sorted(retyped.values())
        for ok, messages in [mgr._validate_train_against_trains_yaml(typed)]
        if not ok
    ]
    assert not unresolved, f"the gate must resolve every retyped train: {unresolved}"
