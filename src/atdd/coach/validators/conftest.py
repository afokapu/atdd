"""
Shared fixtures for coach validators.

Session-scoped fixtures that fetch GitHub data once and share across all
platform tests, eliminating redundant API calls.
"""
import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators.shared_fixtures import *  # noqa: F401,F403


REPO_ROOT = find_repo_root()


def _build_github_client():
    """Build a GitHubClient from .atdd/config.yaml. Returns client or None."""
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


@pytest.fixture(scope="session")
def github_client():
    """Session-scoped GitHubClient (created once, shared across all tests)."""
    client = _build_github_client()
    if client is None:
        pytest.skip("GitHub integration not configured (no .atdd/config.yaml)")
    return client


@pytest.fixture(scope="session")
def github_issues(github_client):
    """All open issues with atdd-issue label (fetched once per session)."""
    from atdd.coach.github import GitHubClientError

    try:
        issues = github_client.list_issues_by_label("atdd-issue")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No issues found")

    return issues


@pytest.fixture(scope="session")
def github_complete_issues(github_client):
    """Issues with atdd:COMPLETE label (fetched once per session)."""
    from atdd.coach.github import GitHubClientError

    try:
        issues = github_client.list_issues_by_label("atdd:COMPLETE")
    except GitHubClientError as e:
        pytest.skip(f"Cannot query GitHub: {e}")

    if not issues:
        pytest.skip("No COMPLETE issues found")

    return issues


@pytest.fixture(scope="session")
def github_project_fields(github_client):
    """Project v2 fields (fetched once per session)."""
    from atdd.coach.github import GitHubClientError

    try:
        return github_client.get_project_fields()
    except GitHubClientError as e:
        pytest.skip(f"Cannot query Project v2 fields (needs 'project' scope): {e}")
