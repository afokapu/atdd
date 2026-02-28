"""
Issue validation against GitHub Issues and Project v2 fields.

Purpose: Validate GitHub Issues before implementation starts.
Convention: src/atdd/coach/conventions/issue.convention.yaml

E008: Train enforcement validators (SPEC-SESSION-VAL-0050 to 0051):
- Issues must have a non-empty Train field after PLANNED phase
- Train field must reference a valid train_id from _trains.yaml

E010: Body section validator (SPEC-SESSION-VAL-0060):
- Issues should have all 11 structured sections from PARENT-ISSUE-TEMPLATE.md
- Soft check (warning) for pre-E010 issues

Run: atdd validate coach
"""
import warnings as w
import pytest
from pathlib import Path
import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.github import GitHubClientError

# ============================================================================
# Configuration
# ============================================================================

REPO_ROOT = find_repo_root()


# ============================================================================
# E008: Issue Train Enforcement (GitHub Issues)
# ============================================================================


def _load_valid_train_ids():
    """Load all valid train IDs from plan/_trains.yaml and plan/_trains/*.yaml."""
    plan_dir = REPO_ROOT / "plan"
    trains_file = plan_dir / "_trains.yaml"
    valid_ids = set()

    if trains_file.exists():
        with open(trains_file) as f:
            data = yaml.safe_load(f) or {}
        for theme_key, categories in data.get("trains", {}).items():
            if isinstance(categories, dict):
                for cat_key, trains_list in categories.items():
                    if isinstance(trains_list, list):
                        for t in trains_list:
                            tid = t.get("train_id", "")
                            if tid:
                                valid_ids.add(tid)

    trains_dir = plan_dir / "_trains"
    if trains_dir.exists():
        for f in trains_dir.glob("*.yaml"):
            valid_ids.add(f.stem)

    return valid_ids


# Post-PLANNED phases where Train field is required
_POST_PLANNED_STATUSES = {"RED", "GREEN", "REFACTOR", "COMPLETE"}


@pytest.mark.platform
def test_issues_have_train_field(github_client, github_issues, github_project_fields):
    """
    SPEC-SESSION-VAL-0050: Issues must have a non-empty Train field

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Checking the Train custom field value
    Then: Issues past PLANNED phase must have Train != TBD and != blank
          Issues at PLANNED phase get a warning if Train is TBD

    E008 acceptance criteria: `atdd validate coach` fails if issue has no train assignment.
    """
    if "ATDD: Train" not in github_project_fields:
        pytest.skip("Train field not configured in Project")

    violations = []
    warnings_list = []

    for issue in github_issues:
        num = issue["number"]

        try:
            item_id = github_client.get_project_item_id(num)
        except GitHubClientError:
            continue
        if not item_id:
            continue

        try:
            values = github_client.get_project_item_field_values(item_id)
        except GitHubClientError:
            continue

        train_value = (values.get("ATDD: Train") or "").strip()
        status_value = (values.get("ATDD: Status") or "UNKNOWN").strip().upper()

        is_empty = not train_value or train_value.upper() == "TBD"

        if is_empty and status_value in _POST_PLANNED_STATUSES:
            violations.append(
                f"#{num} (status={status_value}): Train field is "
                f"{'TBD' if train_value.upper() == 'TBD' else 'empty'}"
            )
        elif is_empty and status_value == "PLANNED":
            warnings_list.append(
                f"#{num} (status=PLANNED): Train field is TBD — "
                f"required before transitioning past PLANNED"
            )

    if warnings_list:
        w.warn(
            f"Issue train assignment warnings ({len(warnings_list)}):\n  "
            + "\n  ".join(warnings_list),
            category=UserWarning,
            stacklevel=1,
        )

    assert not violations, (
        f"\nIssues past PLANNED must have a valid Train field (not TBD, not blank).\n"
        f"Fix: Run `atdd update <issue_number> --train <train_id>`\n\n"
        f"Violations ({len(violations)}):\n  " + "\n  ".join(violations)
    )


@pytest.mark.platform
def test_issue_train_references_valid_train_id(github_client, github_issues, github_project_fields):
    """
    SPEC-SESSION-VAL-0051: Issue Train field must reference a valid train_id

    Given: Issues with a non-empty Train field
    When: Cross-referencing against plan/_trains.yaml
    Then: The Train value matches a known train_id

    E008 acceptance criteria: Train value must reference a valid train_id from _trains.yaml.
    """
    valid_train_ids = _load_valid_train_ids()
    if not valid_train_ids:
        pytest.skip("No trains found in plan/_trains.yaml")

    if "ATDD: Train" not in github_project_fields:
        pytest.skip("Train field not configured in Project")

    invalid = []

    for issue in github_issues:
        num = issue["number"]

        try:
            item_id = github_client.get_project_item_id(num)
        except GitHubClientError:
            continue
        if not item_id:
            continue

        try:
            values = github_client.get_project_item_field_values(item_id)
        except GitHubClientError:
            continue

        train_value = (values.get("ATDD: Train") or "").strip()

        # Skip empty/TBD — handled by SPEC-SESSION-VAL-0050
        if not train_value or train_value.upper() == "TBD":
            continue

        if train_value not in valid_train_ids:
            invalid.append(
                f"#{num}: Train='{train_value}' not found in _trains.yaml"
            )

    assert not invalid, (
        f"\nIssue Train field values must reference valid train IDs from plan/_trains.yaml.\n"
        f"Valid train IDs: {', '.join(sorted(list(valid_train_ids)[:10]))}...\n\n"
        f"Invalid references ({len(invalid)}):\n  " + "\n  ".join(invalid)
    )


# ============================================================================
# E010: Body Section Validation (GitHub Issues)
# ============================================================================

REQUIRED_BODY_SECTIONS = [
    "## Issue Metadata",
    "## Scope",
    "## Context",
    "## Architecture",
    "## Phases",
    "## Validation",
    "## Decisions",
    "## Activity Log",
    "## Artifacts",
    "## Release Gate",
    "## Notes",
]


@pytest.mark.platform
def test_issue_body_has_required_sections(github_issues):
    """
    SPEC-SESSION-VAL-0060: Issue body should contain all structured sections

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Checking the issue body for required H2 headings
    Then: All 11 sections from PARENT-ISSUE-TEMPLATE.md should be present
          Pre-E010 issues emit warnings instead of hard failures

    E010 acceptance criteria: `atdd validate coach` warns if issue body is missing sections.
    """
    incomplete = []

    for issue in github_issues:
        num = issue["number"]
        body = issue.get("body", "") or ""
        missing = [s for s in REQUIRED_BODY_SECTIONS if s not in body]
        if missing:
            incomplete.append(
                f"#{num}: missing {len(missing)} section(s): {', '.join(missing)}"
            )

    if incomplete:
        w.warn(
            f"Issues with incomplete body sections ({len(incomplete)}):\n  "
            + "\n  ".join(incomplete)
            + "\n\nHint: Re-create with `atdd new` (E010+) for full-structure body.",
            category=UserWarning,
            stacklevel=1,
        )
