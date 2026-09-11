# Purpose: re-authoring a train writes the changed spec to the manifest and the
# registry row without deleting post-authoring state or resetting the phase.
# Acceptance: acc:author-plan-substrate:E004-UNIT-006-reauthor-updates-without-clobbering
"""E004-UNIT-006 — a re-authored train lands; a lived-in train survives it.

RED: `create_train` skips the write entirely when the per-train file already
exists, and `_upsert_train_registry` appends only when the id is absent, so a
re-author changes nothing at all. The naive repair — write unconditionally —
would delete every train.schema property the writer does not emit (`route_space`
rides on 7 of the 21 in-repo trains today) and reset `status` to `planned`. Both
halves are pinned here so neither regression can return.
"""
import yaml

from atdd.planner.commands.author import create_train


def _spec(**overrides):
    spec = {
        "train_id": "train:issue-lifecycle:reauthor-demo",
        "category": "nominal",
        "title": "Reauthor demo",
        "description": "the first authoring",
        "themes": ["coach"],
        "family": "behavior",
        "wagons": ["wagon-a"],
        "sequence": [{"step": 1, "actor": "wagon:wagon-a", "action": "does the first thing"}],
    }
    spec.update(overrides)
    return spec


def _registry_row(root):
    registry = yaml.safe_load((root / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    rows = [
        entry
        for buckets in registry["trains"].values()
        for entries in buckets.values()
        for entry in entries
        if entry["train_id"] == "train:issue-lifecycle:reauthor-demo"
    ]
    assert len(rows) == 1, f"expected exactly one registry row, got {len(rows)}"
    return rows[0]


def test_reauthor_updates_the_manifest_and_the_registry_row(tmp_path):
    (tmp_path / "plan").mkdir()
    create_train(_spec(), root=tmp_path)

    path = create_train(
        _spec(
            title="Reauthor demo v2",
            description="the second authoring",
            wagons=["wagon-a", "wagon-b"],
            sequence=[
                {"step": 1, "actor": "wagon:wagon-a", "action": "does the first thing"},
                {"step": 2, "actor": "wagon:wagon-b", "action": "does the new second thing"},
            ],
        ),
        root=tmp_path,
    )

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["title"] == "Reauthor demo v2"
    assert doc["description"] == "the second authoring"
    assert doc["participants"] == ["wagon:wagon-a", "wagon:wagon-b"]
    assert len(doc["sequence"]) == 2

    row = _registry_row(tmp_path)
    assert row["description"] == "the second authoring"
    assert row["wagons"] == ["wagon-a", "wagon-b"]


def test_reauthor_preserves_post_authoring_keys_and_the_advanced_status(tmp_path):
    """`route_space`, `test`, `code` and `sort_key` arrive after authoring.

    The writer does not own them and must not delete them; `status` is advanced by
    the phase machine and must not walk backwards to the writer's seed value.
    """
    (tmp_path / "plan").mkdir()
    path = create_train(_spec(), root=tmp_path)

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["status"] = "tested"
    doc["route_space"] = {"classification": "single-route", "basis": "not-yet-assessed"}
    doc["test"] = {"backend": ["tests/test_reauthor.py"], "frontend": []}
    doc["code"] = {"backend": ["src/atdd/reauthor.py"], "frontend": []}
    doc["sort_key"] = 42
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    create_train(_spec(description="the second authoring"), root=tmp_path)

    after = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert after["description"] == "the second authoring", "the re-author must land"
    assert after["status"] == "tested", "a re-author must not reset the phase"
    assert after["route_space"] == doc["route_space"]
    assert after["test"] == doc["test"]
    assert after["code"] == doc["code"]
    assert after["sort_key"] == 42


def test_an_authored_key_dropped_from_the_spec_is_dropped_from_the_manifest(tmp_path):
    """The spec is authoritative for what it owns — otherwise a removal is unsayable."""
    (tmp_path / "plan").mkdir()
    path = create_train(_spec(), root=tmp_path)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["family"] == "behavior"

    spec = _spec()
    del spec["family"]
    create_train(spec, root=tmp_path)

    assert "family" not in yaml.safe_load(path.read_text(encoding="utf-8"))
