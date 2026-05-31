"""GitHub pull-request adapter (docs/coach-decomposition.md §4.10).

Returns plain data (:class:`PrStateData` / :class:`MergeResult`); Coach-core's
``merge_readiness`` consumes the mapped ``PrState`` that Child 7 builds.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from atdd.integrations.github import _gh
from atdd.integrations.github.types import (
    CheckRunData,
    GitHubIntegrationError,
    MergeResult,
    PrStateData,
    ReviewData,
)

_log = logging.getLogger(__name__)

_PR_VIEW_FIELDS = (
    "number,state,mergeable,mergeStateStatus,headRefOid,"
    "statusCheckRollup,reviews,closingIssuesReferences,mergeCommit"
)


def _rollup_to_check_runs(rollup: list) -> tuple[CheckRunData, ...]:
    runs: list[CheckRunData] = []
    for item in rollup or []:
        name = item.get("name") or item.get("context") or ""
        # CheckRun nodes carry `conclusion` (+ `status` while running);
        # legacy StatusContext nodes carry `state`.
        conclusion = (
            item.get("conclusion")
            or item.get("state")
            or item.get("status")
            or "NONE"
        )
        runs.append(CheckRunData(name=name, conclusion=str(conclusion).upper()))
    return tuple(runs)


def _reviews(raw: list) -> tuple[ReviewData, ...]:
    out: list[ReviewData] = []
    for r in raw or []:
        author = (r.get("author") or {}).get("login", "")
        out.append(
            ReviewData(
                reviewer=author,
                state=str(r.get("state", "")).upper(),
                submitted_at=r.get("submittedAt", ""),
            )
        )
    return tuple(out)


def read_pr_state(pr: int) -> PrStateData:
    """Fetch and normalise PR #*pr* into a :class:`PrStateData`."""
    out = _gh.run_gh(["pr", "view", str(pr), "--json", _PR_VIEW_FIELDS])
    data = json.loads(out) if out else {}
    merge_state = data.get("mergeStateStatus") or "UNKNOWN"
    closes = tuple(
        ref["number"]
        for ref in data.get("closingIssuesReferences", [])
        if ref.get("number") is not None
    )
    return PrStateData(
        number=data.get("number", pr),
        state=str(data.get("state", "UNKNOWN")).upper(),
        mergeable=str(data.get("mergeable", "UNKNOWN")).upper(),
        merge_state=str(merge_state).upper(),
        head_sha=data.get("headRefOid", ""),
        check_runs=_rollup_to_check_runs(data.get("statusCheckRollup", [])),
        reviews=_reviews(data.get("reviews", [])),
        closes_issues=closes,
    )


def open_pr(issue: int, *, title: str, body: str) -> int:
    """Open a PR (draft) for *issue*'s branch. Returns the new PR number.

    This is the sanctioned home for ``gh pr create``; the ``atdd pr`` command
    delegates here. The body should carry ``Closes #<issue>``.
    """
    url = _gh.run_gh(
        ["pr", "create", "--draft", "--title", title, "--body-file", "-"],
        input_text=body,
    )
    last = url.rstrip("/").split("/")[-1]
    try:
        return int(last)
    except ValueError as exc:
        raise GitHubIntegrationError(
            f"could not parse PR number from gh output: {url!r}"
        ) from exc


def merge_pr(
    pr: int, *, strategy: Literal["squash", "merge", "rebase"] = "squash"
) -> MergeResult:
    """Merge PR #*pr* using *strategy*. Returns a :class:`MergeResult`.

    On a clean merge the merge-commit sha is read back from ``gh pr view``. A
    ``gh`` failure (conflict, blocked, checks pending) is returned as
    ``MergeResult(merged=False, reason=...)`` rather than raised, so the caller
    can surface it as a lifecycle blocker.
    """
    try:
        _gh.run_gh(["pr", "merge", str(pr), f"--{strategy}"])
    except GitHubIntegrationError as exc:
        return MergeResult(merged=False, reason=str(exc))
    sha = None
    try:
        out = _gh.run_gh(
            ["pr", "view", str(pr), "--json", "mergeCommit",
             "--jq", ".mergeCommit.oid"]
        )
        sha = out or None
    except GitHubIntegrationError as exc:
        _log.warning(
            "merged PR but could not read merge-commit sha",
            extra={"pr": pr, "error": str(exc)},
        )
    return MergeResult(merged=True, merge_commit_sha=sha)


def update_branch(pr: int) -> None:
    """Update PR #*pr*'s branch with the base branch (resolve BEHIND state)."""
    _gh.run_gh(["pr", "update-branch", str(pr)])


__all__ = ["read_pr_state", "open_pr", "merge_pr", "update_branch"]
