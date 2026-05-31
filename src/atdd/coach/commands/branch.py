"""
Branch (worktree) creation from ATDD issue metadata.

Creates a git worktree with the correct prefix/slug naming derived from
the issue manifest. Updates the GitHub "ATDD Branch" field and refreshes
the VS Code workspace file.

Usage:
    atdd branch 69                        # Create worktree from issue #69
    atdd branch 69 --prefix fix           # Override prefix (default: from type)

Convention: CLAUDE.md git.branching
"""
import json
import logging
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from atdd.coach.commands.issue import ALLOWED_BRANCH_PREFIXES, TYPE_TO_PREFIX
from atdd.coach.github import GitHubClient, GitHubClientError, ProjectConfig
from atdd.coach.utils.default_branch import resolve_default_branch

logger = logging.getLogger(__name__)


def _rev_count_past_default(worktree_path: Path, default_branch: str) -> Optional[int]:
    """Return commits in HEAD past origin/<default_branch>; None on failure."""
    result = subprocess.run(
        ["git", "rev-list", "--count", f"origin/{default_branch}..HEAD"],
        capture_output=True, text=True, timeout=10,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if not out.isdigit():
        return None
    return int(out)


class BranchManager:
    """Create worktree branches from ATDD issue metadata."""

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def _create_draft_pr(
        self,
        branch_name: str,
        issue_number: int,
        slug: str,
        issue_type: str,
        worktree_path: Path,
    ) -> None:
        """Create a draft PR linked to the issue, if none exists yet."""
        # Check for existing PR on this branch
        check = subprocess.run(
            ["gh", "pr", "list", "--head", branch_name, "--json", "number",
             "--jq", ".[0].number"],
            capture_output=True, text=True, timeout=10,
            cwd=worktree_path,
        )
        if check.returncode == 0 and check.stdout.strip():
            pr_num = check.stdout.strip()
            print(f"  PR: #{pr_num} already exists")
            return

        default_branch = resolve_default_branch(self.target_dir)

        # Defer PR creation when the branch has no commits past default.
        # GitHub's createPullRequest mutation hard-fails when head==base, and
        # the standard `atdd branch` flow always lands on an empty branch.
        rev_count = _rev_count_past_default(worktree_path, default_branch)
        if rev_count == 0:
            print(
                f"  Note: Draft PR deferred — branch has 0 commits past "
                f"`{default_branch}`."
            )
            print(
                f"        Commit your work, then run `atdd pr {issue_number}` "
                f"to open the draft PR."
            )
            print( "        See `CLAUDE.md::issues.commands.new` for lifecycle.")
            return

        # Fetch issue title for the PR title
        prefix = TYPE_TO_PREFIX.get(issue_type, "feat")
        pr_title = f"{prefix}: {slug.replace('-', ' ')} (#{issue_number})"
        try:
            proj = ProjectConfig.from_config(self.config_file)
            client = GitHubClient(repo=proj.repo, project_id=proj.project_id)
            issue_data = client.get_issue(issue_number)
            gh_title = issue_data.get("title", "")
            if gh_title:
                pr_title = f"{gh_title} (#{issue_number})"
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            pass  # Fall back to slug-based title

        pr_body = f"Closes #{issue_number}\n\n---\nDraft PR created by `atdd branch`."

        result = subprocess.run(
            ["gh", "pr", "create", "--draft",
             "--title", pr_title,
             "--body", pr_body,
             "--head", branch_name,
             "--base", default_branch],
            capture_output=True, text=True, timeout=15,
            cwd=worktree_path,
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            print(f"  Draft PR: {pr_url}")
        else:
            # Real PR-create failure (non-empty branch, actual API error).
            # Print structured Fix hint per #467 contract.
            print(f"  Error: Could not create draft PR: {result.stderr.strip()}")
            print( "  Fix:")
            print(f"    1. cd {worktree_path}")
            print(f"    2. atdd pr {issue_number}")
            print( "  Why: `atdd branch` defers PR creation to `atdd pr` when the")
            print( "       inline createPullRequest call fails (e.g. transient gh/API).")

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

    def _backfill_from_github(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """Fetch issue #N from GitHub and append a synthesised sessions entry to the manifest.

        Self-heal path (#775): when an issue exists on GitHub but is absent from
        .atdd/manifest.yaml, synthesise the minimum required fields from `gh issue
        view` output and append the entry. This unblocks `atdd branch <N>` without
        requiring the user to manually edit the manifest.

        Returns the new entry dict on success, or None when gh CLI fails or the
        manifest file cannot be written.
        """
        if not self.manifest_file.exists():
            return None

        result = subprocess.run(
            [
                "gh", "issue", "view", str(issue_number),
                "--json", "number,title,state,createdAt,labels,body",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            return None

        # Derive slug from title: strip leading "feat(atdd): " or similar prefix
        title = data.get("title", "")
        slug_raw = re.sub(r"^\w+(?:\([^)]*\))?:\s*", "", title)
        slug_raw = re.sub(r"\s*\(#\d+\)\s*$", "", slug_raw)
        slug = re.sub(r"[^a-z0-9]+", "-", slug_raw.lower()).strip("-") or f"issue-{issue_number}"

        # Derive status from labels
        status = "INIT"
        for label in data.get("labels", []):
            name = label.get("name", "")
            if name.startswith("atdd:"):
                status = name[5:]
                break

        # Derive created date
        created_raw = data.get("createdAt", "")
        created = created_raw[:10] if created_raw else str(date.today())

        entry: Dict[str, Any] = {
            "id": str(issue_number),
            "slug": slug,
            "file": None,
            "issue_number": issue_number,
            "type": "implementation",
            "status": status,
            "created": created,
            "archived": None,
        }

        manifest = self._load_manifest()
        sessions = manifest.get("sessions") or []
        # Idempotent: do not duplicate
        if any(s.get("issue_number") == issue_number for s in sessions):
            return next(s for s in sessions if s.get("issue_number") == issue_number)

        sessions.append(entry)
        manifest["sessions"] = sessions
        try:
            with open(self.manifest_file, "w") as fh:
                yaml.dump(manifest, fh, default_flow_style=False, sort_keys=False)
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            return None

        print(f"  Manifest: backfilled entry for #{issue_number} from GitHub (self-heal)")
        return entry

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

        # Look up issue in manifest; self-heal from GitHub when absent (#775)
        entry = self._find_issue(issue_number)
        if entry is None:
            entry = self._backfill_from_github(issue_number)
        if entry is None:
            print(
                f"Error: Issue #{issue_number} not found in manifest and could not be "
                f"fetched from GitHub.\n"
                f"Create it first with: atdd issue <slug>\n"
                f"Or backfill all missing issues: atdd issue reconcile"
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

        # Targeted fetch: update origin/<default_branch> so new branches start
        # from the latest remote state, not stale local main (#770).
        default_branch = resolve_default_branch(self.target_dir)
        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )

        # Also fetch the feature branch ref if it may already exist remotely
        subprocess.run(
            ["git", "fetch", "origin", branch_name],
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

        # Create worktree. Creation, the existing-path triage, and the
        # I-1/I-2/I-9 incident defenses (incl. `core.bare=false` per-worktree)
        # are owned by the runtime layer (docs/coach-decomposition.md §13.5).
        # New branches start from origin/<default_branch> so they begin at the
        # latest remote commit regardless of local-main staleness.
        from atdd.runtime import worktree as runtime_worktree
        if remote_exists:
            print(f"Attaching to existing remote branch: {branch_name}")
        else:
            print(f"Creating new branch: {branch_name}")

        try:
            created = runtime_worktree.ensure_issue_worktree(
                worktree_path, branch_name, self.target_dir,
                issue_number=issue_number,
                start_point=f"origin/{default_branch}",
            )
        except runtime_worktree.ProtectedBranchError as exc:
            print(f"Error: {exc}")
            return 1
        if created is None:
            print("Error: git worktree add failed")
            return 1

        print(f"  Worktree: {worktree_path}")

        # Push branch to remote (required for draft PR)
        if not remote_exists:
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                capture_output=True, text=True, timeout=30,
                cwd=worktree_path,
            )
            if push_result.returncode != 0:
                print(f"  Warning: Could not push branch: {push_result.stderr.strip()}")
            else:
                print(f"  Pushed: origin/{branch_name}")

        # Create draft PR if none exists
        self._create_draft_pr(
            branch_name=branch_name,
            issue_number=issue_number,
            slug=slug,
            issue_type=issue_type,
            worktree_path=worktree_path,
        )

        # Update GitHub "ATDD Branch" field
        try:
            proj = ProjectConfig.from_config(self.config_file)
            client = GitHubClient(
                repo=proj.repo,
                project_id=proj.project_id,
            )
            item_id = client.get_project_item_id(issue_number)
            if item_id:
                fields = client.get_project_fields()
                if "ATDD Branch" in fields:
                    client.set_project_field_text(
                        item_id, fields["ATDD Branch"]["id"], branch_name,
                    )
                    print(f"  Updated ATDD Branch → {branch_name}")
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
