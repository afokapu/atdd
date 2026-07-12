# URN: test:author-plan-substrate:author-train:C005-UNIT-001-rejects-bad-id-and-duplicate
# Acceptance: acc:author-plan-substrate:C005-UNIT-001-rejects-bad-id-and-duplicate
# WMBT: wmbt:author-plan-substrate:C005
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C005-UNIT-001 (plan train) — create_train rejects a malformed train_id, leaving the registry unchanged.

RED: create_train / validate_train do not exist yet.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_train


def test_create_train_rejects_malformed_id(tmp_path):
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    before = (plan / "_trains.yaml").read_text()
    spec = {"train_id": "Not A Train Id", "wagons": ["demo-wagon"], "description": "x"}
    with pytest.raises(AuthorInputError):
        create_train(spec, root=tmp_path)
    assert (plan / "_trains.yaml").read_text() == before
