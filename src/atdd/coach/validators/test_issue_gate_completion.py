"""
Gate completion validation for COMPLETE issues.

Purpose: Verify that COMPLETE issues have deterministic evidence:
- Gate test commands all PASS (exit code 0)
- Artifact paths verified against git (exist/changed/deleted)
- Release gate verified (version bumped, tag on HEAD)

This is the CI counterpart to the CLI checks in ``atdd update --status COMPLETE``.

Run: atdd validate coach
"""

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()


def _get_github_client_if_configured():
    """Try to get a GitHubClient. Returns client or None."""
    try:
        from atdd.coach.github import GitHubClient, ProjectConfig

        config_file = REPO_ROOT / ".atdd" / "config.yaml"
        project_config = ProjectConfig.from_config(config_file)
        return GitHubClient(
            repo=project_config.repo,
            project_id=project_config.project_id,
        )
    except Exception:
        return None


def _get_complete_issues(client):
    """Return open+closed issues with atdd:COMPLETE label."""
    from atdd.coach.github import GitHubClientError

    try:
        issues = client.list_issues_by_label("atdd:COMPLETE")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No COMPLETE issues found")

    return issues


# ---------------------------------------------------------------------------
# SPEC-GATE-0001: Gate test commands must PASS for COMPLETE issues
# ---------------------------------------------------------------------------

@pytest.mark.platform
def test_complete_issues_gate_tests_pass():
    """
    SPEC-GATE-0001: All gate test commands in COMPLETE issues must PASS.

    Given: Issues labelled atdd:COMPLETE
    When: Parsing the Gate Tests table from the issue body
    Then: Every gate command exits 0 when run from the repo root
    """
    client = _get_github_client_if_configured()
    if client is None:
        pytest.skip("GitHub integration not configured")

    issues = _get_complete_issues(client)
    manager = IssueManager(target_dir=REPO_ROOT)

    failures = []

    for issue in issues:
        num = issue["number"]
        body = issue.get("body", "") or ""
        gates = manager._parse_gate_tests(body)

        if not gates:
            continue

        for gate in gates:
            result = subprocess.run(
                gate["command"],
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                timeout=300,
            )
            if result.returncode != 0:
                stderr_tail = result.stderr.strip().splitlines()[-3:] if result.stderr else []
                failures.append(
                    f"#{num} {gate['id']}: FAIL (exit {result.returncode}) — {gate['command']}"
                    + ("\n    " + "\n    ".join(stderr_tail) if stderr_tail else "")
                )

    assert not failures, (
        f"\nCOMPLETE issues have failing gate commands.\n"
        f"Fix: Resolve failures, then re-run `atdd validate coach`.\n\n"
        f"Failures ({len(failures)}):\n  " + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# SPEC-GATE-0002: Artifact claims must be valid for COMPLETE issues
# ---------------------------------------------------------------------------

@pytest.mark.platform
def test_complete_issues_artifacts_valid():
    """
    SPEC-GATE-0002: Artifact claims in COMPLETE issues must match git state.

    Given: Issues labelled atdd:COMPLETE
    When: Parsing the Artifacts section and checking against git
    Then: Created files exist, Modified files have changes vs main, Deleted files are gone
    """
    client = _get_github_client_if_configured()
    if client is None:
        pytest.skip("GitHub integration not configured")

    issues = _get_complete_issues(client)
    manager = IssueManager(target_dir=REPO_ROOT)

    failures = []

    for issue in issues:
        num = issue["number"]
        body = issue.get("body", "") or ""
        artifacts = manager._parse_artifacts(body)
        total = sum(len(v) for v in artifacts.values())

        if total == 0:
            continue

        valid, messages = manager._verify_artifacts(artifacts, force=False)
        if not valid:
            failed_lines = [m for m in messages if "MISSING" in m or "NO CHANGES" in m or "STILL EXISTS" in m]
            failures.append(
                f"#{num}: artifact verification failed\n    " + "\n    ".join(failed_lines)
            )

    assert not failures, (
        f"\nCOMPLETE issues have invalid artifact claims.\n"
        f"Fix: Update ## Artifacts section to match actual git state.\n\n"
        f"Failures ({len(failures)}):\n  " + "\n  ".join(failures)
    )


# ---------------------------------------------------------------------------
# SPEC-GATE-0003: Release gate must be satisfied for COMPLETE issues
# ---------------------------------------------------------------------------

@pytest.mark.platform
def test_complete_issues_release_gate():
    """
    SPEC-GATE-0003: COMPLETE issues must have version bumped and tag on HEAD.

    Given: Issues labelled atdd:COMPLETE
    When: Checking the release config (version_file, tag)
    Then: Version is changed vs main and tag exists on HEAD or recent ancestor

    Note: This validates the overall release state, not per-issue.
    If any COMPLETE issue exists, the release gate must be satisfied.
    """
    client = _get_github_client_if_configured()
    if client is None:
        pytest.skip("GitHub integration not configured")

    issues = _get_complete_issues(client)
    manager = IssueManager(target_dir=REPO_ROOT)

    # Release gate is a repo-level check, not per-issue.
    # If there are any COMPLETE issues, the release must be tagged.
    valid, messages = manager._verify_release_gate(force=False)

    assert valid, (
        f"\nRelease gate not satisfied for COMPLETE issues.\n"
        f"Fix: Bump version, commit, create tag.\n\n"
        + "\n".join(messages)
    )
