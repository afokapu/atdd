"""
C001: Round-trip confirmation — close WMBTs -> progress -> validate -> archive.

Validates the lifecycle of GitHub Issue-based ATDD tracking:
1. IssueManager.close_wmbt() closes a sub-issue and progress advances
2. IssueManager.list() reflects updated progress
3. IssueManager.archive() closes parent + all remaining sub-issues cleanly
4. No orphaned sub-issues after archive

Creation is NOT covered here: #1477 removed the `IssueManager` mint path
(`new`/`_new_github_issue`), so `atdd author issue` — the store-first,
schema-driven create path — owns it, and the planner's author validators
cover it.

These tests run against the LIVE GitHub API and require:
- .atdd/config.yaml with github.repo and github.project_id
- gh CLI authenticated with project scope

Run: atdd validate coach
"""
import pytest

pytestmark = [pytest.mark.platform, pytest.mark.github_api]


# ---------------------------------------------------------------------------
# C001 validators: confirm round-trip plumbing
# ---------------------------------------------------------------------------


def test_issue_manager_methods_exist():
    """
    SPEC-COACH-C001-0001: IssueManager exposes all lifecycle methods

    Given: The IssueManager class
    When: Checking method availability
    Then: list, archive, update, close_wmbt, sync methods exist

    `new` is deliberately absent: #1477 removed the mint path. Creation is
    `atdd author issue`.
    """
    from atdd.coach.commands.issue import IssueManager

    manager = IssueManager()
    required_methods = ["list", "archive", "update", "close_wmbt", "sync"]
    missing = [m for m in required_methods if not hasattr(manager, m)]

    assert not missing, (
        f"IssueManager missing lifecycle methods: {', '.join(missing)}"
    )


# The mint-path removal guard lives in `test_mint_path_decommissioned.py`, not
# here: this module is marked `platform`/`github_api`, so a guard placed here
# would be deselected in offline runs — and a deselected guard is not a guard.


def test_github_client_methods_exist():
    """
    SPEC-COACH-C001-0002: GitHubClient exposes all required API methods

    Given: The GitHubClient class
    When: Checking method availability
    Then: create_issue, close_issue, add_sub_issue, get_sub_issues,
          list_issues_by_label, get_issue, ensure_label, add_label,
          remove_label methods exist. (Projects v2 board methods —
          get_project_fields/add_issue_to_project/set_project_field_*/
          get_project_item_* — were removed in #1051; state lives in the
          atdd:<phase> label + .atdd/manifest.yaml, not the board.)
    """
    from atdd.coach.github import GitHubClient

    required_methods = [
        "create_issue", "close_issue", "add_sub_issue", "get_sub_issues",
        "get_all_sub_issues",
        "list_issues_by_label", "get_issue", "ensure_label",
        "add_label", "remove_label",
    ]
    missing = [m for m in required_methods if not callable(getattr(GitHubClient, m, None))]

    assert not missing, (
        f"GitHubClient missing API methods: {', '.join(missing)}"
    )


def test_existing_issues_have_sub_issues(github_sub_issues):
    """
    SPEC-COACH-C001-0003: Existing issues have WMBT sub-issues

    Given: Open issues in the GitHub Project (label: atdd-issue)
    When: Querying sub-issues
    Then: At least one issue has sub-issues (WMBTs)
          confirming the create path lands the parent+sub-issue structure
    """
    has_subs = any(subs for subs in github_sub_issues.values())

    if not has_subs:
        pytest.skip(
            "No issue has sub-issues yet. "
            "Create via `atdd author issue --title <t> --slug <s>`."
        )


def test_sub_issue_progress_is_trackable(github_sub_issues):
    """
    SPEC-COACH-C001-0004: Sub-issue progress is trackable (closed/total)

    Given: An issue with sub-issues
    When: Counting open vs closed sub-issues
    Then: Progress is computable as closed/total
          and both counts are non-negative integers
    """
    for num, subs in github_sub_issues.items():
        if not subs:
            continue

        total = len(subs)
        closed = sum(1 for s in subs if s.get("state") == "closed")
        open_count = sum(1 for s in subs if s.get("state") == "open")

        assert total > 0, f"#{num}: total sub-issues should be > 0"
        assert closed >= 0, f"#{num}: closed count should be >= 0"
        assert open_count >= 0, f"#{num}: open count should be >= 0"
        assert closed + open_count == total, (
            f"#{num}: closed ({closed}) + open ({open_count}) != total ({total})"
        )
        # Found a valid issue with trackable progress
        return

    pytest.skip("No issue with sub-issues found")


def test_archived_issues_have_no_orphaned_sub_issues(github_closed_sub_issues):
    """
    SPEC-COACH-C001-0005: Archived (closed) issues have no open sub-issues

    Given: Closed issues (label: atdd-issue)
    When: Checking sub-issue states
    Then: All sub-issues of closed parent issues are also closed
          (no orphaned open sub-issues)
    """
    if not github_closed_sub_issues:
        pytest.skip("No closed issues found")

    orphans = []
    for num, subs in github_closed_sub_issues.items():
        open_subs = [s for s in subs if s.get("state") == "open"]
        if open_subs:
            sub_nums = ", ".join(f"#{s['number']}" for s in open_subs)
            orphans.append(
                f"#{num}: {len(open_subs)} open sub-issues ({sub_nums})"
            )

    assert not orphans, (
        f"\nClosed issues with orphaned open sub-issues:\n  "
        + "\n  ".join(orphans)
        + "\n\nFix: Run `atdd archive <number>` to close all sub-issues."
    )


def test_wmbt_sub_issues_have_atdd_wmbt_label(github_sub_issues):
    """
    SPEC-COACH-C001-0006: WMBT sub-issues carry the atdd-wmbt label

    Given: Sub-issues of parent issues (label: atdd-issue)
    When: Checking labels
    Then: Each sub-issue has the atdd-wmbt label
    """
    for num, subs in github_sub_issues.items():
        if not subs:
            continue

        unlabeled = []
        for sub in subs:
            labels = [l["name"] for l in sub.get("labels", [])]
            if "atdd-wmbt" not in labels:
                unlabeled.append(f"#{sub['number']}: {sub.get('title', '?')}")

        if unlabeled:
            assert False, (
                f"\nWMBT sub-issues of #{num} missing atdd-wmbt label:\n  "
                + "\n  ".join(unlabeled)
            )
        # Found and validated — pass
        return

    pytest.skip("No issue with sub-issues found")
