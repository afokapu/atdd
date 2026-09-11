# URN: test:atdd-plan:reconcile-wmbt-schema:schema-honesty
# Acceptance: wmbt.schema.json + acceptance.schema.json honestly describe the real WMBT file shape
# Issue: #760
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""#760 — the WMBT + acceptance schemas are internally honest about the real
corpus, WITHOUT changing what passes or fails (the schemas are not applied as
file-level gates). Asserts:
  - wmbt.schema.json declares `acceptances` (so it no longer contradicts every
    real WMBT file), keeps `additionalProperties: false` exactly, and carries
    the not-file-applied $comment.
  - acceptance.schema.json defines `embedded_acceptance` (the lighter embedded
    shape) and wmbt.schema's acceptances items $ref it.
  - a real plan/ embedded acceptance validates against `embedded_acceptance`.
  - the strict standalone acceptance object still REJECTS that same embedded
    acceptance (documenting WHY it is not applied as a file gate).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

_SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
_PLAN = Path(__file__).resolve().parents[4].parent / "plan"  # repo-root/plan


def _load(name):
    return json.loads((_SCHEMAS / name).read_text(encoding="utf-8"))


def test_wmbt_schema_is_internally_honest():
    w = _load("wmbt.schema.json")
    assert "acceptances" in w["properties"], "wmbt.schema must declare `acceptances`"
    assert w["additionalProperties"] is False, "additionalProperties:false must be retained unchanged"
    assert "$comment" in w and "not" in w["$comment"].lower(), "must record it is not file-applied"
    assert w["properties"]["acceptances"]["items"]["$ref"].endswith("embedded_acceptance")


def test_acceptance_schema_defines_embedded_shape():
    a = _load("acceptance.schema.json")
    assert "embedded_acceptance" in a.get("definitions", {})
    emb = a["definitions"]["embedded_acceptance"]
    assert set(["identity", "given", "when", "then"]).issubset(set(emb["required"]))
    # `harness` is deliberately NOT in `required` (#1925): spec §4.3 makes an
    # acceptance measurable by EITHER harness.type OR signal.metric+threshold,
    # and requiring `harness` made the second half unauthorable.
    assert "harness" not in emb["required"]


def _measurability_anyof(shape):
    """The §4.3 OR as the schema encodes it: harness, or metric+threshold."""
    branches = shape.get("anyOf")
    assert branches, "the measurability OR must be encoded as anyOf"
    return {
        "harness": any(b.get("required") == ["harness"] for b in branches),
        "metric": any(
            b.get("required") == ["signal"]
            and b.get("properties", {}).get("signal", {}).get("required")
            == ["metric", "threshold"]
            for b in branches
        ),
    }


def test_both_shapes_encode_the_measurability_or():
    """Spec §4.3 is schema structure, not prose, in BOTH shapes (#1925)."""
    a = _load("acceptance.schema.json")
    for shape in (a, a["definitions"]["embedded_acceptance"]):
        got = _measurability_anyof(shape)
        assert got["harness"], "missing the harness branch of the §4.3 OR"
        assert got["metric"], "missing the signal.metric+threshold branch of the §4.3 OR"


def test_signal_declares_the_executable_grammar_the_runtime_consumes():
    """`signal.metric`/`threshold` is what metric_runner reads; the schema
    forbade it outright before #1925 via additionalProperties:false."""
    a = _load("acceptance.schema.json")
    sig = a["properties"]["signal"]
    assert sig["additionalProperties"] is False, "signal stays closed"
    assert "metric" in sig["properties"], "signal.metric must be declared"
    assert "threshold" in sig["properties"], "signal.threshold must be declared"
    # `threshold: 0` and `threshold: false` are meaningful bars, not absences.
    assert set(sig["properties"]["threshold"]["type"]) >= {"number", "boolean"}
    # the descriptive OTel half is untouched and still present
    assert "metrics" in sig["properties"]


def _first_real_embedded_acceptance():
    for f in sorted(glob.glob(str(_PLAN / "define_plans" / "*.yaml"))):
        doc = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("acceptances"):
            return doc["acceptances"][0]
    return None


def test_real_embedded_acceptance_matches_embedded_definition():
    acc = _first_real_embedded_acceptance()
    assert acc is not None, "expected a real define_plans WMBT with acceptances"
    a = _load("acceptance.schema.json")
    # resolve the embedded_acceptance definition with the local $ref base
    schema = {"$ref": "#/definitions/embedded_acceptance", "definitions": a["definitions"], "properties": a["properties"]}
    errs = sorted(Draft7Validator(schema).iter_errors(acc), key=lambda e: list(e.path))
    assert not errs, f"real embedded acceptance should match embedded_acceptance: {[e.message for e in errs[:3]]}"


def test_strict_standalone_schema_would_reject_embedded_documenting_why_not_a_gate():
    acc = _first_real_embedded_acceptance()
    a = _load("acceptance.schema.json")
    # the strict root object requires signal/when.action/then.assertions/metadata.wagon
    errs = list(Draft7Validator(a).iter_errors(acc))
    assert errs, "the strict standalone schema MUST reject the embedded shape — this is why it is not file-applied (#760)"
