"""#1548 (absorbing #1194) — a train acceptance is authorable and validates by construction.

Three separate representations describe the same acceptance URN, and all three
had drifted apart:

* ``urn_grammar.yaml`` families.acc — the executable grammar (single source).
* ``acceptance.schema.json`` identity.urn — a static copy, because JSON Schema
  cannot reference the grammar.
* ``train.convention.yaml`` acceptances.example — the shape humans copy.

The convention's example used the identity scheme retired by #1421, and the
schema's pattern admitted only the wagon-parented shape, so the documented
artifact could not validate. These tests pin all three to each other.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

from atdd.coach.utils.graph.urn import URNGrammar
from atdd.planner.commands.author import AuthorInputError, create_acceptance, create_train


_PLANNER = Path(__file__).resolve().parents[2]
_ACCEPTANCE_SCHEMA = _PLANNER / "schemas" / "acceptance.schema.json"
_TRAIN_SCHEMA = _PLANNER / "schemas" / "train.schema.json"
_TRAIN_CONVENTION = _PLANNER / "conventions" / "train.convention.yaml"

TYPED_TRAIN_ACC = "acc:train:self-compliance:validate-lifecycle:idempotent-on-retry"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The static copy must not drift from the executable grammar
# ---------------------------------------------------------------------------


def test_acceptance_schema_urn_pattern_matches_the_grammar():
    """Byte-identical, not merely equivalent — equivalence is not checkable."""
    schema_pattern = _json(_ACCEPTANCE_SCHEMA)["properties"]["identity"]["properties"]["urn"]["pattern"]
    assert schema_pattern == URNGrammar.PATTERNS["acc"], (
        "acceptance.schema.json identity.urn has drifted from families.acc.pattern "
        "in urn_grammar.yaml; the grammar is the single source — copy it verbatim"
    )


@pytest.mark.parametrize(
    "urn",
    [
        TYPED_TRAIN_ACC,
        "acc:author-plan-substrate:E004-UNIT-002-carries-schema-required-keys",
        "acc:self-compliance:idempotent-on-retry",
        "acc:some-wagon:E001-SMOKE-001",
        "acc:train:substrate:author-artifacts:emits-a-receipt",
        # rejects
        "acc:train:self-compliance:validate-lifecycle",
        "acc:train:Self-Compliance:validate-lifecycle:x",
        "acc:UPPER:E001-UNIT-001",
        "notacc:foo:bar",
    ],
)
def test_schema_pattern_and_grammar_agree_on_every_probe(urn):
    """Same verdict from both representations, accept or reject."""
    schema_pattern = _json(_ACCEPTANCE_SCHEMA)["properties"]["identity"]["properties"]["urn"]["pattern"]
    assert bool(re.match(schema_pattern, urn)) is bool(
        URNGrammar.validate_urn(urn, "acc")
    ), f"schema and grammar disagree on {urn!r}"


# ---------------------------------------------------------------------------
# The documented example must be authorable
# ---------------------------------------------------------------------------


def _convention_example() -> dict:
    doc = yaml.safe_load(_TRAIN_CONVENTION.read_text(encoding="utf-8"))
    return yaml.safe_load(doc["acceptances"]["example"])["acceptances"][0]


def test_convention_example_urn_is_grammar_valid():
    """The exact string a human copies out of the convention must validate.

    This is the #1548 defect in one assertion: the example was
    `acc:0001-self-compliance-validate:idempotent-on-retry` — the scheme retired
    by #1421 — so following the documentation produced an invalid artifact.
    """
    urn = _convention_example()["identity"]["urn"]
    assert URNGrammar.validate_grammar(urn) is True


def test_convention_example_is_parented_by_a_real_typed_train():
    """The example's parent must itself be a valid typed train identity."""
    urn = _convention_example()["identity"]["urn"]
    parsed = URNGrammar.parse_urn(urn)
    assert parsed["parent_kind"] == "train"
    assert URNGrammar.validate_grammar(parsed["train_id"]) is True


def test_convention_example_validates_against_the_train_schema():
    """The example must satisfy the acceptance definition trains actually use."""
    schema = _json(_TRAIN_SCHEMA)
    validator = jsonschema.Draft7Validator(
        {**schema, "$ref": "#/definitions/acceptance"}
    )
    errors = sorted(validator.iter_errors(_convention_example()), key=str)
    assert errors == [], [f"{list(e.absolute_path)}: {e.message}" for e in errors]


# ---------------------------------------------------------------------------
# The writer's own output validates against the writer's own schema (#1194)
# ---------------------------------------------------------------------------


def _train_spec_with_acceptance() -> dict:
    return {
        "train_id": "train:self-compliance:validate-lifecycle",
        "title": "Validate lifecycle",
        "description": "a typed train carrying a typed train acceptance",
        "themes": ["commons"],
        "participants": ["wagon:self-compliance"],
        "sequence": [
            {
                "step": 1,
                "intent": "run the lifecycle end to end",
                "from": "wagon:self-compliance",
                "to": "system:atdd-cli",
                "artifact": "commons:manifest",
            },
        ],
        "acceptances": [_convention_example()],
    }


def test_authored_train_carrying_a_typed_acceptance_validates(tmp_path):
    """create_train's output — acceptance and all — validates by construction."""
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")

    per_train = create_train(_train_spec_with_acceptance(), root=tmp_path)
    doc = yaml.safe_load(per_train.read_text(encoding="utf-8"))

    assert doc["acceptances"][0]["identity"]["urn"] == TYPED_TRAIN_ACC
    errors = sorted(
        jsonschema.Draft7Validator(_json(_TRAIN_SCHEMA)).iter_errors(doc), key=str
    )
    assert errors == [], [f"{list(e.absolute_path)}: {e.message}" for e in errors]


def test_typed_train_lands_at_its_subject_nested_home(tmp_path):
    """The nested home is what made train acceptances invisible to the walker."""
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text("trains: {}\n", encoding="utf-8")

    per_train = create_train(_train_spec_with_acceptance(), root=tmp_path)
    assert per_train.relative_to(plan) == Path(
        "_trains/self-compliance/validate-lifecycle.yaml"
    )


# ---------------------------------------------------------------------------
# create_acceptance now rejects what its schema rejects (#1194)
# ---------------------------------------------------------------------------


def _seed_wmbt(tmp_path: Path) -> Path:
    p = tmp_path / "plan" / "demo_wagon" / "E001.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        'urn: "wmbt:demo-wagon:E001"\nacceptances: []\n', encoding="utf-8"
    )
    return p


def _valid_block() -> dict:
    return {
        "identity": {
            "urn": "acc:demo-wagon:E001-UNIT-001-x",
            "id": "AC-UNIT-001",
            "purpose": "the thing behaves as specified",
            "phase": "GREEN",
        },
        "harness": {"type": "unit", "category": "backend"},
        "given": {"abstract": ["a seeded WMBT"]},
        "when": {"abstract": "create_acceptance is invoked with this block"},
        "then": {"abstract": ["the block is appended"]},
    }


def test_valid_block_is_written(tmp_path):
    wmbt = _seed_wmbt(tmp_path)
    create_acceptance("wmbt:demo-wagon:E001", _valid_block(), root=tmp_path)
    doc = yaml.safe_load(wmbt.read_text(encoding="utf-8"))
    assert doc["acceptances"][0]["identity"]["urn"] == "acc:demo-wagon:E001-UNIT-001-x"


def test_schema_invalid_block_is_rejected(tmp_path):
    """FAULT INJECTION: a malformed URN must be refused."""
    wmbt = _seed_wmbt(tmp_path)
    block = _valid_block()
    block["identity"]["urn"] = "acc:demo-wagon:NOT-A-VALID-ACCEPTANCE-URN"

    with pytest.raises(AuthorInputError, match="not schema-valid"):
        create_acceptance("wmbt:demo-wagon:E001", block, root=tmp_path)


def test_rejected_block_leaves_the_target_file_untouched(tmp_path):
    """The schema gate runs BEFORE the write, so a refusal is not a partial write."""
    wmbt = _seed_wmbt(tmp_path)
    before = wmbt.read_text(encoding="utf-8")

    block = _valid_block()
    del block["harness"]  # embedded_acceptance requires it
    with pytest.raises(AuthorInputError):
        create_acceptance("wmbt:demo-wagon:E001", block, root=tmp_path)

    assert wmbt.read_text(encoding="utf-8") == before
