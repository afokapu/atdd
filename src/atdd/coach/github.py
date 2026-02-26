"""
GitHub API client for ATDD issue tracking.

Wraps `gh` CLI for GitHub Issues, Projects v2, sub-issues, and labels.
Requires `gh` CLI to be installed and authenticated with `project` scope.

Usage:
    client = GitHubClient(repo="afokapu/atdd")
    issue_number = client.create_issue(title="...", body="...", labels=["atdd-session"])
    client.add_sub_issue(parent_number=11, child_number=12)
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


@dataclass
class ProjectConfig:
    """GitHub Project v2 configuration from .atdd/config.yaml."""

    repo: str
    project_number: int
    project_id: str

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

        return cls(
            repo=github["repo"],
            project_number=github["project_number"],
            project_id=github["project_id"],
        )


class GitHubClient:
    """GitHub API client using `gh` CLI."""

    def __init__(self, repo: str, project_id: Optional[str] = None):
        self.repo = repo
        self.project_id = project_id
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
        logger.debug("gh %s", " ".join(args))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            input=input_text,
        )
        if result.returncode != 0:
            raise GitHubClientError(
                f"gh command failed: {' '.join(args)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def _graphql(self, query: str) -> Dict[str, Any]:
        """Execute a GraphQL query via `gh api graphql`."""
        output = self._run_gh(["api", "graphql", "-f", f"query={query}"])
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
        logger.info("Created issue #%d: %s", issue_number, title)
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
        logger.info("Linked #%d as sub-issue of #%d", child_number, parent_number)

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
    # Projects v2
    # -------------------------------------------------------------------------

    def add_issue_to_project(self, issue_number: int) -> str:
        """Add an issue to the Project v2. Returns project item ID."""
        if not self.project_id:
            raise GitHubClientError("No project_id configured")

        node_id = self.get_issue_node_id(issue_number)
        data = self._graphql(
            f'mutation {{ addProjectV2ItemById(input: {{ '
            f'projectId: "{self.project_id}", contentId: "{node_id}" '
            f'}}) {{ item {{ id }} }} }}'
        )
        item_id = data["data"]["addProjectV2ItemById"]["item"]["id"]
        logger.info("Added #%d to project (item: %s)", issue_number, item_id)
        return item_id

    def set_project_field_text(
        self, item_id: str, field_id: str, value: str
    ) -> None:
        """Set a text field on a project item."""
        self._graphql(
            f'mutation {{ updateProjectV2ItemFieldValue(input: {{ '
            f'projectId: "{self.project_id}", itemId: "{item_id}", '
            f'fieldId: "{field_id}", value: {{ text: "{value}" }} '
            f'}}) {{ projectV2Item {{ id }} }} }}'
        )

    def set_project_field_number(
        self, item_id: str, field_id: str, value: float
    ) -> None:
        """Set a number field on a project item."""
        self._graphql(
            f'mutation {{ updateProjectV2ItemFieldValue(input: {{ '
            f'projectId: "{self.project_id}", itemId: "{item_id}", '
            f'fieldId: "{field_id}", value: {{ number: {value} }} '
            f'}}) {{ projectV2Item {{ id }} }} }}'
        )

    def set_project_field_select(
        self, item_id: str, field_id: str, option_id: str
    ) -> None:
        """Set a single-select field on a project item."""
        self._graphql(
            f'mutation {{ updateProjectV2ItemFieldValue(input: {{ '
            f'projectId: "{self.project_id}", itemId: "{item_id}", '
            f'fieldId: "{field_id}", value: {{ singleSelectOptionId: "{option_id}" }} '
            f'}}) {{ projectV2Item {{ id }} }} }}'
        )

    def rename_project_field(self, field_id: str, new_name: str) -> None:
        """Rename a Project v2 field in-place (preserves existing values)."""
        self._graphql(
            f'mutation {{ updateProjectV2Field(input: {{ '
            f'fieldId: "{field_id}", name: "{new_name}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id name }} '
            f'... on ProjectV2SingleSelectField {{ id name }} }} }} }}'
        )
        logger.info("Renamed field %s → %s", field_id, new_name)

    def delete_project_field(self, field_id: str) -> None:
        """Delete a Project v2 field."""
        self._graphql(
            f'mutation {{ deleteProjectV2Field(input: {{ '
            f'fieldId: "{field_id}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} '
            f'... on ProjectV2SingleSelectField {{ id }} }} }} }}'
        )
        logger.info("Deleted field %s", field_id)

    def get_project_fields(self) -> Dict[str, Any]:
        """Fetch all project fields with their IDs and option IDs."""
        if not self.project_id:
            raise GitHubClientError("No project_id configured")

        data = self._graphql(
            f'{{ node(id: "{self.project_id}") {{ '
            f'... on ProjectV2 {{ fields(first: 30) {{ nodes {{ '
            f'... on ProjectV2Field {{ id name dataType }} '
            f'... on ProjectV2SingleSelectField {{ id name dataType options {{ id name }} }} '
            f'}} }} }} }} }}'
        )
        fields = {}
        for node in data["data"]["node"]["fields"]["nodes"]:
            name = node.get("name")
            if name:
                fields[name] = {
                    "id": node["id"],
                    "data_type": node.get("dataType"),
                }
                if "options" in node:
                    fields[name]["options"] = {
                        opt["name"]: opt["id"] for opt in node["options"]
                    }
        return fields

    def get_project_item_id(self, issue_number: int) -> Optional[str]:
        """Get the project item ID for an issue already in the project."""
        if not self.project_id:
            return None
        owner, name = self.repo.split("/")
        data = self._graphql(
            f'{{ repository(owner:"{owner}", name:"{name}") {{ '
            f'issue(number:{issue_number}) {{ '
            f'projectItems(first: 10) {{ nodes {{ id project {{ id }} }} }} '
            f'}} }} }}'
        )
        for item in data["data"]["repository"]["issue"]["projectItems"]["nodes"]:
            if item["project"]["id"] == self.project_id:
                return item["id"]
        return None

    def get_project_item_field_values(
        self, item_id: str
    ) -> Dict[str, Any]:
        """Read all field values for a project item.

        Returns:
            Dict mapping field name to its value (string for text/number,
            option name for single-select).
        """
        if not self.project_id:
            raise GitHubClientError("No project_id configured")

        data = self._graphql(
            f'{{ node(id: "{item_id}") {{ '
            f'... on ProjectV2Item {{ '
            f'fieldValues(first: 30) {{ nodes {{ '
            f'... on ProjectV2ItemFieldTextValue {{ text field {{ ... on ProjectV2Field {{ name }} }} }} '
            f'... on ProjectV2ItemFieldNumberValue {{ number field {{ ... on ProjectV2Field {{ name }} }} }} '
            f'... on ProjectV2ItemFieldSingleSelectValue {{ name field {{ ... on ProjectV2SingleSelectField {{ name }} }} }} '
            f'}} }} }} }} }}'
        )
        values = {}
        for node in data["data"]["node"]["fieldValues"]["nodes"]:
            field_name = node.get("field", {}).get("name")
            if not field_name:
                continue
            if "text" in node:
                values[field_name] = node["text"]
            elif "number" in node:
                values[field_name] = node["number"]
            elif "name" in node and node["name"]:
                values[field_name] = node["name"]
        return values

    # -------------------------------------------------------------------------
    # Issue queries
    # -------------------------------------------------------------------------

    def list_issues_by_label(self, label: str) -> List[Dict[str, Any]]:
        """List open issues with a given label."""
        output = self._run_gh([
            "issue", "list",
            "--repo", self.repo,
            "--label", label,
            "--state", "open",
            "--json", "number,title,labels,state",
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

    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get issue details."""
        output = self._run_gh([
            "issue", "view", str(issue_number),
            "--repo", self.repo,
            "--json", "number,title,state,labels,body",
        ])
        return json.loads(output)
