"""
GitHub API client for ATDD issue tracking.

Wraps `gh` CLI for GitHub Issues, sub-issues, and labels.
Requires `gh` CLI to be installed and authenticated.

Usage:
    client = GitHubClient(repo="afokapu/atdd")
    issue_number = client.create_issue(title="...", body="...", labels=["atdd-issue"])
    client.add_sub_issue(parent_number=11, child_number=12)
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


class GitHubPermissionError(GitHubClientError):
    """A ``gh`` call was refused because the credential lacks the permission.

    A subclass, so every existing ``except GitHubClientError`` keeps catching it —
    but a distinct type, because the two failures have opposite remedies. A
    transport error is worth retrying; a scope that was never granted never
    becomes granted by trying again.

    #1621: the auto-phase workflow's label writes were refused on every run with
    ``Resource not accessible by personal access token``, and because that arrived
    as a plain ``GitHubClientError`` with the same shape as any other failure, two
    separate investigations read it as GitHub flakiness.
    """

    def __init__(
        self, message: str, *, command: Optional[List[str]] = None, stderr: str = "",
    ) -> None:
        self.command = list(command or [])
        self.stderr = stderr
        super().__init__(message)


#: How GitHub words "authenticated, but not authorised". The wording differs by
#: credential kind — ``personal access token`` for a PAT, ``integration`` for
#: GITHUB_TOKEN and GitHub Apps — and both mean the same thing to a caller.
#:
#: These are *phrases*, deliberately, not the status code. HTTP 403 is NOT a
#: permission signature: GitHub also returns 403 for secondary rate limits and
#: abuse detection, which are transient and for which retrying is precisely the
#: remedy. Matching on the code would tell an operator waiting out a rate limit
#: that their token lacks a scope — the same species of misdiagnosis this
#: classification exists to end, merely pointing the other way.
_PERMISSION_REFUSAL_SIGNATURES = (
    "resource not accessible by personal access token",
    "resource not accessible by integration",
    "must have admin rights",
    "you do not have permission",
    "requires one of the following scopes",
    "resource protected by organization saml enforcement",
)

#: Wording that makes a failure transient no matter what else it resembles.
#: Checked first, so the classifier fails toward "a plain error worth retrying"
#: rather than toward a confident wrong diagnosis.
_TRANSIENT_SIGNATURES = (
    "rate limit",
    "abuse detection",
    "please retry",
    "try again later",
    "secondary rate",
)


def _is_permission_refusal(stderr: str) -> bool:
    """Whether ``stderr`` is GitHub declining for lack of scope, not a fault."""
    lowered = stderr.lower()
    if any(sig in lowered for sig in _TRANSIENT_SIGNATURES):
        return False
    return any(sig in lowered for sig in _PERMISSION_REFUSAL_SIGNATURES)


def _credential_in_play() -> str:
    """Which credential ``gh`` would have used — the first thing to check."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return f"the token in ${name}"
    return "the credential from `gh auth login`"


@dataclass
class ProjectConfig:
    """GitHub repo configuration from .atdd/config.yaml.

    ``repo`` is the whole of it. #1051 decommissioned the Projects v2 board and
    #1761 removed the ``project_number`` / ``project_id`` fields it left behind:
    they were kept "optional" rather than deleted, which is precisely why the
    board's write and bootstrap paths outlived its read paths. An unread key is
    an invitation to write to it again.
    """

    repo: str

    @classmethod
    def from_config(cls, config_path: Path) -> "ProjectConfig":
        """Load from .atdd/config.yaml."""
        if not config_path.exists():
            raise GitHubClientError(
                f"Config not found: {config_path}\n"
                "Run 'atdd init' first."
            )
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        github = config.get("github")
        if not github:
            raise GitHubClientError(
                "Missing 'github' section in .atdd/config.yaml\n"
                "Run 'atdd init' to set up GitHub integration."
            )
        if not github.get("repo"):
            raise GitHubClientError(
                "Missing 'github.repo' in .atdd/config.yaml\n"
                "Run 'atdd init' to set up GitHub integration."
            )

        return cls(repo=github["repo"])


class GitHubClient:
    """GitHub API client using `gh` CLI."""

    def __init__(self, repo: str):
        self.repo = repo
        self._check_gh()

    def _check_gh(self) -> None:
        """Verify `gh` CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise GitHubClientError(
                    "gh CLI not authenticated.\n"
                    "Run: gh auth login"
                )
        except FileNotFoundError:
            raise GitHubClientError(
                "gh CLI not found.\n"
                "Install: https://cli.github.com"
            )

    def _run_gh(self, args: List[str], input_text: Optional[str] = None) -> str:
        """Run a `gh` command and return stdout."""
        cmd = ["gh"] + args
        logger.debug("gh %s", " ".join(args), extra={"command": args[0] if args else "gh"})
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            input=input_text,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if _is_permission_refusal(stderr):
                raise GitHubPermissionError(
                    f"gh command refused for lack of permission: {' '.join(args)}\n"
                    f"stderr: {stderr}\n"
                    f"GitHub accepted {_credential_in_play()} and then declined the "
                    "operation, so this is a missing scope, not an outage — retrying "
                    "cannot help. Check that the credential actually carries the "
                    "permission this call needs.",
                    command=args, stderr=stderr,
                )
            raise GitHubClientError(
                f"gh command failed: {' '.join(args)}\n"
                f"stderr: {stderr}"
            )
        return result.stdout.strip()

    def _graphql(
        self, query: str, headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a GraphQL query via `gh api graphql`."""
        args = ["api", "graphql", "-f", f"query={query}"]
        for key, value in (headers or {}).items():
            args.extend(["-H", f"{key}: {value}"])
        output = self._run_gh(args)
        data = json.loads(output)
        if "errors" in data:
            raise GitHubClientError(
                f"GraphQL error: {json.dumps(data['errors'], indent=2)}"
            )
        return data

    # -------------------------------------------------------------------------
    # Issues
    # -------------------------------------------------------------------------

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> int:
        """Create a GitHub issue. Returns issue number."""
        args = [
            "issue", "create",
            "--repo", self.repo,
            "--title", title,
            "--body", body,
        ]
        if labels:
            args.extend(["--label", ",".join(labels)])

        output = self._run_gh(args)
        # Output is the issue URL, extract number
        issue_number = int(output.rstrip("/").split("/")[-1])
        logger.info("Created issue #%d: %s", issue_number, title, extra={"issue": issue_number})
        return issue_number

    def get_issue_node_id(self, issue_number: int) -> str:
        """Get the GraphQL node ID for an issue."""
        owner, name = self.repo.split("/")
        data = self._graphql(
            f'{{ repository(owner:"{owner}", name:"{name}") '
            f'{{ issue(number:{issue_number}) {{ id }} }} }}'
        )
        return data["data"]["repository"]["issue"]["id"]

    def close_issue(self, issue_number: int) -> None:
        """Close a GitHub issue."""
        self._run_gh([
            "issue", "close", str(issue_number),
            "--repo", self.repo,
        ])

    def edit_issue(self, issue_number: int, body: str) -> None:
        """Update the body of an existing GitHub issue."""
        self._run_gh([
            "issue", "edit", str(issue_number),
            "--repo", self.repo,
            "--body", body,
        ])

    def add_label(self, issue_number: int, labels: List[str]) -> None:
        """Add labels to an issue."""
        self._run_gh([
            "issue", "edit", str(issue_number),
            "--repo", self.repo,
            "--add-label", ",".join(labels),
        ])

    def remove_label(self, issue_number: int, labels: List[str]) -> None:
        """Remove labels from an issue."""
        self._run_gh([
            "issue", "edit", str(issue_number),
            "--repo", self.repo,
            "--remove-label", ",".join(labels),
        ])

    # -------------------------------------------------------------------------
    # Sub-issues
    # -------------------------------------------------------------------------

    def add_sub_issue(self, parent_number: int, child_number: int) -> None:
        """Link a child issue as a sub-issue of a parent."""
        parent_id = self.get_issue_node_id(parent_number)
        child_id = self.get_issue_node_id(child_number)
        self._graphql(
            f'mutation {{ addSubIssue(input: {{ '
            f'issueId: "{parent_id}", subIssueId: "{child_id}" '
            f'}}) {{ issue {{ id }} subIssue {{ id }} }} }}'
        )
        logger.info("Linked #%d as sub-issue of #%d", child_number, parent_number, extra={"child": child_number, "parent": parent_number})

    def get_all_sub_issues(
        self, label: str, state: str = "OPEN",
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Batch-fetch sub-issues for all issues matching *label* and *state*.

        Single paginated GraphQL query replaces N sequential REST calls to
        ``get_sub_issues()``.  Requires the ``sub_issues`` GraphQL preview
        header.

        Args:
            label: Filter parent issues by this label (e.g. ``"atdd-issue"``).
            state: GitHub issue state filter — ``"OPEN"`` or ``"CLOSED"``.

        Returns:
            Dict mapping parent issue number to its list of sub-issue dicts.
            Sub-issue dicts contain ``number``, ``title``, ``state``, and
            ``labels`` (normalised to lowercase state values for REST parity).
        """
        owner, name = self.repo.split("/")
        state_upper = state.upper()
        result: Dict[int, List[Dict[str, Any]]] = {}
        cursor = None
        headers = {"GraphQL-Features": "sub_issues"}

        while True:
            after = f', after: "{cursor}"' if cursor else ""
            data = self._graphql(
                f'{{ repository(owner:"{owner}", name:"{name}") {{ '
                f'issues(first: 50, labels: ["{label}"], states: [{state_upper}]{after}) {{ '
                f'pageInfo {{ hasNextPage endCursor }} '
                f'nodes {{ '
                f'number '
                f'subIssues(first: 50) {{ nodes {{ '
                f'number title state '
                f'labels(first: 10) {{ nodes {{ name }} }} '
                f'}} }} '
                f'}} }} }} }}',
                headers=headers,
            )

            repo_data = data["data"]["repository"]
            for node in repo_data["issues"]["nodes"]:
                parent_num = node["number"]
                subs = []
                for sub in node["subIssues"]["nodes"]:
                    subs.append({
                        "number": sub["number"],
                        "title": sub["title"],
                        "state": sub["state"].lower(),
                        "labels": [{"name": l["name"]} for l in sub["labels"]["nodes"]],
                    })
                result[parent_num] = subs

            page_info = repo_data["issues"]["pageInfo"]
            if page_info["hasNextPage"]:
                cursor = page_info["endCursor"]
            else:
                break

        logger.debug(
            "Fetched sub-issues for %d %s issues in batch", len(result), state_upper,
            extra={"count": len(result), "state": state_upper},
        )
        return result

    # -------------------------------------------------------------------------
    # Labels
    # -------------------------------------------------------------------------

    def ensure_label(self, name: str, color: str, description: str) -> None:
        """Create or update a label (idempotent)."""
        self._run_gh([
            "label", "create", name,
            "--repo", self.repo,
            "--color", color,
            "--description", description,
            "--force",
        ])

    # -------------------------------------------------------------------------
    # Batch prefetch (validator optimization)
    # -------------------------------------------------------------------------

    def prefetch_validator_data(self) -> Dict[str, Any]:
        """Fetch all data needed by coach validators in minimal API calls.

        Two parallel groups: one REST call set for issues, and two GraphQL
        calls for sub-issues (which need a preview header).

        Returns dict with keys:
            issues, complete_issues, all_open_issues, sub_issues,
            closed_sub_issues
        """
        from concurrent.futures import ThreadPoolExecutor

        results: Dict[str, Any] = {}

        def _fetch_issues():
            """Fetch open atdd-issue, complete, and unfiltered-open issues via REST."""
            results["issues"] = self.list_issues_by_label("atdd-issue")
            results["complete_issues"] = self.list_issues_by_label("atdd:COMPLETE")
            results["all_open_issues"] = self.list_all_open_issues()

        def _fetch_sub_issues():
            """Fetch open + closed sub-issues in two GraphQL calls (needs preview header)."""
            results["sub_issues"] = self.get_all_sub_issues("atdd-issue", "OPEN")
            results["closed_sub_issues"] = self.get_all_sub_issues("atdd-issue", "CLOSED")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(_fetch_issues),
                pool.submit(_fetch_sub_issues),
            ]
            for f in futures:
                f.result()

        return results

    # -------------------------------------------------------------------------
    # Issue queries
    # -------------------------------------------------------------------------

    def list_all_open_issues(
        self, include_body: bool = False,
    ) -> List[Dict[str, Any]]:
        """List *all* open issues, unfiltered by label.

        Used by the label-compliance validator (#296 D005) which asserts
        every open issue carries ``atdd-issue``. The regular
        ``list_issues_by_label`` path pre-filters and therefore cannot see
        unlabeled drift.
        """
        fields = "number,title,labels,state"
        if include_body:
            fields += ",body"
        output = self._run_gh([
            "issue", "list",
            "--repo", self.repo,
            "--state", "open",
            "--json", fields,
            "--limit", "500",
        ])
        return json.loads(output) if output else []

    def list_issues_by_label(
        self, label: str, include_body: bool = True, state: str = "open",
    ) -> List[Dict[str, Any]]:
        """List issues with a given label.

        ``state`` is passed to ``gh issue list --state`` ("open" by default,
        "closed", or "all"). Closed issues are needed to reconcile stale
        phase labels on already-closed atdd-issues (#1284).
        """
        fields = "number,title,labels,state"
        if include_body:
            fields += ",body"
        output = self._run_gh([
            "issue", "list",
            "--repo", self.repo,
            "--label", label,
            "--state", state,
            "--json", fields,
            "--limit", "100",
        ])
        return json.loads(output) if output else []

    def get_sub_issues(self, issue_number: int) -> List[Dict[str, Any]]:
        """Get sub-issues of a parent issue."""
        output = self._run_gh([
            "api", f"repos/{self.repo}/issues/{issue_number}/sub_issues",
            "--paginate",
        ])
        return json.loads(output) if output else []

    def list_open_issues(
        self,
        label: Optional[str] = None,
        limit: int = 30,
        assignee: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List open issues with optional filters.

        Args:
            label: Filter by label name.
            limit: Maximum number of issues to return.
            assignee: Filter by assignee login.

        Returns:
            List of issue dicts with number, title, labels, createdAt.
        """
        args = [
            "issue", "list",
            "--repo", self.repo,
            "--state", "open",
            "--json", "number,title,labels,createdAt",
            "--limit", str(limit),
        ]
        if label:
            args += ["--label", label]
        if assignee:
            args += ["--assignee", assignee]
        output = self._run_gh(args)
        return json.loads(output) if output else []

    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get issue details."""
        output = self._run_gh([
            "issue", "view", str(issue_number),
            "--repo", self.repo,
            "--json", "number,title,state,labels,body",
        ])
        return json.loads(output)

    def get_closing_merge_commit(self, issue_number: int) -> Optional[str]:
        """The SHA of the commit that merged the PR which closed this issue.

        This is what "the change the PR landed" resolves to once the branch is gone
        (#1611). ``None`` when no PR closed the issue, or none of them merged.
        """
        output = self._run_gh([
            "issue", "view", str(issue_number),
            "--repo", self.repo,
            "--json", "closedByPullRequestsReferences",
        ])
        references = (json.loads(output) or {}).get("closedByPullRequestsReferences") or []

        # Newest first: if an issue was closed, reopened and closed again, the work
        # its artifacts describe is what the *latest* merge landed.
        numbers = sorted(
            (r.get("number") for r in references if r.get("number")), reverse=True,
        )
        for number in numbers:
            pr = json.loads(self._run_gh([
                "pr", "view", str(number),
                "--repo", self.repo,
                "--json", "state,mergeCommit",
            ]) or "{}")
            if pr.get("state") != "MERGED":
                continue
            sha = (pr.get("mergeCommit") or {}).get("oid")
            if sha:
                return sha
        return None
