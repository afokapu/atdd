# URN: component:govern-lifecycle:enforcement-substrate:test_wagonless_graph_context_compliance:backend:domain
# Runtime: python
# Purpose: A wagon-less issue's graph-context state (the sentinel atdd issue injects when
#          there is no wagon) MUST satisfy the graph-context-required validator (#928).
"""
Cross-module guarantee: ``atdd issue``'s wagon-less Graph Context output is
validator-compliant (#928).

The recurrence: a tracking issue with no wagon in ``plan/`` ends up with the
``GRAPH_CONTEXT_UNAVAILABLE`` sentinel; if the
``planner.issue-body.graph-context-required`` validator rejected it, that one
issue would block EVERY PR's CI repo-wide (this session: #933/#935 grooming +
a blocked #934). These tests bind the two modules so wagon-less issues are
compliant **by construction** and the two halves can't silently drift:

  * the validator MUST reject a raw, never-injected placeholder and a missing
    heading (the genuine "operator forgot" failures), AND
  * the validator MUST accept the ``GRAPH_CONTEXT_UNAVAILABLE`` sentinel that
    ``atdd issue`` injects for a wagon-less issue (the honest "no wagon yet"
    state — not a violation).
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.issue import (
    GRAPH_CONTEXT_PLACEHOLDER,
    GRAPH_CONTEXT_UNAVAILABLE,
)
from atdd.planner.validators.test_issue_body_has_graph_context import (
    check_graph_context,
)

pytestmark = [pytest.mark.coach]

_HEADING = "### Graph Context"


def _body(section_text: str, *, with_heading: bool = True) -> str:
    head = f"{_HEADING}\n\n" if with_heading else ""
    return f"## Issue Metadata\n\n| Field | Value |\n\n{head}{section_text}\n\n## Scope\n"


def test_validator_rejects_raw_uninjected_placeholder():
    """The never-injected template placeholder is a genuine violation."""
    assert check_graph_context(_body(GRAPH_CONTEXT_PLACEHOLDER)) is not None


def test_validator_rejects_missing_heading():
    assert check_graph_context(_body("anything", with_heading=False)) is not None


def test_validator_accepts_wagonless_unavailable_sentinel():
    """THE guarantee: the sentinel atdd issue injects for a wagon-less issue is
    compliant — a wagon-less tracking issue never blocks CI on this rule."""
    assert check_graph_context(_body(GRAPH_CONTEXT_UNAVAILABLE)) is None


def test_unavailable_sentinel_is_not_the_rejected_placeholder():
    """Guard the binding: the two sentinels must stay distinct, else the
    'unavailable' state would be misread as the rejected raw placeholder."""
    assert GRAPH_CONTEXT_UNAVAILABLE != GRAPH_CONTEXT_PLACEHOLDER
    assert GRAPH_CONTEXT_PLACEHOLDER not in GRAPH_CONTEXT_UNAVAILABLE
