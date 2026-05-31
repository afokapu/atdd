"""
Walk every open ATDD parent issue and fail hard if any are non-compliant
with the PARENT-ISSUE-TEMPLATE.md shape.

Validates:
- SPEC-GOVERN-ORCH-D003: orchestrate requires the Issue Metadata table,
  the `### Dependencies` heading, and no unfilled placeholders on every
  issue it will walk — this validator escalates the existing warning-only
  check to a hard failure.

This is the "read-time enforcement" half of the orchestrate-ready-lifecycle
feature (#280). The write-time half is D001 (template seed on create) and
D002 (sync-wmbts backfill).

Convention: src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md
"""

from typing import Dict, List

import pytest

from atdd.coach.commands.issue_template import (
    check_body_sections,
    check_placeholders,
)


_DEPENDENCIES_HEADING = "### Dependencies"


def _find_drift(issues: List[Dict]) -> List[str]:
    """Return one drift message per non-compliant open parent issue.

    An issue is considered drifted when:
    - It is missing any required ``## `` section, OR
    - It has any unfilled placeholder string inside a named section, OR
    - It is missing the ``### Dependencies`` heading the orchestrate
      walker relies on.

    Closed, terminal, and non-atdd-issue labeled items should be filtered
    out by the caller before passing them in — this helper is pure.
    """
    messages: List[str] = []
    for issue in issues:
        number = issue.get("number", "<unknown>")
        body = issue.get("body") or ""

        missing_sections = check_body_sections(body)
        unfilled = check_placeholders(body)
        missing_deps = _DEPENDENCIES_HEADING not in body

        if not (missing_sections or unfilled or missing_deps):
            continue

        parts: List[str] = []
        if missing_sections:
            parts.append(f"missing sections: {missing_sections}")
        if unfilled:
            placeholder_summary = [f"{s} → {p}" for s, p in unfilled]
            parts.append(f"unfilled placeholders: {placeholder_summary}")
        if missing_deps:
            parts.append(f"missing '{_DEPENDENCIES_HEADING}' heading")

        messages.append(f"  #{number}: " + "; ".join(parts))
    return messages


@pytest.mark.coach
@pytest.mark.github_api  # consumes live `github_issues` — offline gate must skip (#932)
def test_open_issues_are_orchestrate_ready(github_issues):
    """SPEC-GOVERN-ORCH-D003: Every open parent issue must be template-compliant
    and expose a ``### Dependencies`` heading so ``atdd orchestrate`` can walk
    the dep graph without post-hoc body edits.

    Given: Open issues with the ``atdd-issue`` label
    When:  Walking each body through the section + placeholder + dependencies check
    Then:  Any drift is a hard failure with per-issue detail
    """
    drift = _find_drift(list(github_issues))
    if drift:
        pytest.fail(
            f"\n\n{len(drift)} open issue(s) drifted from PARENT-ISSUE-TEMPLATE shape:\n\n"
            + "\n".join(drift)
            + "\n\nFix each issue via `atdd issue <N> --check` to see details."
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helper.
# ---------------------------------------------------------------------------

def _make_compliant_body() -> str:
    """Build a fully-compliant fixture body by rendering the real
    PARENT-ISSUE-TEMPLATE.md. Avoids drift as the template evolves.
    """
    from atdd.coach.commands.issue import IssueManager
    manager = IssueManager.__new__(IssueManager)
    from pathlib import Path as _P
    manager.package_root = _P(__file__).resolve().parent.parent
    manager.parent_template_source = (
        manager.package_root / "templates" / "PARENT-ISSUE-TEMPLATE.md"
    )
    body = manager._render_parent_body(
        slug="demo",
        issue_type="implementation",
        today="2026-04-14",
        train_display="0001-demo",
        archetypes_display="coach",
    )
    from atdd.coach.commands.issue_template import PLACEHOLDER_STRINGS
    for placeholder in PLACEHOLDER_STRINGS:
        body = body.replace(placeholder, "concrete content")
    return body


_COMPLIANT_BODY = _make_compliant_body()


def test_find_drift_empty_for_compliant_issue():
    """A fully template-compliant body produces no drift messages."""
    issues = [{"number": 42, "body": _COMPLIANT_BODY}]
    assert _find_drift(issues) == []


def test_find_drift_reports_missing_sections():
    """An issue missing the Phases/Validation/Activity Log/Artifacts sections
    is flagged as drifted.
    """
    bare_body = "## Issue Metadata\n\n| Branch | `feat/x` |\n\n### Dependencies\n\n- none\n"
    issues = [{"number": 7, "body": bare_body}]
    drift = _find_drift(issues)
    assert len(drift) == 1
    assert "missing sections" in drift[0]


def test_find_drift_reports_missing_dependencies_heading():
    """A body missing the `### Dependencies` heading is flagged even when
    every top-level ## section is present.
    """
    body = _COMPLIANT_BODY.replace("### Dependencies", "### Deps")
    issues = [{"number": 8, "body": body}]
    drift = _find_drift(issues)
    assert len(drift) == 1
    assert "Dependencies" in drift[0]


def test_find_drift_walks_multiple_issues_independently():
    """Drift is reported per issue; compliant issues are not included."""
    issues = [
        {"number": 1, "body": _COMPLIANT_BODY},
        {"number": 2, "body": "## Issue Metadata\n\nno structure\n"},
        {"number": 3, "body": _COMPLIANT_BODY},
    ]
    drift = _find_drift(issues)
    assert len(drift) == 1
    assert "#2:" in drift[0]
