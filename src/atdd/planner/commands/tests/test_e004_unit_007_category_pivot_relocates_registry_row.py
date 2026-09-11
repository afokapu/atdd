# Purpose: a category pivot moves a typed train's registry row instead of forking
# a second row under the bucket it left.
# Acceptance: acc:author-plan-substrate:E004-UNIT-007-category-pivot-relocates-registry-row
"""E004-UNIT-007 — a pivoted category relocates the row; it does not clone it.

RED: `train_bucket` derives a typed train's bucket from (subject, category), and
the dedup in `_upsert_train_registry` is bucket-LOCAL — the hazard `train_bucket`'s
own docstring names (#1504). Changing `category` therefore appends a second row
under the new bucket and leaves the first where it was, so one train_id is filed
twice. `train_relpath` ignores category, so both rows point at the same file.
"""
import yaml

from atdd.planner.commands.author import create_train

TRAIN_ID = "train:issue-lifecycle:pivot-demo"


def _spec(category):
    return {
        "train_id": TRAIN_ID,
        "category": category,
        "title": "Pivot demo",
        "description": "a train that changes category",
        "themes": ["coach"],
        "wagons": ["wagon-a"],
        "sequence": [{"step": 1, "actor": "wagon:wagon-a", "action": "does the thing"}],
    }


def _buckets(root):
    registry = yaml.safe_load((root / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    return {
        (group, sub): [e["train_id"] for e in entries]
        for group, buckets in registry["trains"].items()
        for sub, entries in buckets.items()
    }


def test_a_category_pivot_leaves_exactly_one_row_in_the_new_bucket(tmp_path):
    (tmp_path / "plan").mkdir()
    create_train(_spec("nominal"), root=tmp_path)
    assert _buckets(tmp_path) == {("issue-lifecycle", "nominal"): [TRAIN_ID]}

    path = create_train(_spec("error"), root=tmp_path)

    buckets = _buckets(tmp_path)
    rows = sum(ids.count(TRAIN_ID) for ids in buckets.values())
    assert rows == 1, f"one train_id must yield one row; found {rows} in {buckets}"
    assert buckets == {("issue-lifecycle", "error"): [TRAIN_ID]}, (
        "the row must move to the new bucket, and the bucket it left must be pruned "
        "rather than kept as an empty list"
    )
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["category"] == "error"
