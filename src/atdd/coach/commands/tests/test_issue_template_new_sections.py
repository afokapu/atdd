# URN: test:govern-lifecycle:issue-template-substrate-completeness:E004-UNIT-001-template-carries-new-sections
# Acceptance: acc:govern-lifecycle:E004-UNIT-001-template-carries-new-sections
# Acceptance: acc:govern-lifecycle:E004-UNIT-002-check-body-sections-enforces-subsections
# Acceptance: acc:govern-lifecycle:E004-UNIT-003-check-placeholders-ignores-rule-wiring
# WMBT: wmbt:govern-lifecycle:E004
# Phase: GREEN
# Layer: unit
"""
Unit coverage for the new template sections introduced by #682:
  - `### Graph Context`        (mandatory H3 under `## Architecture`)
  - `### Mirror Across Agents` (mandatory H3 under `## Architecture`)
  - `## Rule Wiring`           (optional top-level H2)

Asserts:
  * The literal section headings exist in PARENT-ISSUE-TEMPLATE.md.
  * `check_body_sections` flags absent mandatory subsections.
  * `check_body_sections` does NOT flag a missing `## Rule Wiring` (OPTIONAL).
  * `check_placeholders` ignores placeholder text inside OPTIONAL sections so
    authors who don't introduce new rules can leave Rule Wiring scaffolded.
  * The Graph Context placeholder string is registered for the planner rule.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.issue_template import (
    OPTIONAL_SECTIONS,
    PLACEHOLDER_STRINGS,
    REQUIRED_SUBSECTIONS,
    TEMPLATE_PATH,
    check_body_sections,
    check_placeholders,
    load_required_sections,
)

pytestmark = [pytest.mark.platform]


GRAPH_CONTEXT_PLACEHOLDER = "(graph context will be injected at creation by atdd issue <slug>)"


# ---------------------------------------------------------------------------
# Template file contains the new sections
# ---------------------------------------------------------------------------


def test_template_file_contains_graph_context_subsection():
    body = TEMPLATE_PATH.read_text()
    assert "### Graph Context" in body
    assert GRAPH_CONTEXT_PLACEHOLDER in body


def test_template_file_contains_mirror_across_agents_subsection():
    body = TEMPLATE_PATH.read_text()
    assert "### Mirror Across Agents" in body


def test_template_file_contains_rule_wiring_section():
    body = TEMPLATE_PATH.read_text()
    assert "## Rule Wiring" in body


# ---------------------------------------------------------------------------
# REQUIRED_SUBSECTIONS + OPTIONAL_SECTIONS contracts
# ---------------------------------------------------------------------------


def test_required_subsections_lists_graph_context_and_mirror():
    assert "### Graph Context" in REQUIRED_SUBSECTIONS
    assert "### Mirror Across Agents" in REQUIRED_SUBSECTIONS


def test_optional_sections_lists_rule_wiring():
    assert "## Rule Wiring" in OPTIONAL_SECTIONS


# ---------------------------------------------------------------------------
# check_body_sections enforces mandatory subsections
# ---------------------------------------------------------------------------


def _body_with_all_h2(extra: str = "") -> str:
    """Synthesize a body that has every H2 from the template, plus *extra*."""
    sections = [f"{s}\n\nreal content\n" for s in load_required_sections()]
    return "\n\n".join(sections) + ("\n\n" + extra if extra else "")


def test_check_body_sections_flags_missing_graph_context_subsection():
    # All H2s present, but no `### Graph Context` anywhere.
    body = _body_with_all_h2(extra="### Mirror Across Agents\n\nreal content\n")
    missing = check_body_sections(body)
    assert "### Graph Context" in missing
    assert "### Mirror Across Agents" not in missing


def test_check_body_sections_flags_missing_mirror_across_agents_subsection():
    body = _body_with_all_h2(extra="### Graph Context\n\nreal content\n")
    missing = check_body_sections(body)
    assert "### Mirror Across Agents" in missing
    assert "### Graph Context" not in missing


def test_check_body_sections_clean_when_both_subsections_present():
    extras = "\n\n".join(f"{s}\n\nreal content\n" for s in REQUIRED_SUBSECTIONS)
    body = _body_with_all_h2(extra=extras)
    missing = check_body_sections(body)
    assert "### Graph Context" not in missing
    assert "### Mirror Across Agents" not in missing


# ---------------------------------------------------------------------------
# OPTIONAL: ## Rule Wiring is never flagged as missing
# ---------------------------------------------------------------------------


def test_check_body_sections_does_not_require_rule_wiring():
    """A body that omits `## Rule Wiring` entirely is still compliant."""
    # Build a body with every required H2 EXCEPT Rule Wiring + required H3s.
    h2s = [s for s in load_required_sections() if s != "## Rule Wiring"]
    body_parts = [f"{s}\n\nreal content\n" for s in h2s]
    body_parts.extend(f"{s}\n\nreal content\n" for s in REQUIRED_SUBSECTIONS)
    body = "\n\n".join(body_parts)
    missing = check_body_sections(body)
    assert "## Rule Wiring" not in missing


def test_check_placeholders_ignores_unfilled_rule_wiring_scaffold():
    """Authors who don't introduce new rules may leave Rule Wiring placeholders intact."""
    body = (
        "## Issue Metadata\n\nreal content\n\n"
        "## Rule Wiring\n\n"
        "(OPTIONAL — fill in only when this issue introduces new convention rules.)\n\n"
        "| (rule_id) | (1-5) | (strict|suppress-and-clean|advisory|documentation-only) "
        "| (validator module::function) | (recipe or convention pointer) |\n\n"
        "## Notes\n\nreal content\n"
    )
    hits = check_placeholders(body)
    sections = {h[0] for h in hits}
    assert "## Rule Wiring" not in sections


# ---------------------------------------------------------------------------
# PLACEHOLDER_STRINGS registers the Graph Context literal
# ---------------------------------------------------------------------------


def test_graph_context_placeholder_is_registered():
    """The literal placeholder string is in PLACEHOLDER_STRINGS so
    check_placeholders() flags an issue body that never resolved it.
    The planner rule `planner.issue-body.graph-context-required` re-uses
    the same string.
    """
    assert GRAPH_CONTEXT_PLACEHOLDER in PLACEHOLDER_STRINGS


def test_check_placeholders_flags_graph_context_when_unfilled():
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        f"{GRAPH_CONTEXT_PLACEHOLDER}\n\n"
        "## Notes\n\nreal notes\n"
    )
    hits = check_placeholders(body)
    flagged = {(h[0], h[1]) for h in hits}
    assert ("## Architecture", GRAPH_CONTEXT_PLACEHOLDER) in flagged
