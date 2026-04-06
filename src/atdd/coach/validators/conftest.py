"""
Shared fixtures for coach validators.

Session-scoped fixtures that fetch GitHub data once and share across all
platform tests, eliminating redundant API calls.

Performance optimization: ``_github_prefetch`` uses ``GitHubClient.prefetch_validator_data()``
which batches API calls into 3 parallel groups (issues, project data, sub-issues),
reducing 7 sequential HTTP round-trips to 3 concurrent ones.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor

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
    """Prefetch ALL GitHub data via batched API calls.

    Uses GitHubClient.prefetch_validator_data() for issues, project fields,
    project items, and sub-issues (3 parallel groups instead of 7 sequential).
    Branch protection is fetched in parallel alongside the batch.
    """
    results = {}

    def _fetch_batch():
        try:
            results.update(github_client.prefetch_validator_data())
        except Exception as e:
            for key in ("issues", "complete_issues", "project_fields",
                        "project_items", "sub_issues", "closed_sub_issues"):
                results.setdefault(key, e)

    def _fetch_branch_protection():
        try:
            from atdd.coach.commands.branch_protection import verify_branch_protection
            results["branch_protection"] = verify_branch_protection(github_client.repo)
        except Exception as e:
            results["branch_protection"] = e

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_fetch_batch)
        f2 = pool.submit(_fetch_branch_protection)
        f1.result()
        f2.result()

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
