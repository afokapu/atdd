# URN: test:author-plan-substrate:author-train:E004-UNIT-005-typed-train-bucket-agreement
# Acceptance: acc:author-plan-substrate:E004-UNIT-005-typed-train-bucket-agreement
# WMBT: wmbt:author-plan-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-005 (plan train) — both _trains.yaml writers agree on the bucket for a typed id.

Refs #1504. Two writers share plan/_trains.yaml without sharing the function that
decides where an entry goes:

  * ``planner.commands.author._train_home`` buckets a typed ``train:<subject>:<slug>``
    id by subject/category, per the #1421 grammar
    (``train.convention.yaml`` naming.train_id + registry benefits: "trains bucketed by subject").
  * ``coach.commands.registry.RegistryBuilder.build_trains`` predates #1421 and derives
    its bucket from the legacy ``NNXX`` digit grammar, so a typed id with no leading
    digit falls through to the default ``0-commons`` / ``00-commons-nominal``.

The divergence has two distinct failure modes depending on which writer ran last, and
``_upsert_train_registry``'s dedup is bucket-local so it cannot see the twin. Both are
pinned below, plus the nested-discovery gap that lets the rebuild ignore a typed
manifest entirely.

RED: build_trains buckets by digit theme and globs ``_trains/*.yaml`` flat.
"""
from __future__ import annotations

import yaml

from atdd.coach.commands.registry import RegistryBuilder
from atdd.planner.commands.author import create_train

TYPED_ID = "train:issue-lifecycle:demo"
SUBJECT_BUCKET = ("issue-lifecycle", "nominal")
LEGACY_BUCKET = ("0-commons", "00-commons-nominal")


def _spec(train_id: str = TYPED_ID) -> dict:
    return {
        "train_id": train_id,
        "description": "a typed train for the bucket-agreement test",
        "category": "nominal",
        "wagons": [],
        "participants": [],
    }


def _seed(tmp_path):
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    return plan


def _buckets(plan) -> dict:
    return yaml.safe_load((plan / "_trains.yaml").read_text(encoding="utf-8"))["trains"]


def _entries_for(buckets: dict, train_id: str) -> list:
    """Every entry carrying train_id, paired with the (group, sub) bucket holding it."""
    found = []
    for group, subs in (buckets or {}).items():
        for sub, entries in (subs or {}).items():
            for entry in entries or []:
                if isinstance(entry, dict) and entry.get("train_id") == train_id:
                    found.append(((group, sub), entry))
    return found


def test_rebuild_keeps_a_typed_train_in_its_subject_bucket(tmp_path):
    """author -> rebuild: build_trains must not relocate the entry to the digit bucket."""
    plan = _seed(tmp_path)
    create_train(_spec(), root=tmp_path)
    assert [b for b, _ in _entries_for(_buckets(plan), TYPED_ID)] == [SUBJECT_BUCKET]

    RegistryBuilder(repo_root=tmp_path).build_trains(mode="apply")

    placed = [b for b, _ in _entries_for(_buckets(plan), TYPED_ID)]
    assert placed == [SUBJECT_BUCKET], (
        f"rebuild relocated the typed train to {placed}; expected {[SUBJECT_BUCKET]}"
    )
    assert LEGACY_BUCKET[0] not in _buckets(plan)


def test_authoring_after_a_rebuild_does_not_create_a_second_entry(tmp_path):
    """rebuild -> author: the bucket-local dedup must not miss a twin in another bucket."""
    plan = _seed(tmp_path)
    create_train(_spec(), root=tmp_path)
    RegistryBuilder(repo_root=tmp_path).build_trains(mode="apply")

    create_train(_spec(), root=tmp_path)

    placed = [b for b, _ in _entries_for(_buckets(plan), TYPED_ID)]
    assert placed == [SUBJECT_BUCKET], (
        f"{len(placed)} entries for one train_id, in buckets {placed}"
    )


def test_rebuild_discovers_a_nested_typed_per_train_file(tmp_path):
    """A typed manifest's only home is plan/_trains/<subject>/<slug>.yaml — glob it."""
    plan = _seed(tmp_path)
    create_train(_spec(), root=tmp_path)
    assert (plan / "_trains" / "issue-lifecycle" / "demo.yaml").exists()
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")

    stats = RegistryBuilder(repo_root=tmp_path).build_trains(mode="apply")

    assert stats["processed"] == 1, (
        "nested typed per-train file was not discovered as a manifest"
    )
    assert [b for b, _ in _entries_for(_buckets(plan), TYPED_ID)] == [SUBJECT_BUCKET]


def test_rebuild_preserves_a_non_nominal_category(tmp_path):
    """category is a validated FIELD (#1421), and the bucket derivation reads it.

    A rebuild that drops it both loses data and silently re-buckets an `exception`
    train as `nominal` on the next pass.
    """
    plan = _seed(tmp_path)
    spec = _spec("train:object-conflict:resolve")
    spec["category"] = "exception"
    create_train(spec, root=tmp_path)
    assert [b for b, _ in _entries_for(_buckets(plan), spec["train_id"])] == [
        ("object-conflict", "exception")
    ]

    RegistryBuilder(repo_root=tmp_path).build_trains(mode="apply")

    placed = _entries_for(_buckets(plan), spec["train_id"])
    assert [b for b, _ in placed] == [("object-conflict", "exception")], (
        f"rebuild re-bucketed an exception train to {[b for b, _ in placed]}"
    )
    assert placed[0][1].get("category") == "exception", "rebuild dropped the category field"


def test_rebuild_ignores_underscore_prefixed_subdirectories(tmp_path):
    """plan/_trains/_interlockings/*.yaml sits at nesting depth 2 and is not a train."""
    plan = _seed(tmp_path)
    create_train(_spec(), root=tmp_path)
    il_dir = plan / "_trains" / "_interlockings"
    il_dir.mkdir()
    (il_dir / "enforce-something.yaml").write_text(
        yaml.safe_dump({"interlocking_id": "il:demo:enforce-something", "routes": []}),
        encoding="utf-8",
    )

    RegistryBuilder(repo_root=tmp_path).build_trains(mode="apply")

    flat = [
        entry
        for subs in (_buckets(plan) or {}).values()
        for entries in (subs or {}).values()
        for entry in entries or []
    ]
    ids = {e.get("train_id") for e in flat}
    assert ids == {TYPED_ID}, f"interlocking leaked into the train registry: {ids}"
