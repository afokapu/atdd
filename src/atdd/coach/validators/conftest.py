"""
Shared fixtures for coach validators.

Session-scoped fixtures that fetch GitHub data once and share across all
platform tests, eliminating redundant API calls.

Performance optimization: ``_github_prefetch`` runs all API calls in
parallel via ``concurrent.futures.ThreadPoolExecutor``, reducing total
GitHub API wait time from ~5s (sequential) to ~1s (parallel).
"""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed

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
def _github_prefetch(github_client):
    """Prefetch ALL GitHub data in parallel (single session fixture).

    Runs 6 API calls concurrently via ThreadPoolExecutor, reducing total
    setup time from ~5s to ~1s. Individual fixtures below read from this
    cache instead of making their own API calls.
    """
    results = {}

    def _fetch(key, fn):
        try:
            results[key] = fn()
        except Exception as e:
            results[key] = e

    def _fetch_branch_protection():
        from atdd.coach.commands.branch_protection import verify_branch_protection
        return verify_branch_protection(github_client.repo)

    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = [
            pool.submit(_fetch, "issues", lambda: github_client.list_issues_by_label("atdd-issue")),
            pool.submit(_fetch, "complete_issues", lambda: github_client.list_issues_by_label("atdd:COMPLETE")),
            pool.submit(_fetch, "project_fields", lambda: github_client.get_project_fields()),
            pool.submit(_fetch, "project_items", lambda: github_client.get_all_project_items()),
            pool.submit(_fetch, "sub_issues", lambda: github_client.get_all_sub_issues("atdd-issue", "OPEN")),
            pool.submit(_fetch, "closed_sub_issues", lambda: github_client.get_all_sub_issues("atdd-issue", "CLOSED")),
            pool.submit(_fetch, "branch_protection", _fetch_branch_protection),
        ]
        for f in as_completed(futures):
            f.result()

    return results


@pytest.fixture(scope="session")
def github_issues(_github_prefetch):
    """All open issues with atdd-issue label (from prefetch cache)."""
    data = _github_prefetch.get("issues")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot query GitHub: {data}")
    if not data:
        pytest.skip("No issues found")
    return data


@pytest.fixture(scope="session")
def github_complete_issues(_github_prefetch):
    """Issues with atdd:COMPLETE label (from prefetch cache)."""
    data = _github_prefetch.get("complete_issues")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot query GitHub: {data}")
    if not data:
        pytest.skip("No COMPLETE issues found")
    return data


@pytest.fixture(scope="session")
def github_project_fields(_github_prefetch):
    """Project v2 fields (from prefetch cache)."""
    data = _github_prefetch.get("project_fields")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot query Project v2 fields: {data}")
    return data


@pytest.fixture(scope="session")
def github_project_items(_github_prefetch):
    """All project items with field values (from prefetch cache)."""
    data = _github_prefetch.get("project_items")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot query project items: {data}")
    return data


@pytest.fixture(scope="session")
def github_sub_issues(_github_prefetch):
    """Sub-issues for all open parent issues (from prefetch cache)."""
    data = _github_prefetch.get("sub_issues")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot batch-query sub-issues: {data}")
    return data


@pytest.fixture(scope="session")
def github_closed_sub_issues(_github_prefetch):
    """Sub-issues for all closed parent issues (from prefetch cache)."""
    data = _github_prefetch.get("closed_sub_issues")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot batch-query closed sub-issues: {data}")
    return data


@pytest.fixture(scope="session")
def repo_name(github_client):
    """Repo name from session-scoped GitHubClient."""
    return github_client.repo


@pytest.fixture(scope="session")
def protection_result(_github_prefetch):
    """Branch protection result (from prefetch cache)."""
    from atdd.coach.commands.branch_protection import ProtectionStatus

    data = _github_prefetch.get("branch_protection")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot verify branch protection: {data}")
    status, details = data
    if status == ProtectionStatus.DEGRADED:
        pytest.skip(
            f"Cannot verify branch protection (degraded mode): "
            f"{'; '.join(details)}"
        )
    return status, details
