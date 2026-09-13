# URN: test:author-atdd-substrate:author-issue-body:E012-UNIT-001-helper-derives-both-constants
# Acceptance: acc:author-atdd-substrate:E012-UNIT-001-helper-derives-both-constants
# WMBT: wmbt:author-atdd-substrate:E012
# Phase: RED
# Layer: application
"""E012-UNIT-001 — the drift guard's own helper must DERIVE, not restate.

#1901 gave the section contract ONE source and converted ``issue_template.py``'s two
hand-maintained constants into derivations, recording why: "they were not policy.
They were the drift, written down." The same two constants still exist, typed out, in
the helper that IS the guard's instrument — so #1901 fixed the reader it was looking
at and left the one that watches it.

MEASURED COST (#1950's lab). Adding one section failed C011 twice, for two different
hardcoded reasons, and neither was drift:

  * `## Lab` + 4 H3s in the schema, template untouched -> both C011 tests fail,
    because ``REQUIRED_SUBSECTIONS`` is a stale literal.
  * `## Lab` in the template, schema untouched -> both C011 tests fail AND K002
    fails, because ``OPTIONAL_SECTIONS`` is a literal that cannot contain it.
  * both derived -> 38/38 pass, nothing else changed.

BOUNDARY, UNCHANGED. ``author-atdd-substrate`` is commons-themed, so this tree may
not import ``atdd.coach`` (``planner.theme.commons-coach-boundary``, #970). That is
exactly why the helper reconstructs the gate's view by hand — and it need not: it
already reads ``issue.schema.json`` off disk. Deriving honours the boundary; the
last test here pins that it is still honoured afterwards.
"""
from __future__ import annotations

import json
from pathlib import Path

from ._helpers import ISSUE_SCHEMA_PATH, TEMPLATE_PATH

_HELPERS_SOURCE = Path(__file__).parent / "_helpers.py"

#: Section headings that must not appear as literals in the helper once it derives.
#: Every one of these is declared by ``issue.schema.json`` or shown by the template,
#: so a literal here is a second source for a fact that already has one.
_MUST_NOT_BE_TYPED_OUT = (
    '"### Graph Context"',
    '"### Mirror Across Agents"',
    '"## Rule Wiring"',
)


def _get(name: str):
    """A derivation function under test, or fail naming the phase that lands it."""
    from . import _helpers

    fn = getattr(_helpers, name, None)
    assert fn is not None, (
        f"_helpers.{name}() not implemented yet — #1978 Phase 1 (GREEN). The helper "
        f"still types out the set it should read from issue.schema.json."
    )
    return fn


def test_required_subsections_are_derived_from_the_schema():
    """The H3 set equals the schema's required `### ` headings — not a typed tuple."""
    schema = json.loads(ISSUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    expected = tuple(h for h in schema.get("required", []) if h.startswith("### "))
    assert set(_get("required_subsections")(schema_path=ISSUE_SCHEMA_PATH)) == set(expected)


def test_optional_sections_are_derived_as_template_h2s_the_schema_omits():
    """Mirrors ``issue_template._optional_sections()`` — the production reference."""
    schema = json.loads(ISSUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema.get("required", []))
    template_h2 = [
        line.rstrip()
        for line in TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    ]
    expected = {h for h in template_h2 if h not in required}
    got = _get("optional_sections")(
        schema_path=ISSUE_SCHEMA_PATH, template_path=TEMPLATE_PATH
    )
    assert set(got) == expected, (
        f"optional sections must be the template H2s the schema does not require; "
        f"expected {sorted(expected)}, got {sorted(got)}"
    )


def test_no_section_heading_is_typed_out_in_the_helper():
    """The literals themselves are the defect, so their absence is the fix."""
    source = _HELPERS_SOURCE.read_text(encoding="utf-8")
    typed_out = [lit for lit in _MUST_NOT_BE_TYPED_OUT if lit in source]
    assert typed_out == [], (
        f"_helpers.py still types out section headings {typed_out} that "
        f"issue.schema.json and PARENT-ISSUE-TEMPLATE.md already declare — the "
        f"second source is what makes a new section read as drift"
    )


def test_the_helper_still_imports_nothing_from_atdd_coach():
    """Deriving must not be achieved by crossing the commons-coach boundary (#970)."""
    source = _HELPERS_SOURCE.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if "atdd.coach" in line and line.strip().startswith(("import ", "from "))
    ]
    assert offenders == [], (
        f"_helpers.py must not import atdd.coach (planner.theme.commons-coach-boundary, "
        f"#970); found {offenders}. Read issue.schema.json off disk instead."
    )
