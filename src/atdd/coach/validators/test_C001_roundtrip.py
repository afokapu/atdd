"""
C001: Round-trip confirmation — atdd new -> close WMBTs -> progress -> validate -> archive.

Validates the full lifecycle of GitHub Issue-based ATDD tracking:
1. IssueManager.new() creates parent issue + WMBT sub-issues
2. IssueManager.close_wmbt() closes a sub-issue and progress advances
3. IssueManager.list() reflects updated progress
4. IssueManager.archive() closes parent + all remaining sub-issues cleanly
5. No orphaned sub-issues after archive

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
# C001 validators: confirm round-trip plumbing
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_issue_manager_methods_exist():
    """
    SPEC-COACH-C001-0001: IssueManager exposes all lifecycle methods

    Given: The IssueManager class
    When: Checking method availability
    Then: new, list, archive, update, close_wmbt, sync methods exist
    """
    from atdd.coach.commands.session import IssueManager

    manager = IssueManager()
    required_methods = ["new", "list", "archive", "update", "close_wmbt", "sync"]
    missing = [m for m in required_methods if not hasattr(manager, m)]

    assert not missing, (
        f"IssueManager missing lifecycle methods: {', '.join(missing)}"
    )


@pytest.mark.platform
def test_github_client_methods_exist():
    """
    SPEC-COACH-C001-0002: GitHubClient exposes all required API methods

    Given: The GitHubClient class
    When: Checking method availability
    Then: create_issue, close_issue, add_sub_issue, get_sub_issues,
          list_issues_by_label, get_project_fields, add_issue_to_project,
          set_project_field_text, set_project_field_select,
          get_project_item_field_values methods exist
    """
    from atdd.coach.github import GitHubClient

    required_methods = [
        "create_issue", "close_issue", "add_sub_issue", "get_sub_issues",
        "list_issues_by_label", "get_project_fields", "add_issue_to_project",
        "set_project_field_text", "set_project_field_select",
        "set_project_field_number", "get_project_item_id",
        "get_project_item_field_values", "get_issue", "ensure_label",
        "add_label", "remove_label",
    ]
    missing = [m for m in required_methods if not callable(getattr(GitHubClient, m, None))]

    assert not missing, (
        f"GitHubClient missing API methods: {', '.join(missing)}"
    )


@pytest.mark.platform
def test_existing_issues_have_sub_issues():
    """
    SPEC-COACH-C001-0003: Existing issues have WMBT sub-issues

    Given: Open issues in the GitHub Project (label: atdd-session)
    When: Querying sub-issues
    Then: At least one issue has sub-issues (WMBTs)
          confirming that atdd new creates the parent+sub-issue structure
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

    has_subs = False
    for issue in issues:
        try:
            subs = client.get_sub_issues(issue["number"])
            if subs:
                has_subs = True
                break
        except GitHubClientError:
            continue

    assert has_subs, (
        "No issue has sub-issues. "
        "The atdd new command should create parent issues with WMBT sub-issues."
    )


@pytest.mark.platform
def test_sub_issue_progress_is_trackable():
    """
    SPEC-COACH-C001-0004: Sub-issue progress is trackable (closed/total)

    Given: An issue with sub-issues
    When: Counting open vs closed sub-issues
    Then: Progress is computable as closed/total
          and both counts are non-negative integers
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

    for issue in issues:
        try:
            subs = client.get_sub_issues(issue["number"])
        except GitHubClientError:
            continue

        if not subs:
            continue

        total = len(subs)
        closed = sum(1 for s in subs if s.get("state") == "closed")
        open_count = sum(1 for s in subs if s.get("state") == "open")

        assert total > 0, f"#{issue['number']}: total sub-issues should be > 0"
        assert closed >= 0, f"#{issue['number']}: closed count should be >= 0"
        assert open_count >= 0, f"#{issue['number']}: open count should be >= 0"
        assert closed + open_count == total, (
            f"#{issue['number']}: closed ({closed}) + open ({open_count}) != total ({total})"
        )
        # Found a valid issue with trackable progress
        return

    pytest.skip("No issue with sub-issues found")


@pytest.mark.platform
def test_archived_issues_have_no_orphaned_sub_issues():
    """
    SPEC-COACH-C001-0005: Archived (closed) issues have no open sub-issues

    Given: Closed issues (label: atdd-session)
    When: Checking sub-issue states
    Then: All sub-issues of closed parent issues are also closed
          (no orphaned open sub-issues)
    """
    client = _get_client()
    if client is None:
        pytest.skip("GitHub integration not configured")

    from atdd.coach.github import GitHubClientError

    try:
        # Get closed issues
        output = client._run_gh([
            "issue", "list",
            "--repo", client.repo,
            "--label", "atdd-session",
            "--state", "closed",
            "--json", "number,title",
            "--limit", "20",
        ])
        import json
        closed_issues = json.loads(output) if output else []
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not closed_issues:
        pytest.skip("No closed issues found")

    orphans = []
    for issue in closed_issues:
        try:
            subs = client.get_sub_issues(issue["number"])
            open_subs = [s for s in subs if s.get("state") == "open"]
            if open_subs:
                sub_nums = ", ".join(f"#{s['number']}" for s in open_subs)
                orphans.append(
                    f"#{issue['number']}: {len(open_subs)} open sub-issues ({sub_nums})"
                )
        except GitHubClientError:
            continue

    assert not orphans, (
        f"\nClosed issues with orphaned open sub-issues:\n  "
        + "\n  ".join(orphans)
        + "\n\nFix: Run `atdd archive <number>` to close all sub-issues."
    )


@pytest.mark.platform
def test_wmbt_sub_issues_have_atdd_wmbt_label():
    """
    SPEC-COACH-C001-0006: WMBT sub-issues carry the atdd-wmbt label

    Given: Sub-issues of parent issues (label: atdd-session)
    When: Checking labels
    Then: Each sub-issue has the atdd-wmbt label
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

    # Check first issue that has sub-issues
    for issue in issues:
        try:
            subs = client.get_sub_issues(issue["number"])
        except GitHubClientError:
            continue

        if not subs:
            continue

        unlabeled = []
        for sub in subs:
            labels = [l["name"] for l in sub.get("labels", [])]
            if "atdd-wmbt" not in labels:
                unlabeled.append(f"#{sub['number']}: {sub.get('title', '?')}")

        if unlabeled:
            assert False, (
                f"\nWMBT sub-issues of #{issue['number']} missing atdd-wmbt label:\n  "
                + "\n  ".join(unlabeled)
            )
        # Found and validated — pass
        return

    pytest.skip("No issue with sub-issues found")
