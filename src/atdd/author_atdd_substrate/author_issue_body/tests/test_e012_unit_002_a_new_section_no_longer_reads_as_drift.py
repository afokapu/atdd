# URN: test:author-atdd-substrate:author-issue-body:E012-UNIT-002-a-new-section-no-longer-reads-as-drift
# Acceptance: acc:author-atdd-substrate:E012-UNIT-002-a-new-section-no-longer-reads-as-drift
# WMBT: wmbt:author-atdd-substrate:E012
# Phase: RED
# Layer: application
"""E012-UNIT-002 — adding ONE section to ONE surface must not read as drift.

The guard exists to catch a section that moved on one surface and not the others.
Today it also fires when a section is added correctly, because two of the sets it
compares are literals that cannot follow. Those are different facts and the guard
reports them identically, which is what made #1950 drop its template edit rather
than fix the instrument.

Both directions are covered here, because the two literals fail in opposite ways:

  * a new template H2 the schema does not require -> must land in the OPTIONAL set
    (this is the ``OPTIONAL_SECTIONS`` literal's failure mode)
  * a new schema-required H3 -> must land in the REQUIRED-SUBSECTION set
    (this is the ``REQUIRED_SUBSECTIONS`` literal's failure mode)

Driven through temp schema/template pairs rather than the live ones, so the test
says something about the MECHANISM instead of about today's corpus — a module-level
constant computed once at import cannot answer these questions at all, which is why
the surface under test is a function taking paths.
"""
from __future__ import annotations

import json

from ._helpers import load_issue_schema


def _get(name: str):
    from . import _helpers

    fn = getattr(_helpers, name, None)
    assert fn is not None, (
        f"_helpers.{name}() not implemented yet — #1978 Phase 1 (GREEN); a literal "
        f"cannot follow a section added to another surface."
    )
    return fn


def _pair(tmp_path, *, extra_required=(), extra_template_h2=(), required_h3s=None):
    """A (schema, template) pair with the given additions."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    schema = dict(load_issue_schema())
    required = list(schema["required"])
    if required_h3s is not None:
        required = [h for h in required if not h.startswith("### ")] + list(required_h3s)
    required += list(extra_required)
    schema["required"] = required
    schema_path = tmp_path / "issue.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    h2s = [h for h in schema["required"] if h.startswith("## ")] + list(extra_template_h2)
    lines = []
    for h in h2s:
        lines += [h, "", "(placeholder)", ""]
    for h in [h for h in schema["required"] if h.startswith("### ")]:
        lines += [h, "", "(placeholder)", ""]
    template_path = tmp_path / "PARENT-ISSUE-TEMPLATE.md"
    template_path.write_text("\n".join(lines), encoding="utf-8")
    return schema_path, template_path


def test_a_new_template_h2_the_schema_omits_is_optional(tmp_path):
    """`## Rule Wiring` is not special — it is simply the only such section today."""
    schema_path, template_path = _pair(tmp_path, extra_template_h2=["## Lab"])
    optional = _get("optional_sections")(
        schema_path=schema_path, template_path=template_path
    )
    assert "## Lab" in optional, (
        "a template H2 the schema does not require must be treated as OPTIONAL; "
        f"got {sorted(optional)}"
    )


def test_a_new_schema_required_h3_is_surfaced(tmp_path):
    """The set must follow the schema, so the guard compares like with like."""
    schema_path, _ = _pair(
        tmp_path, required_h3s=["### Graph Context", "### Mirror Across Agents", "### Hypothesis"]
    )
    subsections = _get("required_subsections")(schema_path=schema_path)
    assert "### Hypothesis" in subsections, (
        f"a newly required H3 must be surfaced from the schema; got {sorted(subsections)}"
    )


def test_neither_addition_is_reported_as_drift(tmp_path):
    """The whole point: added correctly on one surface, the guard stays silent.

    ``required_section_set`` is the set the C011 guard compares against the schema.
    With both constants derived, adding `## Lab` to the template alone leaves the two
    equal — the optional set absorbs it — and that equality is what stops a correct
    addition from being reported as a fault.
    """
    schema_path, template_path = _pair(tmp_path, extra_template_h2=["## Lab"])
    effective = _get("required_section_set")(
        schema_path=schema_path, template_path=template_path
    )
    schema_required = set(json.loads(schema_path.read_text(encoding="utf-8"))["required"])
    assert effective == schema_required, (
        "the gate's effective set must equal the schema's required set when a section "
        "was added to the template only;\n"
        f"  only in gate:   {sorted(effective - schema_required)}\n"
        f"  only in schema: {sorted(schema_required - effective)}"
    )
