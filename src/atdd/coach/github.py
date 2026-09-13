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
from urllib.parse import quote, unquote
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def _normalise_sub_issue(row: Dict[str, Any]) -> Dict[str, Any]:
    """One REST sub-issue row in the shape callers already read (#1989).

    The GraphQL form lowercased ``state`` "for REST parity" and flattened labels
    to ``[{"name": ...}]``. REST already reports state lowercase and returns full
    label objects, so only the label reduction is real work — but it is written
    out rather than assumed, because the parity claim is the whole contract.
    """
    return {
        "number": row.get("number"),
        "title": row.get("title"),
        "state": str(row.get("state") or "").lower(),
        "labels": [{"name": lbl.get("name")} for lbl in (row.get("labels") or [])],
    }


def normalise_rest_issues(
    rows: List[Dict[str, Any]], *, fields: str,
) -> List[Dict[str, Any]]:
    """REST `/issues` rows reduced to exactly what `gh issue list --json` returns.

    Moving the listing off GraphQL (#1930) is a TRANSPORT change; the contract
    every caller reads must not move with it. Three differences have to be
    absorbed here rather than pushed onto callers:

    * REST's ``/issues`` includes pull requests. Measured on this repository, the
      unlabelled listing is 319 over REST against 296 over GraphQL — 23 PRs. The
      count goes UP, so the mistake looks like health.
    * REST reports ``state`` lowercase, ``gh`` reports it uppercase, and callers
      compare against both forms in different modules. The listing keeps gh's.
    * REST returns roughly thirty keys per issue. Only the requested ones are
      kept, so payload and shape both match what callers had.
    """
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        if row.get("pull_request") is not None:
            continue                      # a PR, not an issue
        item: Dict[str, Any] = {}
        for field in wanted:
            value = row.get(field)
            if field == "state":
                value = str(value or "").upper()
            elif field == "body":
                value = value or ""       # REST gives null, gh gives ""
            elif field == "labels":
                value = [{"name": lbl.get("name")} for lbl in (value or [])]
            item[field] = value
        out.append(item)
    return out


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


class GitHubResultTruncated(RuntimeError):
    """A listing hit its fetch cap, so completeness is UNKNOWN (#1903).

    Distinct from an API failure: the call succeeded. What it did not do is
    answer the question asked of it, and a prefix of the answer read as the whole
    answer is how a validator reports PASS over a sample.
    """


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
        """Verify `gh` is available and the credential can reach the API.

        `gh auth status` resolves the IDENTITY — it calls ``/user``. That is a
        different question from "can this credential do the work", and the two
        come apart exactly where it matters: the Actions ``GITHUB_TOKEN`` is an
        installation token that cannot call ``/user`` while being able to perform
        every repo-scoped call it was issued for, and a repo-scoped fine-grained
        PAT fails the same check for the same reason.

        So a non-zero status is a HINT and a real call is the VERDICT (#1937).
        The healthy path is unchanged — one ``gh auth status`` — and the second
        call is spent only on the path that was about to refuse anyway.
        """
        try:
            status = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError:
            raise GitHubClientError(
                "gh CLI not found.\n"
                "Install: https://cli.github.com"
            )
        if status.returncode == 0:
            return

        # Probe with a REPO-scoped call, never ``/user``: ``/user`` is the exact
        # call the installation token cannot make, so probing with it would
        # reproduce the bug inside the fix.
        try:
            probe = subprocess.run(
                ["gh", "api", f"repos/{self.repo}", "--jq", ".name"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError:  # pragma: no cover - gh vanished mid-check
            raise GitHubClientError(
                "gh CLI not found.\n"
                "Install: https://cli.github.com"
            )
        if probe.returncode == 0:
            return

        # Both failed: a real refusal. Quote what gh said rather than discarding
        # it — "Run: gh auth login" addresses nobody in CI, and the stderr is the
        # only thing that says which of the two actually went wrong.
        raise GitHubClientError(
            "gh cannot reach the GitHub API with the current credential.\n"
            f"gh auth status said: {status.stderr.strip() or '(no stderr)'}\n"
            f"the probe call said: {probe.stderr.strip() or '(no stderr)'}\n"
            "On a workstation: gh auth login. In CI: check the job's GH_TOKEN "
            "and the workflow's permissions: block."
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
        """Add labels to an issue, over REST.

        `gh issue edit` is GraphQL-backed, so a phase transition could read its
        issue and then fail to swap the label — leaving the store advanced and
        GitHub not. See :meth:`get_issue` for the measurement.
        """
        args = ["api", f"repos/{self.repo}/issues/{issue_number}/labels"]
        for label in labels:
            args += ["-f", f"labels[]={label}"]
        self._run_gh(args)

    def remove_label(self, issue_number: int, labels: List[str]) -> None:
        """Remove labels from an issue, over REST.

        One DELETE per label — REST has no batch form. A label that is already
        absent returns 404, which is the desired end state rather than an error,
        so it is not raised.
        """
        for label in labels:
            try:
                self._run_gh([
                    "api", "--method", "DELETE",
                    f"repos/{self.repo}/issues/{issue_number}/labels/{label}",
                ])
            except GitHubClientError as exc:
                if "404" not in str(exc) and "Label does not exist" not in str(exc):
                    raise
                logger.debug(
                    "remove_label: label already absent",
                    extra={"issue": issue_number, "label": label},
                )

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

        REST, not GraphQL (#1989). This was a paginated GraphQL crawl needing the
        ``sub_issues`` preview header, and it was the LAST GraphQL call left in
        the validator prefetch — #1930 had already moved the listing to REST.
        One call failing took all five prefetch keys down with it (the prefetch
        marks every key with the same exception), so an exhausted GraphQL bucket
        reported twelve validators as COULD_NOT_CHECK even though their own data
        had been fetched successfully over REST.

        N+1 is avoided by the listing itself: REST's ``/issues`` rows carry
        ``sub_issues_summary``, so a parent with no children is known to have
        none without asking. Measured on this repository, 24 of 987 atdd-issues
        have any sub-issue at all, so this is ~34 REST calls rather than 987 —
        which matters because Actions' GITHUB_TOKEN is capped at 1000 REST
        requests/hour/repo, and a naive per-parent fetch would trade one
        exhausted bucket for another.

        Args:
            label: Filter parent issues by this label (e.g. ``"atdd-issue"``).
            state: Issue state filter — ``"OPEN"`` or ``"CLOSED"``.

        Returns:
            Dict mapping parent issue number to its list of sub-issue dicts.
            Sub-issue dicts contain ``number``, ``title``, ``state``, and
            ``labels`` — the shape the GraphQL form returned, unchanged.
        """
        from concurrent.futures import ThreadPoolExecutor

        parents = self._list_issues_complete(
            [f"state={state.lower()}", f"labels={quote(label, safe='')}"],
            "number,sub_issues_summary",
        )

        result: Dict[int, List[Dict[str, Any]]] = {}
        owed: List[int] = []
        for parent in parents:
            number = parent["number"]
            summary = parent.get("sub_issues_summary") or {}
            if summary.get("total", 0):
                owed.append(number)
            else:
                result[number] = []

        if owed:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for number, subs in zip(owed, pool.map(self.get_sub_issues, owed)):
                    result[number] = [_normalise_sub_issue(row) for row in subs]

        return result

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

        Two parallel groups, both REST (#1989 moved the sub-issue half off
        GraphQL). Each key carries its own outcome: a query that fails records
        its exception against its own key instead of taking the others down.

        Returns dict with keys:
            issues, complete_issues, all_open_issues, sub_issues,
            closed_sub_issues
        """
        from concurrent.futures import ThreadPoolExecutor

        results: Dict[str, Any] = {}

        def _record(key: str, fetch):
            """Run one fetch and keep its OUTCOME against its OWN key.

            Per-key, deliberately (#1989). A failure used to propagate out of this
            method, and the caller marked all five keys with the same exception —
            so one unavailable query reported twelve validators as COULD_NOT_CHECK
            when only some of them had lost their data. An unestablished verdict
            must be attributable to the query that was not established, or the
            refusal says less than it knows.
            """
            try:
                results[key] = fetch()
            except Exception as exc:  # noqa: BLE001 — recorded, then re-raised by the fixture
                results[key] = exc

        def _fetch_issues():
            """Fetch open atdd-issue, complete, and unfiltered-open issues via REST."""
            _record("issues", lambda: self.list_issues_by_label("atdd-issue"))
            _record("complete_issues", lambda: self.list_issues_by_label("atdd:COMPLETE"))
            _record("all_open_issues", self.list_all_open_issues)

        def _fetch_sub_issues():
            """Fetch open + closed sub-issues over REST."""
            _record("sub_issues", lambda: self.get_all_sub_issues("atdd-issue", "OPEN"))
            _record("closed_sub_issues", lambda: self.get_all_sub_issues("atdd-issue", "CLOSED"))

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

    # `gh issue list --limit N` paginates internally up to N and then STOPS,
    # returning N rows with no indication that more exist (#1903). A validator
    # behind a capped fetch reports PASS over a sample: measured, 100 of 289 open
    # atdd-issues, and the 100 were the NEWEST — so ten issues labelled minutes
    # earlier sat outside the window and the label validator passed without ever
    # seeing them.
    #
    # The cap is set far above any plausible repository, and reaching it RAISES.
    # At exactly N rows the result is indistinguishable from "there were more",
    # so the honest verdict is that completeness is unknown — and unknown is not
    # clean. `get_sub_issues`, ten lines below, has always used --paginate; the
    # two read identically at the call site, which is why nothing marked one as a
    # sample and the other as an answer.
    _ISSUE_FETCH_CAP = 5000
    _REST_PAGE_SIZE = 100

    def _list_issues_complete(
        self, selector: List[str], fields: str,
    ) -> List[Dict[str, Any]]:
        """Every issue matching *selector*, or an error — never a silent prefix."""
        # REST, not `gh issue list` (#1930). That subcommand is `POST /graphql`
        # (verified with GH_DEBUG=api), which put the entire coach validator
        # surface on the one bucket that keeps failing in CI — three PRs and a
        # publish run were blocked by "API rate limit already exceeded" while
        # REST stood at 4823/5000. `--paginate` merges the pages into a single
        # JSON array, so completeness is still decided here rather than by a
        # `--limit` the caller cannot see.
        query = "&".join([*selector, f"per_page={self._REST_PAGE_SIZE}"])
        output = self._run_gh([
            "api", "--paginate", f"repos/{self.repo}/issues?{query}",
        ])
        raw = json.loads(output) if output else []
        data = normalise_rest_issues(raw, fields=fields)
        if len(data) >= self._ISSUE_FETCH_CAP:
            raise GitHubResultTruncated(
                f"gh returned {len(data)} issues, the fetch cap. Whether more "
                f"exist is UNKNOWN, so this is not a complete answer and callers "
                # Unencoded for the message: the request needs `atdd%3ACOMPLETE`,
                # an operator reading the refusal needs `atdd:COMPLETE`.
                f"must not treat it as one. Selector: "
                f"{' '.join(unquote(part) for part in selector)}"
            )
        return data


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
        return self._list_issues_complete(["state=open"], fields)

    def list_issues_by_label(
        self, label: str, include_body: bool = True, state: str = "open",
    ) -> List[Dict[str, Any]]:
        """List issues with a given label.

        ``state`` is "open" (default), "closed" or "all" — the REST `/issues`
        filter takes the same three values gh's `--state` did. Closed issues are
        needed to reconcile stale phase labels on already-closed atdd-issues
        (#1284).
        """
        fields = "number,title,labels,state"
        if include_body:
            fields += ",body"
        return self._list_issues_complete(
            [f"state={state}", f"labels={quote(label, safe='')}"], fields,
        )

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
        """Get issue details, over REST.

        `gh issue view --json` is GraphQL-backed, and GraphQL is the bucket that
        runs out: measured 2026-09-13, it refused every call with "rate limit
        already exceeded" while REST reported 4644/5000 remaining. This read
        gates every lifecycle transition, so an exhausted GraphQL bucket stalls
        the whole ladder while the healthy transport sits idle. #1930/Y011 made
        the same swap for `gh issue list`; `gh_failure.py` documents why.

        REST reports `state` lowercase where the GraphQL projection reports it
        upper, so it is normalised here — callers compare against "OPEN".
        """
        output = self._run_gh([
            "api", f"repos/{self.repo}/issues/{issue_number}",
            "--jq", "{number,title,state,labels,body}",
        ])
        issue = json.loads(output)
        if isinstance(issue.get("state"), str):
            issue["state"] = issue["state"].upper()
        return issue

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
