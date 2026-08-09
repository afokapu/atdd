"""
Shared fixtures for coach validators.

Session-scoped fixtures that fetch GitHub data once and share across all
platform tests, eliminating redundant API calls.

Performance optimization: ``_github_prefetch`` uses ``GitHubClient.prefetch_validator_data()``
which batches API calls into 3 parallel groups (issues, project data, sub-issues),
reducing 7 sequential HTTP round-trips to 3 concurrent ones.
"""
import subprocess

import pytest
from concurrent.futures import ThreadPoolExecutor

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators.shared_fixtures import *  # noqa: F401,F403


REPO_ROOT = find_repo_root()


@pytest.fixture(scope="session", autouse=True)
def _worktree_integrity_guard():
    """Session-level fallback: active worktree unchanged after the full validator session.

    Snapshots ``git rev-parse HEAD`` and ``git config core.bare`` before the
    session starts.  Asserts both are identical after.

    NOTE: ``src/atdd/conftest.py`` now has a **function-scoped** autouse guard
    (_git_repo_pollution_guard) that covers ALL src/atdd test dirs, catches
    each polluting test individually, names it via request.node.nodeid, and
    restores core.bare immediately — so per-test isolation is handled upstream
    (issue #771).  This session guard remains as a belt-and-suspenders check
    for phantom commits (HEAD drift) that the per-test guard may not surface
    on its own in a single-assertion stop.
    """
    def _git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    head_before = _git("rev-parse", "HEAD")
    bare_before = _git("config", "core.bare")

    yield

    head_after = _git("rev-parse", "HEAD")
    bare_after = _git("config", "core.bare")

    assert head_before == head_after, (
        f"Test session added phantom commits to the active worktree.\n"
        f"  HEAD before: {head_before}\n"
        f"  HEAD after:  {head_after}\n"
        "A test ran `git commit` against the live repo rather than a tmp_path "
        "fixture.  Find it with:\n"
        "  git log --oneline --author='ATDD Test' HEAD~10..HEAD"
    )
    assert bare_before == bare_after, (
        f"Test session mutated core.bare on the active worktree.\n"
        f"  core.bare before: {bare_before!r}\n"
        f"  core.bare after:  {bare_after!r}\n"
        "A test called `git config core.bare true` against the live repo.\n"
        "Recovery: git config core.bare false"
    )


def _build_github_client():
    """Build a GitHubClient from .atdd/config.yaml. Returns client or None."""
    try:
        from atdd.coach.github import GitHubClient, ProjectConfig

        config_file = REPO_ROOT / ".atdd" / "config.yaml"
        project_config = ProjectConfig.from_config(config_file)
        return GitHubClient(repo=project_config.repo)
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

    Uses GitHubClient.prefetch_validator_data() for issues and sub-issues
    (2 parallel groups instead of 5 sequential). Branch protection is fetched
    in parallel alongside the batch.
    """
    results = {}

    def _fetch_batch():
        try:
            results.update(github_client.prefetch_validator_data())
        except Exception as e:
            for key in ("issues", "complete_issues", "all_open_issues",
                        "sub_issues", "closed_sub_issues"):
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
def all_open_issues_unfiltered(_github_prefetch):
    """All open repo issues, unfiltered by label (from prefetch cache).

    Counterpart to ``github_issues`` (which filters by ``atdd-issue``).
    Required by #296 D005 — the inverse-filter validator needs to see
    unlabeled issues that the default prefetch drops.
    """
    data = _github_prefetch.get("all_open_issues")
    if isinstance(data, Exception):
        pytest.skip(f"Cannot query GitHub: {data}")
    if data is None:
        pytest.skip("No open issues in prefetch cache")
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
