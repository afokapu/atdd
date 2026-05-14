# URN: test:govern-lifecycle:issue-template-substrate-completeness:E004-INTEGRATION-002-planner-rule-binding
# Acceptance: acc:govern-lifecycle:E004-INTEGRATION-002-planner-rule-binding
# WMBT: wmbt:govern-lifecycle:E004
# Phase: GREEN
# Layer: unit
"""
Pure-logic unit tests for `check_graph_context` (#682 Phase 3).

Decoupled from the GitHub-API path so this layer runs under
`atdd validate planner --skip-api` and pinpoints regressions without
needing live gh access.
"""
from __future__ import annotations

import pytest

from atdd.planner.validators.test_issue_body_has_graph_context import (
    GRAPH_CONTEXT_PLACEHOLDER,
    _body_carries_suppression,
    check_graph_context,
)

pytestmark = [pytest.mark.planner]


def test_returns_none_when_h3_section_is_present_and_populated():
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        "**Wagon:** wagon:foo\n"
    )
    assert check_graph_context(body) is None


def test_returns_none_when_h2_section_is_present_and_populated():
    body = "## Graph Context\n\nReal content here\n"
    assert check_graph_context(body) is None


def test_flags_missing_section():
    body = "## Architecture\n\nNo graph context anywhere.\n"
    detail = check_graph_context(body)
    assert detail is not None
    assert "missing Graph Context section" in detail


def test_flags_unfilled_placeholder():
    body = (
        "## Architecture\n\n"
        "### Graph Context\n\n"
        f"{GRAPH_CONTEXT_PLACEHOLDER}\n"
    )
    detail = check_graph_context(body)
    assert detail is not None
    assert "placeholder" in detail


def test_flags_empty_body():
    assert check_graph_context("") is not None


def test_body_suppression_marker_absorbs_violation():
    rule_id = "planner.issue-body.graph-context-required"
    body_lines = [
        "## Architecture",
        "",
        "### Graph Context",
        "",
        f"# atdd:suppress({rule_id}) UNTIL=2026-12-31",
        f"{GRAPH_CONTEXT_PLACEHOLDER}",
    ]
    body = "\n".join(body_lines)
    assert _body_carries_suppression(body, rule_id) is True


def test_body_without_marker_does_not_self_suppress():
    body = "## Graph Context\n\nReal content\n"
    assert (
        _body_carries_suppression(body, "planner.issue-body.graph-context-required")
        is False
    )
