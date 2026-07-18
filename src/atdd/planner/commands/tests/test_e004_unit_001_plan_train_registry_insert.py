# URN: test:author-plan-substrate:author-train:E004-UNIT-001-registry-insert-and-per-train-file
# Acceptance: acc:author-plan-substrate:E004-UNIT-001-registry-insert-and-per-train-file
# WMBT: wmbt:author-plan-substrate:E004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-001 (plan train) — create_train dedup-inserts into _trains.yaml and writes the per-train file.

RED: create_train does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.planner.commands.author import AuthorInputError, create_train


def test_create_train_registers_and_writes_per_train_file(tmp_path):
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    spec = {"train_id": "0009-demo-train", "wagons": ["demo-wagon"],
            "description": "a demo train for the writer test"}
    per_train = create_train(spec, root=tmp_path)
    assert per_train == plan / "_trains" / "0009-demo-train.yaml"
    assert per_train.exists()
    registry = yaml.safe_load((plan / "_trains.yaml").read_text())
    assert "0009-demo-train" in yaml.safe_dump(registry)


def _typed_spec():
    return {"train_id": "train:issue-lifecycle:demo", "category": "nominal",
            "wagons": [], "description": "a typed train for the shape guard"}


def test_legacy_list_shaped_registry_refuses_with_migration_hint(tmp_path):
    """Issue #1236 — a pre-#1421 list-shaped 'trains:' must fail loudly.

    It used to reach `.setdefault` on the list and surface a bare
    `AttributeError: 'list' object has no attribute 'setdefault'`.
    """
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text(
        "trains:\n- train_id: train:legacy:old-shape\n", encoding="utf-8")

    with pytest.raises(AuthorInputError) as exc:
        create_train(_typed_spec(), root=tmp_path)

    assert exc.value.field == "registry"
    # The operator is told what is wrong AND how to get out of it.
    assert "legacy list-shaped" in str(exc.value)
    assert "atdd registry update trains" in str(exc.value)
    # Nothing partially written on the refusal path.
    assert not (plan / "_trains" / "issue-lifecycle").exists()


def test_non_mapping_registry_refuses_with_migration_hint(tmp_path):
    """A whole-file list (no 'trains:' key at all) is refused the same way."""
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("- train_id: train:legacy:old\n", encoding="utf-8")

    with pytest.raises(AuthorInputError) as exc:
        create_train(_typed_spec(), root=tmp_path)

    assert exc.value.field == "registry"
    assert "atdd registry update trains" in str(exc.value)
