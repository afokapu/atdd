# URN: component:govern-lifecycle:enforcement-substrate:test_issue_body_has_graph_context:backend:domain
# Acceptance: acc:govern-lifecycle:E004-SMOKE-001-rule-blocks-empty-graph-context
# WMBT: wmbt:govern-lifecycle:E004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Purpose: Enforce that every open atdd-issue has a populated `### Graph Context` section.
"""
Planner validator: every open ATDD parent issue body must carry a populated
`### Graph Context` (or `## Graph Context`) section. The section may not be
absent, and it may not still contain the literal placeholder text the
template ships with — that placeholder is replaced at issue-creation time
by `atdd issue <slug>` (Phase 2 of #682).

Rule binding: `planner.issue-body.graph-context-required`
Convention:   src/atdd/planner/conventions/issue-body.convention.yaml

The rule's disposition is `suppress-and-clean` — issues that genuinely have
no useful graph context (infrastructure-only, docs, hotfix) can absorb the
violation by adding the marker INSIDE the issue body itself:

    # atdd:suppress(planner.issue-body.graph-context-required) UNTIL=YYYY-MM-DD

The check is a pure-logic function; the pytest test wires it to the live
github_api fetch and pipes results through `assert_disposition_satisfied`.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.utils.suppression_scanner import is_suppressed
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


pytestmark = [pytest.mark.planner, pytest.mark.github_api]


# Rule binding fails at import if the convention drifts.
_RULE_GRAPH_CONTEXT = bind_rule("planner.issue-body.graph-context-required")


# Literal placeholder string the template ships with (Phase 1 of #682).
# Kept in sync with `src/atdd/coach/commands/issue_template.py::PLACEHOLDER_STRINGS`.
GRAPH_CONTEXT_PLACEHOLDER = "(graph context will be injected at creation by atdd issue <slug>)"

# Section headings — accepted at either H2 or H3 level (template ships H3 under
# `## Architecture`, but operators may promote to H2 in some bodies).
_HEADINGS = ("### Graph Context", "## Graph Context")

# Issues created STRICTLY BEFORE this date are exempt from the rule (#682
# success criterion: "Today's already-filed issues are NOT retroactively
# flagged"). Issues created on/after this date are enforced. The cutoff is
# the day after #682 was authored (2026-05-14), so the new substrate covers
# every issue filed once the rule lands.
_RULE_CUTOFF = date(2026, 5, 15)


def check_graph_context(body: str) -> Optional[str]:
    """Return a violation detail string, or None when the body is compliant.

    Compliant means: at least one of the accepted headings is present, AND
    the body does not still contain the unfilled placeholder text.
    """
    if not body:
        return "issue body is empty"
    if not any(h in body for h in _HEADINGS):
        return f"missing Graph Context section (expected one of {list(_HEADINGS)})"
    if GRAPH_CONTEXT_PLACEHOLDER in body:
        return "Graph Context section still contains the unfilled placeholder text"
    return None


def _body_carries_suppression(body: str, rule_id: str) -> bool:
    """True when the issue body has the inline suppress marker for *rule_id*.

    Body-level suppression is checked here (not by the disposition gate)
    because GitHub issue bodies aren't files in the worktree — the gate's
    file-line scanner would never see them.
    """
    return any(is_suppressed(line, rule_id) for line in body.splitlines())


def _open_atdd_issues() -> List[Dict[str, Any]]:
    """Fetch open issues with the ``atdd-issue`` label via the REST API.

    Uses GET /repos/{owner}/{repo}/issues (REST, 0 GraphQL pts) rather than
    ``gh issue list --json`` (GraphQL, ~100 pts/call) — see issue #877.
    REST field ``created_at`` is normalised to ``createdAt`` so the cutoff
    filter is unchanged.
    """
    import json
    import subprocess
    from atdd.coach.utils.config import load_atdd_config

    repo_root = find_repo_root()
    try:
        config = load_atdd_config(repo_root)
        github_config = (config.get("github") or {})
        repo = github_config.get("repo")
        if not repo:
            pytest.skip("No github.repo configured in .atdd/config.yaml")
        r = subprocess.run(
            [
                "gh", "api",
                f"repos/{repo}/issues?labels=atdd-issue&state=open&per_page=100",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            pytest.skip(f"Cannot query GitHub issues: {r.stderr}")
        items = json.loads(r.stdout) if r.stdout else []
        # REST uses snake_case; normalise so the cutoff filter is unchanged.
        for item in items:
            if "created_at" in item and "createdAt" not in item:
                item["createdAt"] = item["created_at"]
        return items
    except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pytest.skip(f"Cannot query GitHub issues: {e}")


def _was_created_before_cutoff(created_at: Optional[str]) -> bool:
    """True when *created_at* (an ISO-8601 timestamp) precedes `_RULE_CUTOFF`."""
    if not created_at:
        return False
    try:
        # gh returns timestamps like "2026-05-14T10:30:00Z"
        when = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return when.date() < _RULE_CUTOFF


@pytest.fixture(scope="session")
def atdd_issue_bodies():
    issues = _open_atdd_issues()
    if not issues:
        pytest.skip("No open atdd-issue labeled issues found")
    return issues


def test_issue_body_has_graph_context(atdd_issue_bodies):
    """Every open atdd-issue must have a populated Graph Context section.

    `suppress-and-clean` disposition: a body containing the inline marker
    `# atdd:suppress(planner.issue-body.graph-context-required) [UNTIL=...]`
    absorbs the violation. Stale UNTIL= dates are flagged separately by
    `coach.rule-id.stale-suppression`.
    """
    rule_id = _RULE_GRAPH_CONTEXT.rule_id
    violations: List[Violation] = []

    for issue in atdd_issue_bodies:
        if _was_created_before_cutoff(issue.get("createdAt")):
            # Pre-#682 issues are exempt — the rule is forward-looking.
            continue
        body = issue.get("body") or ""
        if _body_carries_suppression(body, rule_id):
            continue
        detail = check_graph_context(body)
        if detail is None:
            continue
        number = issue.get("number")
        violations.append(Violation(
            rule_id=rule_id,
            severity=_RULE_GRAPH_CONTEXT.severity,
            location=f"github-issue#{number}:body",
            detail=f"#{number}: {detail}",
            fix_hint_ref=_RULE_GRAPH_CONTEXT.fix_hint_ref,
        ))

    assert_disposition_satisfied(
        validator_id="issue_body_has_graph_context",
        violations=violations,
    )
