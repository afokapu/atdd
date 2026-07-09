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

from atdd.coach.commands.issue_prefixes import ALLOWED_BRANCH_PREFIXES, TYPE_TO_PREFIX
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


def _store_session_entry(root, issue_number: int):
    """Manifest-session-shaped dict for *issue_number* from the State Store, or None."""
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=root) as reader:
            return reader.session_entry(issue_number)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


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
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        """Find an issue by number — store-first (#1270 slice B), manifest fallback.

        Returns a manifest-``sessions``-shaped entry (``slug``/``type``/...) or None.
        """
        entry = _store_session_entry(self.target_dir, issue_number)
        if entry is not None:
            return entry
        manifest = self._load_manifest()
        for entry in manifest.get("sessions", []):
            if entry.get("issue_number") == issue_number:
                return entry
        return None

    def _record_branch_in_manifest(self, issue_number: int, branch_name: str) -> None:
        """Persist *branch_name* onto the issue's session entry (#1051).

        Replaces the retired Projects v2 ``ATDD Branch`` write. A missing
        manifest or entry is a no-op (the worktree still exists; the gate that
        reads this falls open on an empty branch).
        """
        if not self.manifest_file.exists():
            return
        manifest = self._load_manifest()
        mutated = False
        for entry in manifest.get("sessions", []):
            if entry.get("issue_number") == issue_number:
                entry["branch"] = branch_name
                mutated = True
        if not mutated:
            return
        try:
            with open(self.manifest_file, "w") as fh:
                yaml.dump(manifest, fh, default_flow_style=False, sort_keys=False)
        except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-19
            logger.debug("Could not record branch in manifest: %s", exc, extra={"error": str(exc)})
            return
        print(f"  Recorded branch in manifest → {branch_name}")

    def _record_binding_in_store(
        self, issue_number: int, branch_name: str, worktree_path: Path
    ) -> bool:
        """Write the branch↔issue↔worktree binding into the State Store (#1347).

        This is the store-side seam the #1270 pre-commit gate relies on: the
        worktree-create path is the single writer of ``data.branch`` and
        ``data.worktree_path`` onto the issue's work item, so a freshly created
        worktree is registered in the store — with **zero commits to local
        ``main``** — and ``atdd issue is-registered`` (#1324, store-first)
        resolves it without ever reading ``.atdd/manifest.yaml``.

        Resolves ``issue_number`` → work item via the github ``external_ref``
        (WorkItemReader), merges the two binding keys into its ``data`` bag
        (preserving kind + lifecycle ``state``) through ``ObjectStore.upsert``
        — storage API only, within the #1220 boundaries. Returns True on a
        store write, False when the store is unavailable or the issue is not
        yet in the store. Never raises; makes no GitHub calls; no commit.
        """
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.store import StateStore
            from atdd.state.work_item_reader import WorkItemReader

            with WorkItemReader(control_root=self.target_dir) as reader:
                obj = reader.get(issue_number)
            if obj is None:
                return False
            merged = {
                **obj.data,
                "branch": branch_name,
                "worktree_path": str(worktree_path),
            }
            conn = connect(init_state_store(start=self.target_dir))
            try:
                StateStore(conn).objects.upsert(
                    obj.uid, obj.kind, state=obj.state, data=merged
                )
            finally:
                conn.close()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "branch↔worktree binding store write unavailable",
                extra={"issue": issue_number, "branch": branch_name, "error": str(exc)},
            )
            return False
        print(f"  Recorded binding in store → {branch_name} @ {worktree_path.name}")
        return True

    def _ff_sync_default_branch(self, default_branch: str) -> None:
        """Fast-forward local ``default_branch`` to ``origin/default_branch`` (#1347).

        Keeps local ``main`` a clean fast-forward of ``origin/main`` so that
        creating a worktree never leaves ``main`` drifting behind the remote.
        Fast-forwards **only** when it is strictly safe: local ``main`` is a
        proper ancestor of ``origin/main`` (behind-only, zero commits ahead) and
        its working tree is clean. On any divergence (commits ahead) or a dirty
        tree, it skips loudly and never rewrites history — the create path makes
        zero commits to ``main`` regardless.
        """
        root = self.target_dir
        try:
            behind = subprocess.run(
                ["git", "rev-list", "--count", f"{default_branch}..origin/{default_branch}"],
                capture_output=True, text=True, timeout=10, cwd=root,
            )
            ahead = subprocess.run(
                ["git", "rev-list", "--count", f"origin/{default_branch}..{default_branch}"],
                capture_output=True, text=True, timeout=10, cwd=root,
            )
            if behind.returncode != 0 or ahead.returncode != 0:
                return
            behind_n = int(behind.stdout.strip() or "0")
            ahead_n = int(ahead.stdout.strip() or "0")
            if behind_n == 0:
                return  # already current — nothing to sync
            if ahead_n > 0:
                print(
                    f"  Note: local `{default_branch}` has diverged from "
                    f"origin/{default_branch} ({ahead_n} ahead, {behind_n} behind) — "
                    f"skipping ff-sync (worktree is based on origin/{default_branch})."
                )
                return
            # Only fast-forward from the checkout that has default_branch checked out.
            head = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=root,
            )
            if head.returncode != 0 or head.stdout.strip() != default_branch:
                return
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=10, cwd=root,
            )
            if dirty.returncode != 0 or dirty.stdout.strip():
                print(
                    f"  Note: local `{default_branch}` is {behind_n} behind "
                    f"origin/{default_branch} but its working tree is dirty — "
                    f"skipping ff-sync."
                )
                return
            ff = subprocess.run(
                ["git", "merge", "--ff-only", f"origin/{default_branch}"],
                capture_output=True, text=True, timeout=15, cwd=root,
            )
            if ff.returncode == 0:
                print(f"  Fast-forwarded local `{default_branch}` → origin/{default_branch}")
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug(
                "ff-sync of default branch skipped",
                extra={"default_branch": default_branch, "error": str(exc)},
            )

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

        # Keep local `main` a clean fast-forward of origin/main so worktree
        # creation never leaves it drifting behind the remote (#1347). Safe
        # (behind-only + clean tree) or a loud no-op; never writes a commit.
        self._ff_sync_default_branch(default_branch)

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
            logger.warning(
                "refused worktree on protected branch",
                extra={"issue": issue_number, "error": str(exc)},
            )
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

        # Record the branch in the local manifest (#1051). The Projects v2
        # "ATDD Branch" field is decommissioned — the manifest is now the
        # canonical local mirror that downstream gates (e.g. the PLANNED PR
        # gate) read.
        self._record_branch_in_manifest(issue_number, branch_name)

        # Write the branch↔issue↔worktree binding to the State Store (#1347) —
        # the control-root SoT the #1270 pre-commit gate (`atdd issue
        # is-registered`, store-first) reads. Zero commits to local `main`.
        self._record_binding_in_store(issue_number, branch_name, worktree_path)

        # Refresh VS Code workspace file
        try:
            from atdd.coach.commands.initializer import write_workspace
            write_workspace(self.target_dir)
        except Exception as e:
            print(f"  Warning: Could not refresh workspace file: {e}")

        print(f"\n  cd {worktree_path}")
        return 0

    def _list_worktrees(self):
        """Yield (path, branch) for each registered git worktree, main first."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=15,
            cwd=self.target_dir,
        )
        entries = []
        cur_path = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                cur_path = Path(line[len("worktree "):].strip())
            elif line.startswith("branch ") and cur_path is not None:
                ref = line[len("branch "):].strip()
                branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
                entries.append((cur_path, branch))
                cur_path = None
            elif line.strip() == "" :
                if cur_path is not None:
                    entries.append((cur_path, None))
                    cur_path = None
        if cur_path is not None:
            entries.append((cur_path, None))
        return entries

    def list_worktrees(self) -> int:
        """`atdd worktree list` — show atdd worktrees and their store bindings.

        Lists every registered git worktree with its branch and, when the
        branch resolves to a work item in the State Store, the bound issue
        number (read from the ``data.worktree_path``/``branch`` binding written
        at create time, #1347). Read-only; never writes.
        """
        entries = self._list_worktrees()
        if not entries:
            print("No git worktrees found.")
            return 0
        # Build a branch → issue_number map from the store (best-effort).
        branch_to_issue = {}
        try:
            from atdd.state.db import connect, init_state_store
            from atdd.state.manifest_import import WORK_ITEM_KIND
            from atdd.state.store import StateStore

            conn = connect(init_state_store(start=self.target_dir))
            try:
                store = StateStore(conn)
                for obj in store.objects.list(kind=WORK_ITEM_KIND):
                    br = (obj.data or {}).get("branch")
                    if br:
                        branch_to_issue[br] = obj.uid
            finally:
                conn.close()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            logger.debug("worktree list store read unavailable", extra={"error": str(exc)})

        print("ATDD worktrees:")
        for path, branch in entries:
            slug = branch_to_issue.get(branch)
            bound = f"  → work item: {slug}" if slug else ""
            print(f"  {branch or '(detached)':45s}  {path}{bound}")
        return 0

    def remove_worktree(self, target: str) -> int:
        """`atdd worktree remove <issue|path>` — safely remove an atdd worktree.

        ``target`` is either an issue number (the worktree path is derived from
        the issue's ``prefix-slug`` naming) or a worktree directory path. Refuses
        to remove the main checkout. Delegates to ``git worktree remove`` (no
        ``--force``): a dirty or locked worktree is reported, not clobbered.
        """
        worktree_path: Optional[Path] = None
        if target.isdigit():
            entry = self._find_issue(int(target)) or self._backfill_from_github(int(target))
            if entry is None:
                print(f"Error: Issue #{target} not found; pass an explicit worktree path.")
                return 1
            slug = entry["slug"]
            issue_type = entry.get("type", "implementation")
            prefix = TYPE_TO_PREFIX.get(issue_type, "feat")
            worktree_path = self.target_dir.parent / f"{prefix}-{slug}"
        else:
            worktree_path = Path(target).expanduser()
            if not worktree_path.is_absolute():
                worktree_path = (self.target_dir.parent / target).resolve()

        if worktree_path.resolve() == self.target_dir.resolve():
            print("Error: refusing to remove the main checkout.")
            return 1

        registered = {p.resolve() for p, _ in self._list_worktrees()}
        if worktree_path.resolve() not in registered:
            print(f"Error: {worktree_path} is not a registered git worktree.")
            print("  List them with: atdd worktree list")
            print("  Clean non-git orphan dirs with: atdd worktree gc --apply")
            return 1

        result = subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            capture_output=True, text=True, timeout=30,
            cwd=self.target_dir,
        )
        if result.returncode != 0:
            print(f"Error: could not remove worktree: {result.stderr.strip()}")
            print("  If it has uncommitted work, commit or discard it first, then retry.")
            return 1
        print(f"Removed worktree: {worktree_path}")
        return 0
