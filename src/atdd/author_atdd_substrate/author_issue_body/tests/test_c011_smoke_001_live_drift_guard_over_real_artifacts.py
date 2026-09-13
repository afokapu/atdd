# URN: test:author-atdd-substrate:author-issue-body:C011-SMOKE-001-live-drift-guard-over-real-artifacts
# Acceptance: acc:author-atdd-substrate:C011-SMOKE-001-live-drift-guard-over-real-artifacts
# WMBT: wmbt:author-atdd-substrate:C011
# Phase: SMOKE
# Layer: integration
"""C011-SMOKE-001 — the drift-guard over the real shipped artifacts (no mocks).

Loads the live issue.schema.json, the real create_issue_body, and the real coach
gate (load_required_sections() + REQUIRED_SUBSECTIONS) from the checkout and
confirms the three required-section sets are identical.

Carries the #1978 subsection arm too, over the shipped artifacts: every H3 the
schema requires must appear in the real PARENT-ISSUE-TEMPLATE.md. Before that arm
existed the template was the one surface this "tri-directional" guard never
compared for subsections.
"""
from __future__ import annotations

import pytest

from ._helpers import (
    get_create_issue_body,
    load_issue_schema,
    required_section_set,
    sample_spec,
    template_missing_required_subsections,
)


@pytest.mark.smoke
def test_c011_smoke_001_live_drift_guard_over_real_artifacts():
    # Real artifact 1: the shipped schema.
    schema_sections = set(load_issue_schema().get("required", []))

    # Real artifact 2: the real coach gate's required-section set (read from
    # PARENT-ISSUE-TEMPLATE.md, the source load_required_sections() parses).
    gate_sections = required_section_set()

    # Real artifact 3: the real generator's emitted body.
    body = get_create_issue_body()(sample_spec())
    generator_sections = {s for s in (schema_sections | gate_sections) if s in body}

    assert schema_sections == gate_sections == generator_sections, (
        "drift across the real artifacts:\n"
        f"  schema:    {sorted(schema_sections)}\n"
        f"  gate:      {sorted(gate_sections)}\n"
        f"  generator: {sorted(generator_sections)}"
    )

    # Real artifact 2 again, for SUBSECTIONS: the template must SHOW every H3 the
    # schema demands, not merely agree about H2s (#1978).
    missing_from_template = template_missing_required_subsections()
    assert missing_from_template == [], (
        f"schema-required subsections missing from the shipped template: "
        f"{missing_from_template}"
    )
