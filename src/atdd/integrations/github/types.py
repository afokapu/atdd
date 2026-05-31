"""Plain-data return types for the GitHub integration layer.

These mirror the *shape* of the Coach-core types ``PrState`` / ``CheckRun`` /
``Review`` / ``MergeResult`` (docs/coach-decomposition.md §4.2, §4.7) but are
defined **here** because §3.3 forbids ``atdd.integrations.github`` from importing
``atdd.coach.*``. ``train.persistence.materialize_evidence()`` (Child 7) maps
these field-for-field onto the Coach-core types when it builds ``Evidence``.

Keeping them local — rather than returning bare dicts — keeps the adapter typed
and table-testable while honouring the "integration calls return plain data, no
Coach types" rule in §4.10.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class GitHubIntegrationError(Exception):
    """Raised when a ``gh`` CLI / GraphQL call fails."""


class MissingProjectTokenError(GitHubIntegrationError):
    """Raised when a Projects v2 mutation is attempted without ``PROJECT_TOKEN``.

    The default ``GITHUB_TOKEN`` in CI cannot write Projects v2 (issue #404),
    which is the root cause of #882. Operators must provision a fine-grained PAT
    with Projects: R/W — see ``docs/operator-projects-v2-token.md``.
    """


@dataclass(frozen=True)
class MergeResult:
    """Outcome of a PR merge attempt (§4.7)."""

    merged: bool
    merge_commit_sha: str | None = None
    reason: str | None = None  # populated when merged is False


@dataclass(frozen=True)
class CheckRunData:
    """Mirror of Coach-core ``CheckRun`` (§4.2)."""

    name: str
    conclusion: str  # SUCCESS|FAILURE|NEUTRAL|CANCELLED|TIMED_OUT|PENDING|NONE
    workflow_id: int | None = None


@dataclass(frozen=True)
class ReviewData:
    """Mirror of Coach-core ``Review`` (§4.2)."""

    reviewer: str
    state: str  # APPROVED|CHANGES_REQUESTED|COMMENTED|DISMISSED
    submitted_at: str  # ISO-8601


@dataclass(frozen=True)
class PrStateData:
    """Mirror of Coach-core ``PrState`` (§4.2)."""

    number: int
    state: str  # OPEN|MERGED|CLOSED
    mergeable: str  # MERGEABLE|CONFLICTING|UNKNOWN
    merge_state: str  # CLEAN|BLOCKED|BEHIND|UNSTABLE|DIRTY|UNKNOWN
    head_sha: str
    check_runs: tuple[CheckRunData, ...] = field(default_factory=tuple)
    reviews: tuple[ReviewData, ...] = field(default_factory=tuple)
    closes_issues: tuple[int, ...] = field(default_factory=tuple)


__all__ = [
    "GitHubIntegrationError",
    "MissingProjectTokenError",
    "MergeResult",
    "CheckRunData",
    "ReviewData",
    "PrStateData",
]
