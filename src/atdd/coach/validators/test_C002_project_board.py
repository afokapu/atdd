"""
C002: Project board confirmation — filterable by status, phase, archetype.

Validates that the GitHub Project v2 board has:
1. All required custom fields (ATDD Status, Phase, Train, etc.)
2. Issues are added to the Project with field values
3. Fields support filtering (single-select fields have expected options)
4. Progress pills visible via sub-issue counts

These tests run against the LIVE GitHub API and require:
- .atdd/config.yaml with github.repo and github.project_id
- gh CLI authenticated with project scope

Run: atdd validate coach
"""
import pytest
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()


def _get_client():
    """Get GitHubClient if configured, else None."""
    try:
        from atdd.coach.github import GitHubClient, ProjectConfig, GitHubClientError
        config_file = REPO_ROOT / ".atdd" / "config.yaml"
        project_config = ProjectConfig.from_config(config_file)
        return GitHubClient(
            repo=project_config.repo,
            project_id=project_config.project_id,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Required Project v2 custom fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "Session Number",
    "ATDD Status",
    "ATDD Phase",
    "Session Type",
    "Complexity",
    "Archetypes",
    "Branch",
    "Train",
    "Feature URN",
]

REQUIRED_STATUS_OPTIONS = {"INIT", "PLANNED", "RED", "GREEN", "REFACTOR", "COMPLETE", "BLOCKED"}
REQUIRED_PHASE_OPTIONS = {"Planner", "Tester", "Coder"}


# ---------------------------------------------------------------------------
# C002 validators: confirm Project board infrastructure
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_project_has_required_custom_fields():
    """
    SPEC-COACH-C002-0001: Project v2 has all required custom fields

    Given: The ATDD Project v2
    When: Querying project fields via GraphQL
    Then: All required fields exist (incl. ATDD Status, Phase, Train, etc.)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        fields = client.get_project_fields()
    except GitHubClientError as e:
        pytest.skip(f"Cannot query Project fields: {e}")

    missing = [f for f in REQUIRED_FIELDS if f not in fields]

    assert not missing, (
        f"\nProject missing required custom fields:\n  "
        + "\n  ".join(missing)
        + f"\n\nFix: Run `atdd init` to create missing fields."
    )


@pytest.mark.platform
def test_atdd_status_field_has_required_options():
    """
    SPEC-COACH-C002-0002: ATDD Status field has all lifecycle options

    Given: The ATDD Status single-select field
    When: Checking available options
    Then: All lifecycle statuses are present (INIT through COMPLETE + BLOCKED)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        fields = client.get_project_fields()
    except GitHubClientError as e:
        pytest.skip(f"Cannot query Project fields: {e}")

    if "ATDD Status" not in fields:
        pytest.skip("ATDD Status field not found")

    options = set(fields["ATDD Status"].get("options", {}).keys())
    missing = REQUIRED_STATUS_OPTIONS - options

    assert not missing, (
        f"\nATDD Status field missing options:\n  "
        + "\n  ".join(sorted(missing))
        + f"\n\nExisting options: {', '.join(sorted(options))}"
    )


@pytest.mark.platform
def test_atdd_phase_field_has_required_options():
    """
    SPEC-COACH-C002-0003: ATDD Phase field has Planner/Tester/Coder options

    Given: The ATDD Phase single-select field
    When: Checking available options
    Then: Planner, Tester, Coder are present
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        fields = client.get_project_fields()
    except GitHubClientError as e:
        pytest.skip(f"Cannot query Project fields: {e}")

    if "ATDD Phase" not in fields:
        pytest.skip("ATDD Phase field not found")

    options = set(fields["ATDD Phase"].get("options", {}).keys())
    missing = REQUIRED_PHASE_OPTIONS - options

    assert not missing, (
        f"\nATDD Phase field missing options:\n  "
        + "\n  ".join(sorted(missing))
        + f"\n\nExisting options: {', '.join(sorted(options))}"
    )


@pytest.mark.platform
def test_issues_are_in_project():
    """
    SPEC-COACH-C002-0004: Issues are added to the Project

    Given: Open issues with atdd-session label
    When: Checking Project membership
    Then: At least one issue has a Project item ID
          (confirming issues are tracked in the board)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        issues = client.list_issues_by_label("atdd-session")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No issues found")

    in_project = 0
    for issue in issues:
        try:
            item_id = client.get_project_item_id(issue["number"])
            if item_id:
                in_project += 1
        except GitHubClientError:
            continue

    assert in_project > 0, (
        f"No issues found in Project board. "
        f"Checked {len(issues)} issues — none have a Project item ID.\n"
        f"Fix: Run `atdd init` to set up the Project, then `atdd new` to create issues."
    )


@pytest.mark.platform
def test_issues_have_status_field_set():
    """
    SPEC-COACH-C002-0005: Issues in Project have ATDD Status set

    Given: Issues in the Project (label: atdd-session)
    When: Reading ATDD Status field value
    Then: At least one issue has a non-empty ATDD Status
          (confirming field values are set, enabling board filtering)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        issues = client.list_issues_by_label("atdd-session")
        fields = client.get_project_fields()
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No issues found")

    if "ATDD Status" not in fields:
        pytest.skip("ATDD Status field not configured")

    has_status = False
    for issue in issues:
        try:
            item_id = client.get_project_item_id(issue["number"])
            if not item_id:
                continue
            values = client.get_project_item_field_values(item_id)
            status = values.get("ATDD Status", "")
            if status:
                has_status = True
                break
        except GitHubClientError:
            continue

    assert has_status, (
        "No issue has ATDD Status set in Project fields.\n"
        "Board filtering by status requires this field to be populated.\n"
        "Fix: Run `atdd update <number> --status INIT` to set the field."
    )


@pytest.mark.platform
def test_archetype_labels_exist():
    """
    SPEC-COACH-C002-0006: Archetype labels exist for board filtering

    Given: The repository label set
    When: Checking for archetype labels
    Then: At least one archetype:* label exists (e.g., archetype:be)
          enabling archetype-based filtering on the Project board
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        issues = client.list_issues_by_label("atdd-session")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No issues found")

    # Check if any issue has archetype labels
    has_archetype = False
    for issue in issues:
        labels = [l["name"] for l in issue.get("labels", [])]
        if any(l.startswith("archetype:") for l in labels):
            has_archetype = True
            break

    assert has_archetype, (
        "No issue has archetype:* labels.\n"
        "Board filtering by archetype requires these labels.\n"
        "Fix: Add archetype labels via `atdd init` or manually."
    )


@pytest.mark.platform
def test_progress_pill_data_available():
    """
    SPEC-COACH-C002-0007: Sub-issue progress data available for progress pills

    Given: Issues with sub-issues (label: atdd-session)
    When: Computing progress fraction
    Then: Progress can be expressed as "N/M WMBTs" where M > 0
          (confirming the data backing progress pills on board cards)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        issues = client.list_issues_by_label("atdd-session")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No issues found")

    progress_available = False
    for issue in issues:
        try:
            subs = client.get_sub_issues(issue["number"])
            if subs:
                total = len(subs)
                closed = sum(1 for s in subs if s.get("state") == "closed")
                # Progress pill would show: "closed/total WMBTs"
                assert total > 0
                progress_available = True
                break
        except (GitHubClientError, AssertionError):
            continue

    assert progress_available, (
        "No issue has sub-issues for progress pill display.\n"
        "The Project board shows progress as N/M WMBTs on each card."
    )
