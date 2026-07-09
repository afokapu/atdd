# URN: test:author-plan-substrate:author-train:E004-UNIT-003-alternate-path-train-carries-sequence
# Acceptance: acc:author-plan-substrate:E004-UNIT-003-alternate-path-train-carries-sequence
# WMBT: wmbt:author-plan-substrate:E004
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-003 — the per-train document writer is category-agnostic.

Train ids are [Theme][Category][Variation]. Category digit 2 = alternate path
(0201, 0202 …). The document writer must never branch on any digit of the id;
an alternate-path train carries `themes` / `sequence` exactly as a nominal one.

RED: neither carries them today, so the equality below holds vacuously on the
missing-key side — the explicit `in doc` assertions are what fail.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.planner.commands.author import create_train


def _spec(train_id: str) -> dict:
    return {
        "train_id": train_id,
        "title": "Category probe",
        "description": "identical but for the train_id category digit",
        "themes": ["commons"],
        "primary_wagon": "demo-wagon",
        "wagons": ["demo-wagon"],
        "participants": ["wagon:demo-wagon"],
        "sequence": [
            {
                "step": 1,
                "intent": "carry the sequence through the writer",
                "from": "wagon:demo-wagon",
                "to": "system:atdd-cli",
                "artifact": "commons:manifest",
            },
        ],
    }


def _author(tmp_path: Path, train_id: str) -> dict:
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    per_train = create_train(_spec(train_id), root=tmp_path)
    return yaml.safe_load(per_train.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "train_id",
    [
        "0009-nominal-probe",     # category 0 — nominal
        "0209-alternate-probe",   # category 2 — alternate path
        "0309-exception-probe",   # category 3 — exception
    ],
)
def test_every_category_carries_themes_and_sequence(tmp_path, train_id):
    doc = _author(tmp_path, train_id)
    assert doc["themes"] == ["commons"]
    assert doc["sequence"] == _spec(train_id)["sequence"]


def test_nominal_and_alternate_documents_differ_only_by_train_id(tmp_path):
    nominal = _author(tmp_path / "a", "0009-probe")
    alternate = _author(tmp_path / "b", "0209-probe")
    assert nominal.pop("train_id") == "0009-probe"
    assert alternate.pop("train_id") == "0209-probe"
    assert nominal == alternate, "the writer must not branch on the category digit"
