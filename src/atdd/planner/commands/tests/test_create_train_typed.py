# Purpose: create_train authors a typed train:<subject>:<slug> into a sane
# subject/category bucket + nested home (issue #1421 — retires the `t-trains`
# bucket the legacy `{tid[0]}` derivation produced for typed ids).
"""GREEN pins for typed-train authoring (`atdd author` create_train, #1421)."""
from __future__ import annotations

import yaml

import pytest

from atdd.planner.commands import author


def _typed_spec() -> dict:
    return {
        "train_id": "train:artifact-identity:migrate-with-alias",
        "title": "Migrate with alias",
        "description": "A typed train authored fresh via create_train",
        "category": "nominal",
        "themes": ["commons"],
        "wagons": ["author-artifacts"],
        "sequence": [
            {
                "step": 1,
                "intent": "do a thing",
                "from": "wagon:author-artifacts",
                "to": "system:atdd-cli",
                "artifact": "commons:plan:manifest",
            }
        ],
    }


def test_typed_train_nests_under_subject_slug(tmp_path) -> None:
    per_train = author.create_train(_typed_spec(), root=tmp_path)
    assert per_train == tmp_path / "plan" / "_trains" / "artifact-identity" / "migrate-with-alias.yaml"
    doc = yaml.safe_load(per_train.read_text(encoding="utf-8"))
    assert doc["train_id"] == "train:artifact-identity:migrate-with-alias"
    assert doc["category"] == "nominal"


def test_typed_train_buckets_by_subject_and_category_not_t_trains(tmp_path) -> None:
    author.create_train(_typed_spec(), root=tmp_path)
    registry = yaml.safe_load((tmp_path / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    trains = registry["trains"]
    assert "t-trains" not in trains, "typed id must not fall into the legacy `t-trains` bucket"
    entry = trains["artifact-identity"]["nominal"][0]
    assert entry["train_id"] == "train:artifact-identity:migrate-with-alias"
    assert entry["category"] == "nominal"
    assert entry["path"] == "plan/_trains/artifact-identity/migrate-with-alias.yaml"


def test_typed_train_defaults_category_to_nominal(tmp_path) -> None:
    spec = _typed_spec()
    del spec["category"]
    author.create_train(spec, root=tmp_path)
    registry = yaml.safe_load((tmp_path / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    assert registry["trains"]["artifact-identity"]["nominal"][0]["category"] == "nominal"


def test_invalid_category_is_rejected(tmp_path) -> None:
    spec = _typed_spec()
    spec["category"] = "bogus"
    with pytest.raises(author.AuthorInputError) as exc:
        author.create_train(spec, root=tmp_path)
    assert exc.value.field == "category"


def test_legacy_train_id_still_authors_flat(tmp_path) -> None:
    """The NNNN-slug form keeps its flat home + digit bucket during the transition."""
    spec = _typed_spec()
    spec["train_id"] = "0001-self-compliance-validate"
    del spec["category"]
    per_train = author.create_train(spec, root=tmp_path)
    assert per_train == tmp_path / "plan" / "_trains" / "0001-self-compliance-validate.yaml"
    registry = yaml.safe_load((tmp_path / "plan" / "_trains.yaml").read_text(encoding="utf-8"))
    assert "0-trains" in registry["trains"]
