# URN: test:author-atdd-substrate:author-issue-body:C011-SMOKE-001-live-drift-guard-over-real-artifacts
# Acceptance: acc:author-atdd-substrate:C011-SMOKE-001-live-drift-guard-over-real-artifacts
# WMBT: wmbt:author-atdd-substrate:C011
# Phase: SMOKE
# Layer: integration
"""C011-SMOKE-001 — the drift-guard over the real shipped artifacts (no mocks).

Loads the live issue.schema.json, the real create_issue_body, and the real coach
gate (load_required_sections() + REQUIRED_SUBSECTIONS) from the checkout and
confirms the three required-section sets are identical.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue_template import (
    REQUIRED_SUBSECTIONS,
    load_required_sections,
)

from ._helpers import get_create_issue_body, load_issue_schema, sample_spec


@pytest.mark.smoke
def test_c011_smoke_001_live_drift_guard_over_real_artifacts():
    # Real artifact 1: the shipped schema.
    schema_sections = set(load_issue_schema().get("required", []))

    # Real artifact 2: the real coach gate.
    gate_sections = set(load_required_sections()) | set(REQUIRED_SUBSECTIONS)

    # Real artifact 3: the real generator's emitted body.
    body = get_create_issue_body()(sample_spec())
    generator_sections = {s for s in (schema_sections | gate_sections) if s in body}

    assert schema_sections == gate_sections == generator_sections, (
        "drift across the real artifacts:\n"
        f"  schema:    {sorted(schema_sections)}\n"
        f"  gate:      {sorted(gate_sections)}\n"
        f"  generator: {sorted(generator_sections)}"
    )
