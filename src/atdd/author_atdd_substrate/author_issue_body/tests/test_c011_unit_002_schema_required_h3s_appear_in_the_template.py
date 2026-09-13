# URN: test:author-atdd-substrate:author-issue-body:C011-UNIT-002-schema-required-h3s-appear-in-the-template
# Acceptance: acc:author-atdd-substrate:C011-UNIT-002-schema-required-h3s-appear-in-the-template
# WMBT: wmbt:author-atdd-substrate:C011
# Phase: RED
# Layer: application
"""C011-UNIT-002 — the guard's third surface, for SUBSECTIONS.

THE DEFECT THIS PINS (#1978). The C011 guard is named tri-directional and compares
two surfaces where subsections are concerned. Every template scan is written

    line.startswith("## ") and not line.startswith("### ")

at all three sites (``issue_template.py`` :123, :203, :234), so the template's H3
headings have never been read by anything. Measured: a mandatory H3 declared by
``issue.schema.json``, emitted by ``create_issue_body``, and absent from
``PARENT-ISSUE-TEMPLATE.md`` is reported as no drift at all — both C011 tests pass
in 0.15s. The consequence is not cosmetic: an author working from the human
template is held to a section the template never shows them.

RED, and it must stay red until the arm exists. The capability under test —
``template_missing_required_subsections`` — is not implemented, so this test fails
by ``AssertionError`` naming the phase rather than by a vacuous ``assert False``.
It exercises the eventual public surface exactly as the sibling RED tests in this
tree do (see ``_helpers.get_validate_issue_body``).

TODAY'S CORPUS PASSES THE NEW ARM. The schema requires ``### Graph Context`` and
``### Mirror Across Agents``; both are in the template (lines 51 and 55). So
landing the assertion clears no backlog and breaks no existing artifact — the only
thing it changes is that the next mandatory subsection cannot go missing quietly.
"""
from __future__ import annotations

import json

from ._helpers import ISSUE_SCHEMA_PATH, TEMPLATE_PATH, load_issue_schema


def _get_template_missing_required_subsections():
    """The arm under test, or fail naming the phase that lands it."""
    from . import _helpers

    fn = getattr(_helpers, "template_missing_required_subsections", None)
    assert fn is not None, (
        "_helpers.template_missing_required_subsections not implemented yet — "
        "#1978 Phase 2 (GREEN). The guard cannot see a schema-required H3 that is "
        "missing from PARENT-ISSUE-TEMPLATE.md until this arm exists."
    )
    return fn


def _write_pair(tmp_path, required_h3s: list[str], template_h3s: list[str]):
    """A (schema, template) pair on disk declaring/showing the given H3s."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    schema = dict(load_issue_schema())
    schema["required"] = [h for h in schema["required"] if not h.startswith("### ")] + required_h3s
    schema_path = tmp_path / "issue.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    body = ["## Architecture", ""]
    for h in template_h3s:
        body += [h, "", "(placeholder)", ""]
    template_path = tmp_path / "PARENT-ISSUE-TEMPLATE.md"
    template_path.write_text("\n".join(body), encoding="utf-8")
    return schema_path, template_path


def test_todays_required_h3s_are_all_present_in_the_template():
    """The live pair satisfies the new arm, so it lands with nothing to clean up."""
    missing = _get_template_missing_required_subsections()(
        schema_path=ISSUE_SCHEMA_PATH, template_path=TEMPLATE_PATH
    )
    assert missing == [], (
        f"schema-required subsections absent from PARENT-ISSUE-TEMPLATE.md: {missing}"
    )


def test_a_schema_required_h3_absent_from_the_template_is_reported(tmp_path):
    """The case the guard is blind to today — declared and emitted, but not shown."""
    fn = _get_template_missing_required_subsections()
    schema_path, template_path = _write_pair(
        tmp_path,
        required_h3s=["### Graph Context", "### Bogus Subsection"],
        template_h3s=["### Graph Context"],
    )
    missing = fn(schema_path=schema_path, template_path=template_path)
    assert missing == ["### Bogus Subsection"], (
        "a schema-required H3 missing from the template must be reported; "
        f"got {missing!r}"
    )


def test_the_template_scan_reads_h3_headings(tmp_path):
    """Not a restatement of the above: it pins the CAUSE, not just the symptom.

    Every template scan in the toolkit excludes `### ` by construction. An
    implementation that satisfied the case above by reading the schema twice, or by
    string-matching the body, would leave the cause in place. So assert the arm
    actually SEES a template H3 — present here, absent there, different answers.
    """
    fn = _get_template_missing_required_subsections()
    shown = _write_pair(tmp_path / "a", required_h3s=["### Setup"], template_h3s=["### Setup"])
    hidden = _write_pair(tmp_path / "b", required_h3s=["### Setup"], template_h3s=[])

    assert fn(schema_path=shown[0], template_path=shown[1]) == []
    assert fn(schema_path=hidden[0], template_path=hidden[1]) == ["### Setup"]
