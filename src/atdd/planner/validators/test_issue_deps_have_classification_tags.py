# URN: component:dispatch-ux-defaults-and-primer:session-template-dep-classification:test_issue_deps_have_classification_tags:backend:domain
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y004-UNIT-007-planner-validator-flags-bare-deps
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y004
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Purpose: Enforce that every open atdd-issue has all dependency entries classified with a tag.
"""
Planner validator: every open ATDD parent issue body must have classification
tags on all `### Dependencies` entries. A bare `- #N` without `(prereq)`,
`(merged)`, `(sibling)`, or `(parallel)` causes session-template to include the
dep in the merge-wait loop unconditionally — breaking dispatch for sibling issues.

Rule binding: `planner.issue-body.dependency-entries-must-be-classified`
Convention:   src/atdd/planner/conventions/issue-body.convention.yaml

Disposition: warn-and-log — violations are surfaced but do not block CI.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied

pytestmark = [pytest.mark.planner, pytest.mark.github_api]

_RULE = bind_rule("planner.issue-body.dependency-entries-must-be-classified")

# Issues filed before this date are exempt (rule is forward-looking from #831).
_RULE_CUTOFF = date(2026, 5, 21)

_DEP_NUMBER = re.compile(r"^\s*-\s+#(\d+)")
_CLASSIFIED_TAGS = re.compile(
    r"\(\s*(?:prereq|merged|sibling|parallel)\s*\)", re.IGNORECASE
)


def check_dep_classification(body: str) -> Optional[str]:
    """Return a violation detail string for the first bare dep found, or None."""
    in_deps = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("#").strip()
            if heading == "Dependencies":
                in_deps = True
                continue
            if in_deps and level <= 3:
                break
        if not in_deps:
            continue
        if _DEP_NUMBER.match(line) and not _CLASSIFIED_TAGS.search(line):
            m = _DEP_NUMBER.match(line)
            return f"bare dep #{m.group(1)} — add (prereq), (merged), (sibling), or (parallel) tag"
    return None


# ---------------------------------------------------------------------------
# Pure-logic unit tests (no github_api mark — run in all environments)
# ---------------------------------------------------------------------------

class TestCheckDepClassificationUnit:
    pytestmark = [pytest.mark.platform]

    def test_compliant_prereq_tag(self):
        body = "### Dependencies\n\n- #10 (prereq)\n"
        assert check_dep_classification(body) is None

    def test_compliant_merged_tag(self):
        body = "### Dependencies\n\n- #10 (merged)\n"
        assert check_dep_classification(body) is None

    def test_compliant_sibling_tag(self):
        body = "### Dependencies\n\n- #10 (sibling)\n"
        assert check_dep_classification(body) is None

    def test_compliant_parallel_tag(self):
        body = "### Dependencies\n\n- #10 (parallel)\n"
        assert check_dep_classification(body) is None

    def test_bare_entry_returns_violation_detail(self):
        body = "### Dependencies\n\n- #100\n"
        result = check_dep_classification(body)
        assert result is not None
        assert "100" in result

    def test_bare_entry_with_description_still_flagged(self):
        body = "### Dependencies\n\n- #200 — shipped infra\n"
        result = check_dep_classification(body)
        assert result is not None

    def test_no_deps_section_returns_none(self):
        body = "## Scope\n\nNo dependencies.\n"
        assert check_dep_classification(body) is None

    def test_none_literal_in_deps_returns_none(self):
        body = "### Dependencies\n\nNone — small targeted fix.\n"
        assert check_dep_classification(body) is None

    def test_tags_case_insensitive(self):
        body = "### Dependencies\n\n- #55 (SIBLING)\n"
        assert check_dep_classification(body) is None

    def test_extended_tag_sibling_open_is_compliant(self):
        """(sibling, open) counts as classified."""
        body = "### Dependencies\n\n- **#829** (sibling, open) — desc\n"
        assert check_dep_classification(body) is None

    def test_prose_sibling_without_parens_is_flagged(self):
        """'#824 — sibling issue' has no parenthetical tag — flagged."""
        body = "### Dependencies\n\n- #824 — sibling issue that wires the actual loop\n"
        result = check_dep_classification(body)
        assert result is not None
        assert "824" in result


# ---------------------------------------------------------------------------
# Live GitHub integration (github_api mark — skipped without ATDD_RUN_SMOKE)
# ---------------------------------------------------------------------------

def _open_atdd_issues() -> List[Dict[str, Any]]:
    from atdd.coach.github import GitHubClient
    from atdd.coach.utils.config import load_atdd_config
    import json

    repo_root = find_repo_root()
    try:
        config = load_atdd_config(repo_root)
        github_config = config.get("github") or {}
        repo = github_config.get("repo")
        if not repo:
            pytest.skip("No github.repo configured in .atdd/config.yaml")
        client = GitHubClient(repo=repo)
        output = client._run_gh([
            "issue", "list",
            "--repo", repo,
            "--label", "atdd-issue",
            "--state", "open",
            "--json", "number,title,labels,state,body,createdAt",
            "--limit", "100",
        ])
        return json.loads(output) if output else []
    except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pytest.skip(f"Cannot query GitHub issues: {e}")


def _was_created_before_cutoff(created_at: Optional[str]) -> bool:
    if not created_at:
        return False
    try:
        when = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return when.date() < _RULE_CUTOFF


@pytest.fixture(scope="session")
def atdd_issue_bodies_for_dep_check():
    issues = _open_atdd_issues()
    if not issues:
        pytest.skip("No open atdd-issue labeled issues found")
    return issues


def test_issue_deps_have_classification_tags(atdd_issue_bodies_for_dep_check):
    """Every open atdd-issue must have classified dependency entries.

    warn-and-log disposition: violations are reported but do not fail CI.
    """
    rule_id = _RULE.rule_id
    violations: List[Violation] = []

    for issue in atdd_issue_bodies_for_dep_check:
        if _was_created_before_cutoff(issue.get("createdAt")):
            continue
        body = issue.get("body") or ""
        detail = check_dep_classification(body)
        if detail is None:
            continue
        number = issue.get("number")
        violations.append(Violation(
            rule_id=rule_id,
            severity=_RULE.severity,
            location=f"github-issue#{number}:body",
            detail=f"#{number}: {detail}",
            fix_hint_ref=_RULE.fix_hint_ref,
        ))

    assert_disposition_satisfied(
        validator_id="issue_deps_have_classification_tags",
        violations=violations,
    )
