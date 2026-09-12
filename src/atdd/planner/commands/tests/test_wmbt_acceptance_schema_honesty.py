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


# ---------------------------------------------------------------------------
# #1957 — two fields that read as supported and have no reader.
#
# Measured over the corpus at the time of writing (1347 acceptances, 732 plan
# files): `then.assertions[].tolerance` is carried by 0 of the 26 acceptances
# that declare `then.assertions` at all, and `signal.metrics[]` is used by 0
# acceptances — yet `threshold` was `required` on every entry of it. Neither
# field has a reader anywhere in `src/`: `metric_runner` reads `signal.metric`
# and `signal.threshold` and nothing else off `signal`.
#
# Decision 1 — DROP `tolerance`. #1925 made `signal.metric` + `signal.threshold`
#   the quantitative mechanism; a second one on the assertion leg splits the
#   grammar, and this one was never used.
# Decision 2 — DE-REQUIRE `metrics[].threshold`. `metrics[]` describes the OTel
#   signals a slice EMITS; a bar belongs to the executable half. Requiring it
#   taxed every author of a descriptive metric for a field no gate reads. It
#   stays authorable as observability metadata — it is no longer compelled.
# ---------------------------------------------------------------------------


def _assertion_item(schema):
    """The `then.assertions[]` item shape of the strict standalone object."""
    return schema["properties"]["then"]["properties"]["assertions"]["items"]


def _descriptive_metric_item(schema):
    """The `signal.metrics[]` item shape — the OTel descriptive half."""
    return schema["properties"]["signal"]["properties"]["metrics"]["items"]


def test_assertion_leg_declares_no_second_quantitative_mechanism():
    """#1957 decision 1 — `tolerance` is gone from the assertion leg.

    A shapeless `{"type": "object"}` with no inner shape and no reader
    advertises a comparability that does not exist: two teams expressing the
    same band would write it differently and no gate could reason about
    either.
    """
    a = _load("acceptance.schema.json")
    item = _assertion_item(a)
    assert "tolerance" not in item["properties"], (
        "then.assertions[].tolerance must not be declared — it is shapeless, "
        "unused across the corpus and read by nothing (#1957)"
    )
    # ...and the mechanism it duplicated is still the executable one (#1925).
    assert "threshold" in a["properties"]["signal"]["properties"], (
        "signal.threshold remains THE quantitative bar"
    )


def test_descriptive_metrics_do_not_compel_an_unread_threshold():
    """#1957 decision 2 — `metrics[].threshold` is declared but not required."""
    a = _load("acceptance.schema.json")
    item = _descriptive_metric_item(a)
    assert "threshold" not in item["required"], (
        "signal.metrics[].threshold must not be required — no reader evaluates "
        "it, so requiring it taxes the author and pays nobody (#1957)"
    )
    # what actually identifies a declared OTel metric is still compelled
    assert item["required"] == ["name", "type"], item["required"]
    # the field itself survives as observability metadata, still closed-shape
    assert "threshold" in item["properties"], (
        "threshold stays authorable on a descriptive metric — de-required, not dropped"
    )
    assert item["additionalProperties"] is False, "the metric item stays closed"


def test_schema_records_why_each_unread_affordance_was_retired():
    """The rationale lives in the schema so neither field silently returns."""
    a = _load("acceptance.schema.json")
    for shape, label in (
        (_assertion_item(a), "then.assertions[]"),
        (_descriptive_metric_item(a), "signal.metrics[]"),
    ):
        assert "#1957" in shape.get("$comment", ""), (
            f"{label} must carry a $comment naming #1957 — the decision is the "
            "only thing stopping an unread field from being re-added"
        )
