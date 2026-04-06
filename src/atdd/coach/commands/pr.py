"""
PR creation from ATDD issue metadata.

Creates a GitHub pull request with:
- Conventional-commit title derived from issue type
- Closing keyword (``Closes #N``) for automatic issue closure
- WMBT sub-issue summary in the PR body
- Issue metadata table

Usage:
    atdd pr 69                              # Create PR for issue #69
    atdd pr 69 --draft                      # Create as draft PR
    atdd pr 69 --base develop               # Override base branch
    atdd pr 69 --auto                       # Create PR and enable auto-merge
    atdd pr 69 --auto --merge-strategy rebase

Convention: CLAUDE.md git.commits, issues.prohibited_commands
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from atdd.coach.commands.issue import TYPE_TO_PREFIX

logger = logging.getLogger(__name__)


class PRManager:
    """Create pull requests from ATDD issue metadata."""

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def _load_manifest(self) -> dict:
        if not self.manifest_file.exists():
            logger.warning("Manifest not found: %s", self.manifest_file, extra={"path": str(self.manifest_file)})
            return {}
        with open(self.manifest_file) as f:
            return yaml.safe_load(f) or {}

    def _find_issue_in_manifest(self, issue_number: int) -> Optional[dict]:
        """Find an issue in the manifest by number."""
        manifest = self._load_manifest()
        for entry in manifest.get("sessions", []):
            if entry.get("issue_number") == issue_number:
                return entry
        return None

    def _get_repo(self) -> Optional[str]:
        """Read repo slug from .atdd/config.yaml."""
        if not self.config_file.exists():
            return None
        cfg = yaml.safe_load(self.config_file.read_text()) or {}
        return cfg.get("github", {}).get("repo")

    def _fetch_issue(self, issue_number: int) -> Optional[dict]:
        """Fetch issue details from GitHub via gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "issue", "view", str(issue_number),
                 "--json", "number,title,state,labels,body"],
                capture_output=True, text=True, timeout=15,
                cwd=self.target_dir,
            )
            if result.returncode != 0:
                logger.error("gh issue view failed: %s", result.stderr.strip(), extra={"stderr": result.stderr.strip()})
                return None
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
            logger.error("Failed to fetch issue #%d: %s", issue_number, exc, extra={"issue": issue_number, "error": str(exc)})
            return None

    def _fetch_sub_issues(self, issue_number: int) -> list:
        """Fetch WMBT sub-issues for a parent issue."""
        repo = self._get_repo()
        if not repo:
            logger.warning("No repo configured; cannot fetch sub-issues", extra={"config": str(self.config_file)})
            return []
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}/issues/{issue_number}/sub_issues",
                 "--paginate"],
                capture_output=True, text=True, timeout=15,
                cwd=self.target_dir,
            )
            if result.returncode != 0:
                logger.debug("Sub-issues API failed: %s", result.stderr.strip(), extra={"stderr": result.stderr.strip()})
                return []
            return json.loads(result.stdout) if result.stdout.strip() else []
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
            logger.debug("Failed to fetch sub-issues: %s", exc, extra={"error": str(exc)})
            return []

    def _detect_branch(self) -> Optional[str]:
        """Detect current git branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=self.target_dir,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                if branch and branch != "HEAD":
                    return branch
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _existing_pr_for_branch(self, branch: str) -> Optional[str]:
        """Check if a PR already exists for the given branch. Returns PR URL or None."""
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch,
                 "--json", "number,url", "--jq", ".[0].url"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _build_pr_title(
        self,
        issue_title: str,
        issue_type: str,
        issue_number: int,
    ) -> str:
        """Build PR title using conventional commit format.

        Examples:
            feat(atdd): Pr Auto Close (#182)
            fix(atdd): broken urn validation (#99)
        """
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")

        # If the issue title already has a conventional prefix, use it as-is
        conventional_prefixes = ("feat:", "fix:", "refactor:", "chore:", "docs:", "devops:")
        title_lower = issue_title.lower().strip()
        for cp in conventional_prefixes:
            if title_lower.startswith(cp):
                # Already conventional — append issue ref if missing
                if f"#{issue_number}" not in issue_title:
                    return f"{issue_title} (#{issue_number})"
                return issue_title

        # Strip leading type labels like "feat(atdd):" if present via labels
        clean_title = issue_title.strip()

        return f"{prefix}: {clean_title} (#{issue_number})"

    def _build_pr_body(
        self,
        issue_number: int,
        issue_data: dict,
        sub_issues: list,
        manifest_entry: Optional[dict],
    ) -> str:
        """Build PR body with closing keywords and WMBT summary."""
        lines = []

        # Closing keyword — GitHub auto-closes the issue on merge
        lines.append(f"Closes #{issue_number}")
        lines.append("")

        # WMBT sub-issues summary
        if sub_issues:
            lines.append("## WMBT Sub-Issues")
            lines.append("")
            for si in sub_issues:
                si_number = si.get("number", "?")
                si_title = si.get("title", "Untitled")
                si_state = si.get("state", "open")
                check = "x" if si_state in ("closed", "CLOSED") else " "
                lines.append(f"- [{check}] #{si_number} — {si_title}")
            lines.append("")

        # Issue metadata table
        lines.append("## Issue Metadata")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Issue | #{issue_number} |")

        if manifest_entry:
            if manifest_entry.get("type"):
                lines.append(f"| Type | {manifest_entry['type']} |")
            if manifest_entry.get("slug"):
                lines.append(f"| Slug | {manifest_entry['slug']} |")
            if manifest_entry.get("train"):
                lines.append(f"| Train | {manifest_entry['train']} |")
            if manifest_entry.get("archetypes"):
                lines.append(f"| Archetypes | {manifest_entry['archetypes']} |")

        # Labels from issue
        labels = issue_data.get("labels", [])
        if labels:
            label_names = [lbl.get("name", lbl) if isinstance(lbl, dict) else str(lbl) for lbl in labels]
            lines.append(f"| Labels | {', '.join(label_names)} |")

        lines.append("")
        lines.append("---")
        lines.append("PR created by `atdd pr`.")

        return "\n".join(lines)

    def _check_auto_merge_enabled(self) -> bool:
        """Check if the repository has auto-merge enabled."""
        try:
            result = subprocess.run(
                ["gh", "api", "repos/{owner}/{repo}",
                 "--jq", ".allow_auto_merge"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if result.returncode == 0:
                return result.stdout.strip().lower() == "true"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def _enable_auto_merge(self, pr_url: str, strategy: str) -> bool:
        """Enable auto-merge on a PR via gh CLI.

        Args:
            pr_url: The PR URL returned by gh pr create.
            strategy: One of 'squash', 'merge', 'rebase'.

        Returns:
            True if auto-merge was enabled successfully.
        """
        cmd = ["gh", "pr", "merge", pr_url, "--auto", f"--{strategy}"]
        logger.info("Enabling auto-merge: %s", " ".join(cmd), extra={"cmd": " ".join(cmd), "strategy": strategy})

        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=15,
                cwd=self.target_dir,
            )
            if result.returncode == 0:
                return True
            logger.error("gh pr merge --auto failed: %s", result.stderr.strip(), extra={"stderr": result.stderr.strip()})
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.error("Failed to enable auto-merge: %s", exc, extra={"error": str(exc)})
            return False

    def pr(
        self,
        issue_number: int,
        draft: bool = False,
        base: str = "main",
        auto_merge: bool = False,
        merge_strategy: str = "squash",
    ) -> int:
        """Create a PR linked to the given issue number.

        Args:
            issue_number: GitHub issue number.
            draft: If True, create as a draft PR.
            base: Base branch for the PR (default: main).
            auto_merge: If True, enable auto-merge after PR creation.
            merge_strategy: Merge strategy for auto-merge (squash, merge, rebase).

        Returns:
            0 on success, 1 on error.
        """
        logger.info("Creating PR for issue #%d", issue_number, extra={"issue": issue_number})

        # 1. Detect current branch
        branch = self._detect_branch()
        if not branch:
            print("Error: Could not detect current git branch.")
            print("Make sure you are in a git worktree or repository.")
            return 1

        if branch in ("main", "master"):
            print(f"Error: Cannot create PR from '{branch}' branch.")
            print("Switch to a feature branch first: atdd branch <N>")
            return 1

        logger.info("Branch: %s", branch, extra={"branch": branch})

        # 2. Check for existing PR
        existing = self._existing_pr_for_branch(branch)
        if existing:
            print(f"PR already exists for branch '{branch}':")
            print(f"  {existing}")
            return 0

        # 3. Fetch issue metadata from GitHub
        issue_data = self._fetch_issue(issue_number)
        if not issue_data:
            print(f"Error: Could not fetch issue #{issue_number} from GitHub.")
            print("Verify the issue exists and `gh` CLI is authenticated.")
            return 1

        issue_title = issue_data.get("title", f"Issue #{issue_number}")
        logger.info("Issue title: %s", issue_title, extra={"title": issue_title})

        # 4. Look up manifest for type/slug metadata
        manifest_entry = self._find_issue_in_manifest(issue_number)
        issue_type = (manifest_entry or {}).get("type", "implementation")
        logger.info("Issue type: %s (from manifest: %s)", issue_type, manifest_entry is not None, extra={"type": issue_type, "from_manifest": manifest_entry is not None})

        # 5. Fetch WMBT sub-issues
        sub_issues = self._fetch_sub_issues(issue_number)
        logger.info("WMBT sub-issues found: %d", len(sub_issues), extra={"count": len(sub_issues)})

        # 6. Build PR title and body
        pr_title = self._build_pr_title(issue_title, issue_type, issue_number)
        pr_body = self._build_pr_body(issue_number, issue_data, sub_issues, manifest_entry)

        logger.info("PR title: %s", pr_title, extra={"pr_title": pr_title})
        logger.debug("PR body:\n%s", pr_body, extra={"pr_body_length": len(pr_body)})

        # 7. Ensure branch is pushed to remote
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )
        if push_result.returncode != 0:
            stderr = push_result.stderr.strip()
            # "Everything up-to-date" is fine
            if "Everything up-to-date" not in stderr and "set up to track" not in stderr:
                print(f"Warning: git push may have failed: {stderr}")

        # 8. Create the PR via gh CLI
        cmd = [
            "gh", "pr", "create",
            "--title", pr_title,
            "--body", pr_body,
            "--head", branch,
            "--base", base,
        ]
        if draft:
            cmd.append("--draft")

        logger.info("Running: %s", " ".join(cmd), extra={"cmd": " ".join(cmd)})

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )

        if result.returncode != 0:
            print(f"Error: gh pr create failed:\n{result.stderr.strip()}")
            return 1

        pr_url = result.stdout.strip()
        print(f"PR created: {pr_url}")
        print(f"  Title: {pr_title}")
        print(f"  Closes: #{issue_number}")
        if sub_issues:
            print(f"  WMBT sub-issues: {len(sub_issues)}")

        # 9. Enable auto-merge if requested
        if auto_merge:
            if draft:
                print("Warning: Auto-merge cannot be enabled on draft PRs.")
                print("  Convert to ready-for-review first, then run:")
                print(f"  gh pr merge {pr_url} --auto --{merge_strategy}")
            elif not self._check_auto_merge_enabled():
                print("Warning: Auto-merge is not enabled for this repository.")
                print("  Enable it in Settings → General → Allow auto-merge.")
            else:
                if self._enable_auto_merge(pr_url, merge_strategy):
                    print(f"  Auto-merge: enabled ({merge_strategy})")
                else:
                    print(f"Warning: Failed to enable auto-merge.")
                    print(f"  You can retry manually:")
                    print(f"  gh pr merge {pr_url} --auto --{merge_strategy}")

        # Worktree cleanup reminder
        worktree_dir = self.target_dir.name
        print(f"\n  After merge, clean up:")
        print(f"    git worktree remove ../{worktree_dir}")

        return 0
