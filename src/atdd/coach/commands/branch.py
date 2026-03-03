"""
Branch (worktree) creation from ATDD issue metadata.

Creates a git worktree with the correct prefix/slug naming derived from
the issue manifest. Updates the GitHub "ATDD: Branch" field and refreshes
the VS Code workspace file.

Usage:
    atdd branch 69                        # Create worktree from issue #69
    atdd branch 69 --prefix fix           # Override prefix (default: from type)

Convention: CLAUDE.md git.branching
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from atdd.coach.commands.issue import ALLOWED_BRANCH_PREFIXES, TYPE_TO_PREFIX
from atdd.coach.github import GitHubClient, GitHubClientError, ProjectConfig

logger = logging.getLogger(__name__)


class BranchManager:
    """Create worktree branches from ATDD issue metadata."""

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def _load_manifest(self):
        if not self.manifest_file.exists():
            return {}
        with open(self.manifest_file) as f:
            return yaml.safe_load(f) or {}

    def _find_issue(self, issue_number: int):
        """Find an issue in the manifest by number. Returns the entry or None."""
        manifest = self._load_manifest()
        for entry in manifest.get("sessions", []):
            if entry.get("issue_number") == issue_number:
                return entry
        return None

    def branch(self, issue_number: int, prefix: Optional[str] = None) -> int:
        """Create a worktree branch for the given issue.

        Args:
            issue_number: GitHub issue number.
            prefix: Override branch prefix (e.g. "fix"). Derived from type if None.

        Returns:
            0 on success, 1 on error.
        """
        from atdd.coach.utils.repo import detect_worktree_layout

        # Verify worktree-ready layout
        layout = detect_worktree_layout(self.target_dir)
        if layout != "worktree-ready":
            print(
                f"Error: Repository layout is '{layout}', expected 'worktree-ready'.\n"
                "Run `atdd init --worktree-layout` from the repo root first."
            )
            return 1

        # Look up issue in manifest
        entry = self._find_issue(issue_number)
        if entry is None:
            print(
                f"Error: Issue #{issue_number} not found in manifest.\n"
                f"Create it first with: atdd new <slug>"
            )
            return 1

        slug = entry["slug"]
        issue_type = entry.get("type", "implementation")

        # Derive prefix
        if prefix is None:
            prefix = TYPE_TO_PREFIX.get(issue_type, "feat")

        if prefix not in ALLOWED_BRANCH_PREFIXES:
            print(
                f"Error: Prefix '{prefix}' is not allowed.\n"
                f"Allowed: {', '.join(ALLOWED_BRANCH_PREFIXES)}"
            )
            return 1

        branch_name = f"{prefix}/{slug}"
        worktree_dir_name = f"{prefix}-{slug}"
        worktree_path = self.target_dir.parent / worktree_dir_name

        # Check if worktree directory already exists
        if worktree_path.exists():
            print(
                f"Error: Directory already exists: {worktree_path}\n"
                f"Either remove it or work in it directly:\n"
                f"  cd {worktree_path}"
            )
            return 1

        # Fetch remote to check for existing remote branch
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )

        # Check if remote branch exists
        result = subprocess.run(
            ["git", "branch", "-r", "--list", f"origin/{branch_name}"],
            capture_output=True, text=True, timeout=10,
            cwd=self.target_dir,
        )
        remote_exists = bool(result.stdout.strip())

        # Create worktree
        if remote_exists:
            cmd = [
                "git", "worktree", "add",
                str(worktree_path),
                f"origin/{branch_name}",
            ]
            print(f"Attaching to existing remote branch: {branch_name}")
        else:
            cmd = [
                "git", "worktree", "add",
                str(worktree_path),
                "-b", branch_name,
            ]
            print(f"Creating new branch: {branch_name}")

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )
        if result.returncode != 0:
            print(f"Error: git worktree add failed:\n{result.stderr.strip()}")
            return 1

        print(f"  Worktree: {worktree_path}")

        # Update GitHub "ATDD: Branch" field
        try:
            proj = ProjectConfig.from_config(self.config_file)
            client = GitHubClient(
                repo=proj.repo,
                project_id=proj.project_id,
            )
            item_id = client.get_project_item_id(issue_number)
            if item_id:
                fields = client.get_project_fields()
                if "ATDD: Branch" in fields:
                    client.set_project_field_text(
                        item_id, fields["ATDD: Branch"]["id"], branch_name,
                    )
                    print(f"  Updated ATDD: Branch → {branch_name}")
            else:
                print("  Warning: Issue not found in Project; Branch field not updated.")
        except GitHubClientError as e:
            print(f"  Warning: Could not update Branch field: {e}")

        # Refresh VS Code workspace file
        try:
            from atdd.coach.commands.initializer import write_workspace
            write_workspace(self.target_dir)
        except Exception as e:
            print(f"  Warning: Could not refresh workspace file: {e}")

        print(f"\n  cd {worktree_path}")
        return 0
