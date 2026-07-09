# URN: test:author-plan-substrate:author-train:E004-UNIT-004-preserves-caller-participants
# Acceptance: acc:author-plan-substrate:E004-UNIT-004-preserves-caller-participants
# WMBT: wmbt:author-plan-substrate:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E004-UNIT-004 — caller-supplied participants survive the writer.

RED: create_train unconditionally overwrites participants with
`[f"wagon:{w}" for w in spec["wagons"]]`, silently discarding every
`system:*` / `user:*` principal the caller passed. train.schema.json admits
all three prefixes, so the discard is lossy, not normalizing.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.planner.commands.author import create_train


def _author(tmp_path: Path, spec: dict) -> dict:
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")
    per_train = create_train(spec, root=tmp_path)
    return yaml.safe_load(per_train.read_text(encoding="utf-8"))


def _base(train_id: str = "0009-participants-probe") -> dict:
    return {
        "train_id": train_id,
        "title": "Participants probe",
        "description": "a train carrying a non-wagon principal",
        "themes": ["commons"],
        "wagons": ["demo-wagon"],
        "sequence": [
            {
                "step": 1,
                "intent": "hand the artifact to the cli",
                "from": "wagon:demo-wagon",
                "to": "system:atdd-cli",
                "artifact": "commons:manifest",
            },
        ],
    }


def test_caller_participants_are_preserved_verbatim(tmp_path):
    spec = _base()
    spec["participants"] = ["wagon:demo-wagon", "system:atdd-cli", "user:operator"]
    doc = _author(tmp_path, spec)
    assert doc["participants"] == ["wagon:demo-wagon", "system:atdd-cli", "user:operator"]


def test_non_wagon_principals_are_not_discarded(tmp_path):
    spec = _base()
    spec["participants"] = ["wagon:demo-wagon", "system:atdd-cli"]
    doc = _author(tmp_path, spec)
    assert "system:atdd-cli" in doc["participants"]


def test_participants_derived_from_wagons_when_omitted(tmp_path):
    # Today's fallback is preserved: no participants supplied -> derive wagon URNs.
    spec = _base()
    assert "participants" not in spec
    doc = _author(tmp_path, spec)
    assert doc["participants"] == ["wagon:demo-wagon"]
