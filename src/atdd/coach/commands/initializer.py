"""
Project initializer for ATDD structure in consumer repos.

Creates the following structure:
    consumer-repo/
    ├── CLAUDE.md                (with managed ATDD block)
    └── .atdd/
        ├── manifest.yaml        (machine-readable issue tracking)
        └── config.yaml          (agent sync + GitHub integration config)

GitHub infrastructure (requires `gh` CLI):
    - Labels: atdd-issue, atdd-wmbt, atdd:*, archetype:*, wagon:*
    - Project v2: "ATDD Sessions" with 11 custom fields
    - Workflow: .github/workflows/atdd-validate.yml
    - Config: project_id, project_number, repo in .atdd/config.yaml

Usage:
    atdd init                    # Initialize ATDD structure
    atdd init --force            # Overwrite existing files

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import json
import logging
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# Known branch prefixes for slug → branch name mapping
_BRANCH_PREFIXES = ("feat", "fix", "refactor", "chore", "docs", "devops")


def slug_to_branch_name(slug: str) -> str:
    """Convert worktree directory slug to branch-style name.

    Maps the first hyphen after a known prefix back to '/':
        feat-some-feature → feat/some-feature
        fix-typo          → fix/typo
        main              → main  (no prefix match)
    """
    for prefix in _BRANCH_PREFIXES:
        if slug.startswith(prefix + "-"):
            return prefix + "/" + slug[len(prefix) + 1:]
    return slug


def write_workspace(target_dir: Path) -> None:
    """Write a VS Code .code-workspace file in the parent directory.

    Scans sibling directories for git worktrees and generates a multi-root
    workspace so VS Code shows branch info per folder.

    Args:
        target_dir: The main checkout directory (e.g. .../project/main).
    """
    parent = target_dir.parent
    workspace_name = parent.name
    workspace_path = parent / f"{workspace_name}.code-workspace"

    folders = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        git_marker = child / ".git"
        if not (git_marker.is_file() or git_marker.is_dir()):
            continue
        folders.append({
            "path": child.name,
            "name": slug_to_branch_name(child.name),
        })

    # Ensure main is listed first
    main_entry = next((f for f in folders if f["path"] == "main"), None)
    if main_entry:
        folders.remove(main_entry)
        folders.insert(0, main_entry)

    # Resolve background color: config → existing workspace → default yellow
    bg = "#FFC107"
    config_path = target_dir / ".atdd" / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            saved = config.get("workspace", {}).get("color")
            if saved:
                bg = saved
        except Exception:
            pass

    # If still default, check existing workspace file for user-set color
    if bg == "#FFC107" and workspace_path.exists():
        try:
            existing = json.loads(workspace_path.read_text())
            existing_bg = (
                existing.get("settings", {})
                .get("workbench.colorCustomizations", {})
                .get("titleBar.activeBackground")
            )
            if existing_bg and existing_bg != "#FFC107":
                bg = existing_bg
                # Persist discovered color to config for future runs
                if config_path.exists():
                    try:
                        with open(config_path) as f:
                            cfg = yaml.safe_load(f) or {}
                        cfg.setdefault("workspace", {})["color"] = bg
                        with open(config_path, "w") as f:
                            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
                    except Exception:
                        pass
        except Exception:
            pass

    # Compute foreground via WCAG relative luminance
    from atdd.coach.commands.color import ColorManager
    fg = ColorManager._foreground(bg)

    workspace = {
        "folders": folders,
        "settings": {
            "workbench.colorCustomizations": {
                "titleBar.activeBackground": bg,
                "titleBar.activeForeground": fg,
                "statusBar.background": bg,
                "statusBar.foreground": fg,
            },
            # Minimal default layout: Explorer + Terminal only
            "workbench.panel.defaultLocation": "bottom",
            "panel.defaultVisibility": "hidden",
            "workbench.sideBar.location": "left",
            "workbench.activityBar.location": "top",
            "editor.minimap.enabled": False,
            "breadcrumbs.enabled": False,
            "workbench.secondarySideBar.visible": False,
        },
    }

    workspace_path.write_text(
        json.dumps(workspace, indent=2) + "\n"
    )
    print(f"Wrote: {workspace_path}")


class ProjectInitializer:
    """Initialize ATDD structure in consumer repo."""

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the ProjectInitializer.

        Args:
            target_dir: Target directory for initialization. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach

    def _has_linked_worktrees(self) -> list:
        """Return paths of linked worktrees (excludes the main checkout)."""
        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if result.returncode != 0:
                return []
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        # Porcelain format: blocks separated by blank lines, first block is main checkout
        worktrees = []
        blocks = result.stdout.strip().split("\n\n")
        for i, block in enumerate(blocks):
            if i == 0:
                continue  # Skip main checkout (first entry)
            for line in block.splitlines():
                if line.startswith("worktree "):
                    worktrees.append(line[len("worktree "):])
                    break
        return worktrees

    def _prompt_workspace_color(self) -> None:
        """Prompt user to pick a workspace color if unset or default yellow."""
        config_path = self.target_dir / ".atdd" / "config.yaml"
        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            return

        saved = config.get("workspace", {}).get("color")
        if saved and saved != "#FFC107":
            return

        print("\nWorkspace color customization:")
        from atdd.coach.commands.color import ColorManager
        manager = ColorManager(self.target_dir)
        manager.color()

    def _write_workspace(self) -> None:
        """Write a VS Code .code-workspace file (delegates to module-level)."""
        write_workspace(self.target_dir)

    def _migrate_to_worktree_layout(self) -> Path:
        """
        Move all repo contents into a main/ subdirectory.

        Returns:
            Path to the new repo root (main/).

        Raises:
            RuntimeError: If migration fails (with rollback).
        """
        main_dir = self.target_dir / "main"

        if main_dir.exists():
            raise RuntimeError(
                f"Directory already exists: {main_dir}\n"
                "Cannot migrate — 'main/' would conflict."
            )

        main_dir.mkdir()
        moved_items = []

        try:
            for item in sorted(self.target_dir.iterdir()):
                if item.name == "main":
                    continue
                dest = main_dir / item.name
                shutil.move(str(item), str(dest))
                moved_items.append((dest, item))
        except Exception as e:
            # Rollback: move items back
            for dest, original in reversed(moved_items):
                try:
                    shutil.move(str(dest), str(original))
                except Exception:
                    pass
            try:
                main_dir.rmdir()
            except Exception:
                pass
            raise RuntimeError(f"Migration failed (rolled back): {e}") from e

        return main_dir

    def _update_target_dir(self, new_root: Path) -> None:
        """Repoint all paths to the new repo root after migration."""
        self.target_dir = new_root
        self.atdd_config_dir = new_root / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def init(self, force: bool = False, worktree_layout: bool = False) -> int:
        """
        Bootstrap .atdd/ config and GitHub infrastructure.

        Args:
            force: If True, overwrite existing files.
            worktree_layout: If True, migrate repo to flat-sibling worktree layout.

        Returns:
            0 on success, 1 on error.
        """
        from atdd.coach.utils.repo import detect_worktree_layout, find_repo_root

        layout = detect_worktree_layout(self.target_dir)

        if worktree_layout:
            if layout == "worktree-ready":
                print("Already in worktree-ready layout (repo root is main/).")
                self._write_workspace()
            elif layout == "worktree":
                print("Error: You are inside a linked worktree.")
                print("Run this command from the main checkout instead.")
                return 1
            elif layout == "no-git":
                print("Error: No git repository found.")
                print("Initialize git first: git init")
                return 1
            elif layout == "flat":
                # Safety: must be at repo root, not a subdirectory
                try:
                    repo_root = find_repo_root(self.target_dir)
                    if repo_root.resolve() != self.target_dir.resolve():
                        print("Error: Not at repository root.")
                        print(f"Run from: {repo_root}")
                        return 1
                except RuntimeError:
                    pass

                # Safety: no linked worktrees (their .git files would break)
                linked = self._has_linked_worktrees()
                if linked:
                    print("Error: Existing linked worktrees would break after migration.")
                    print("Remove them first:")
                    for wt in linked:
                        print(f"  git worktree remove {wt}")
                    return 1

                # Confirm before migrating
                items = [i.name for i in self.target_dir.iterdir()]
                print(f"This will move all {len(items)} items into {self.target_dir / 'main'}:")
                for name in sorted(items)[:10]:
                    print(f"  {name}")
                if len(items) > 10:
                    print(f"  ... and {len(items) - 10} more")
                if not force:
                    answer = input("\nProceed? [y/N] ").strip().lower()
                    if answer not in ("y", "yes"):
                        print("Aborted.")
                        return 1

                # Migrate
                try:
                    new_root = self._migrate_to_worktree_layout()
                    self._update_target_dir(new_root)
                    print(f"Migrated to worktree layout: {new_root}")
                    self._write_workspace()
                    print(f"\n  ** After init completes, run: cd main **\n")
                except RuntimeError as e:
                    print(f"Error: {e}")
                    return 1
        else:
            if layout == "flat":
                print("Advisory: Repo uses flat layout (not worktree-ready).")
                print("  Run: atdd init --worktree-layout\n")

        # Check if already initialized
        if self.atdd_config_dir.exists() and not force:
            print(f"ATDD already initialized at {self.target_dir}")
            print("Use --force to reinitialize")
            return 1

        try:
            # Create .atdd/ config directory
            self.atdd_config_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.atdd_config_dir}")

            # Create manifest.yaml
            self._create_manifest(force)

            # Create config.yaml
            self._create_config(force)

            # Prompt for workspace color if unset or default yellow
            self._prompt_workspace_color()

            # Install git hooks (pre-commit worktree enforcement)
            self._install_hooks(force)

            # Sync agent config files
            from atdd.coach.commands.sync import AgentConfigSync
            syncer = AgentConfigSync(self.target_dir)
            syncer.sync()

            # Bootstrap GitHub infrastructure
            github_summary = self._bootstrap_github(force)

            # Print next steps
            print("\n" + "=" * 60)
            print("ATDD initialized successfully!")
            print("=" * 60)
            print("\nStructure created:")
            print(f"  {self.atdd_config_dir}/")
            print(f"  {self.manifest_file}")
            print(f"  {self.config_file}")
            print(f"  CLAUDE.md (with ATDD managed block)")
            if github_summary:
                print(f"\n{github_summary}")

            return 0

        except PermissionError as e:
            print(f"Error: Permission denied - {e}")
            return 1
        except OSError as e:
            print(f"Error: {e}")
            return 1

    def export_schemas(self) -> int:
        """
        Export convention YAML and schema JSON files to .atdd/schemas/.

        Copies files from the installed atdd package into the consumer repo
        so agents can reference conventions and schemas without the package
        being importable in their runtime.

        Target layout:
            .atdd/schemas/
            ├── .version                           # installed atdd version
            ├── planner/conventions/*.convention.yaml
            ├── planner/schemas/*.json
            ├── tester/conventions/*.convention.yaml
            ├── tester/schemas/*.json
            ├── coder/conventions/*.convention.yaml
            ├── coder/schemas/*.json
            ├── coach/conventions/*.convention.yaml
            └── coach/schemas/*.json

        Returns:
            0 on success, 1 on error.
        """
        from atdd import __version__

        package_root = Path(__file__).parent.parent.parent  # src/atdd
        schemas_dir = self.atdd_config_dir / "schemas"

        # Roles and their sub-directories to export
        roles = ["planner", "tester", "coder", "coach"]
        sub_dirs = ["conventions", "schemas"]

        copied = 0
        for role in roles:
            for sub in sub_dirs:
                src_dir = package_root / role / sub
                if not src_dir.is_dir():
                    logger.debug("Skipping missing source: %s", src_dir, extra={"path": str(src_dir)})
                    continue

                dest_dir = schemas_dir / role / sub
                dest_dir.mkdir(parents=True, exist_ok=True)

                for src_file in sorted(src_dir.iterdir()):
                    if not src_file.is_file():
                        continue
                    # Convention YAML or schema/template JSON
                    if src_file.suffix not in (".yaml", ".json"):
                        continue
                    dest_file = dest_dir / src_file.name
                    shutil.copy2(str(src_file), str(dest_file))
                    copied += 1

        # Write version stamp
        version_file = schemas_dir / ".version"
        version_file.write_text(__version__ + "\n")

        print(f"Exported {copied} convention/schema files to {schemas_dir}")
        print(f"Version stamp: {__version__}")
        return 0

    @staticmethod
    def check_schema_version(target_dir: Optional[Path] = None) -> int:
        """
        Compare .atdd/schemas/.version against installed atdd version.

        Args:
            target_dir: Consumer repo root. Defaults to cwd.

        Returns:
            0 if versions match, 1 if mismatch or missing.
        """
        from atdd import __version__

        target = target_dir or Path.cwd()
        version_file = target / ".atdd" / "schemas" / ".version"

        if not version_file.exists():
            print("No exported schemas found (.atdd/schemas/.version missing).")
            print("Run: atdd init --export-schemas")
            return 1

        exported_version = version_file.read_text().strip()
        if exported_version == __version__:
            print(f"Schemas in sync: {exported_version}")
            return 0
        else:
            print(f"Schema version mismatch:")
            print(f"  exported: {exported_version}")
            print(f"  installed: {__version__}")
            print("Run: atdd init --export-schemas   (or atdd sync)")
            return 1

    def _create_manifest(self, force: bool = False) -> None:
        """
        Create or update .atdd/manifest.yaml.

        Args:
            force: If True, overwrite existing manifest.
        """
        if self.manifest_file.exists() and not force:
            print(f"Manifest already exists: {self.manifest_file}")
            return

        manifest = {
            "version": "2.0",
            "created": date.today().isoformat(),
            "sessions": [],
        }

        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {self.manifest_file}")

    def _create_config(self, force: bool = False) -> None:
        """
        Create or update .atdd/config.yaml.

        When force=True and config already exists, deep-merges defaults into
        the existing config — preserving user-set values (workspace.color,
        github.*, customised release/sync settings) while filling in any
        missing default keys and always updating toolkit.last_version.

        Args:
            force: If True, merge defaults into existing config instead of
                   skipping.
        """
        if self.config_file.exists() and not force:
            print(f"Config already exists: {self.config_file}")
            return

        # Get installed ATDD version
        try:
            from atdd import __version__
            toolkit_version = __version__
        except ImportError:
            toolkit_version = "0.0.0"

        defaults = {
            "version": "1.0",
            "release": {
                "version_file": "VERSION",
                "tag_prefix": "v",
            },
            "sync": {
                "agents": ["claude"],
            },
            "toolkit": {
                "last_version": toolkit_version,
            },
        }

        # Merge: preserve existing user values, fill in missing defaults
        existing = {}
        is_update = self.config_file.exists()
        if is_update:
            with open(self.config_file) as f:
                existing = yaml.safe_load(f) or {}

        for key, value in defaults.items():
            if key not in existing:
                existing[key] = value
            elif isinstance(value, dict) and isinstance(existing[key], dict):
                for sub_key, sub_value in value.items():
                    if sub_key not in existing[key]:
                        existing[key][sub_key] = sub_value

        # Always update toolkit version to current
        existing.setdefault("toolkit", {})["last_version"] = toolkit_version

        with open(self.config_file, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

        action = "Updated" if is_update else "Created"
        print(f"{action}: {self.config_file}")

    def _install_hooks(self, force: bool = False) -> None:
        """Install git hooks from package templates into .atdd/hooks/.

        Copies all hook templates (pre-commit, pre-push, pre-merge-commit,
        etc.), makes them executable, and sets ``git config core.hooksPath``
        to the absolute path so that all worktrees sharing this repository
        inherit the hooks automatically.

        Args:
            force: If True, overwrite existing hooks.
        """
        hooks_dir = self.atdd_config_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        template_dir = self.package_root / "templates" / "hooks"
        if not template_dir.exists():
            logger.warning("Hook template directory not found: %s", template_dir, extra={"path": str(template_dir)})
            return

        installed = 0
        for hook_src in sorted(template_dir.iterdir()):
            if hook_src.name.startswith(("__", ".")) or hook_src.is_dir():
                continue
            hook_dst = hooks_dir / hook_src.name
            if hook_dst.exists() and not force:
                print(f"Hook exists (skip): {hook_dst}")
            else:
                shutil.copy2(hook_src, hook_dst)
                os.chmod(hook_dst, hook_dst.stat().st_mode | 0o111)
                print(f"Installed: {hook_dst}")
                installed += 1

        if installed == 0 and not force:
            print("All hooks already installed.")

        # Point git to the hooks directory (absolute path survives worktrees)
        abs_hooks = str(hooks_dir.resolve())
        try:
            subprocess.run(
                ["git", "config", "core.hooksPath", abs_hooks],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            print(f"Set git core.hooksPath → {abs_hooks}")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not set core.hooksPath: %s", exc, extra={"path": str(abs_hooks)})

    def is_initialized(self) -> bool:
        """Check if ATDD is already initialized in target directory."""
        return self.atdd_config_dir.exists() and self.manifest_file.exists()

    # -------------------------------------------------------------------------
    # E007: GitHub infrastructure bootstrap
    # -------------------------------------------------------------------------

    def _gh_available(self) -> bool:
        """Check if `gh` CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _detect_repo(self) -> Optional[str]:
        """Detect the GitHub repo from git remote."""
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _bootstrap_github(self, force: bool = False) -> Optional[str]:
        """Bootstrap GitHub infrastructure: labels, Project v2, fields, workflow."""
        if not self._gh_available():
            print("\nWarning: gh CLI not available or not authenticated.")
            print("  GitHub infrastructure not created.")
            print("  Install: https://cli.github.com")
            print("  Then run: gh auth login && atdd init --force")
            return None

        repo = self._detect_repo()
        if not repo:
            print("\nWarning: Could not detect GitHub repo.")
            print("  Run from inside a git repo with a GitHub remote.")
            return None

        print(f"\nBootstrapping GitHub infrastructure for {repo}...")

        from atdd.coach.github import GitHubClient, GitHubClientError

        # Migrate legacy labels (e.g., atdd-session → atdd-issue)
        self._migrate_labels(repo)

        # Load label taxonomy from schema
        schema_path = self.package_root / "schemas" / "label_taxonomy.schema.json"
        labels_created, labels_existed = self._create_labels(repo, schema_path)

        # Create or find Project v2
        project_id, project_number, project_created = self._ensure_project(repo)

        # Create custom fields
        fields_created = 0
        if project_id:
            fields_created = self._create_project_fields(project_id)

        # Write workflow files (skip if config says so)
        skip_workflows = False
        if self.config_file.exists():
            try:
                cfg = yaml.safe_load(self.config_file.read_text()) or {}
                skip_workflows = cfg.get("init", {}).get("skip_workflows", False)
            except (yaml.YAMLError, OSError):
                pass

        if skip_workflows:
            print("Workflows: skipped (init.skip_workflows=true in config)")
            workflow_written = False
            publish_written = False
        else:
            workflow_written = self._write_workflow(repo)
            infra_written = self._write_infra_workflow()
            publish_written = self._write_publish_workflow()

        # Configure branch protection on main
        protection_set = self._set_branch_protection(repo)

        # Enable auto-merge
        auto_merge_set = self._enable_auto_merge(repo)

        # Update config with GitHub settings
        if project_id:
            self._update_config_github(repo, project_id, project_number)

        # Summary
        parts = []
        parts.append(f"{labels_created + labels_existed} labels "
                      f"({labels_created} created, {labels_existed} existed)")
        if project_id:
            verb = "created" if project_created else "found"
            parts.append(f"Project 'ATDD Sessions' #{project_number} ({verb})")
        if fields_created:
            parts.append(f"{fields_created} fields created")
        if workflow_written:
            parts.append("workflow written")
        if protection_set:
            parts.append("branch protection configured")
        if auto_merge_set:
            parts.append("auto-merge enabled")

        summary = f"GitHub: {', '.join(parts)}"
        print(f"  {summary}")
        return summary

    # R002: label renames — `gh label edit` renames in-place and propagates to all issues
    _LABEL_MIGRATION = {"atdd-session": "atdd-issue"}

    def _migrate_labels(self, repo: str) -> None:
        """Rename legacy labels in-place via `gh label edit`. Idempotent."""
        for old_name, new_name in self._LABEL_MIGRATION.items():
            try:
                result = subprocess.run(
                    ["gh", "label", "edit", old_name,
                     "--name", new_name, "--repo", repo],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    print(f"  Migrated label: {old_name} → {new_name}")
                else:
                    # Old label doesn't exist (already migrated or fresh install) — no-op
                    logger.debug("Label %s not found for migration: %s", old_name, result.stderr.strip(), extra={"label": old_name})
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.debug("Could not migrate label %s", old_name, extra={"label": old_name})

    def _create_labels(self, repo: str, schema_path: Path) -> Tuple[int, int]:
        """Create ATDD labels from taxonomy schema. Returns (created, existed)."""
        if not schema_path.exists():
            logger.warning("Label taxonomy schema not found: %s", schema_path, extra={"path": str(schema_path)})
            return 0, 0

        with open(schema_path) as f:
            schema = json.load(f)

        # Extract labels from schema
        labels = []
        categories = schema.get("properties", {}).get("categories", {}).get("properties", {})
        for cat_name, cat_spec in categories.items():
            cat_props = cat_spec.get("properties", {})
            label_items = cat_props.get("labels", {}).get("prefixItems", [])
            for item in label_items:
                props = item.get("properties", {})
                name = props.get("name", {}).get("const")
                color = props.get("color", {}).get("const")
                desc = props.get("description", {}).get("const", "")
                if name and color:
                    labels.append((name, color, desc))

        created = 0
        existed = 0
        for name, color, desc in labels:
            try:
                subprocess.run(
                    ["gh", "label", "create", name,
                     "--repo", repo, "--color", color,
                     "--description", desc, "--force"],
                    capture_output=True, text=True, timeout=10,
                )
                # --force means it's always "success"; we check if it existed
                # by trying without --force first, but simpler to just count all
                created += 1
            except (subprocess.TimeoutExpired, FileNotFoundError):
                existed += 1

        return created, existed

    def _ensure_project(self, repo: str) -> Tuple[Optional[str], Optional[int], bool]:
        """Find or create 'ATDD Sessions' Project v2. Returns (id, number, created)."""
        owner = repo.split("/")[0]

        # Check for existing project
        try:
            result = subprocess.run(
                ["gh", "project", "list", "--owner", owner, "--format", "json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                for proj in data.get("projects", []):
                    if proj.get("title") == "ATDD Sessions":
                        # Need to get the node ID via GraphQL
                        proj_number = proj["number"]
                        node_id = self._get_project_node_id(owner, proj_number)
                        return node_id, proj_number, False
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass

        # Create new project via GraphQL
        try:
            # Get owner node ID
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ user(login:"{owner}") {{ id }} }}',
                 "--jq", ".data.user.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # Try as org
                result = subprocess.run(
                    ["gh", "api", "graphql", "-f",
                     f'query={{ organization(login:"{owner}") {{ id }} }}',
                     "--jq", ".data.organization.id"],
                    capture_output=True, text=True, timeout=10,
                )

            owner_id = result.stdout.strip()
            if not owner_id:
                print("  Warning: Could not find owner ID for Project creation")
                return None, None, False

            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query=mutation {{ createProjectV2(input: {{ ownerId: "{owner_id}", '
                 f'title: "ATDD Sessions" }}) {{ projectV2 {{ id number }} }} }}'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                proj = data["data"]["createProjectV2"]["projectV2"]
                return proj["id"], proj["number"], True
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: Could not create Project: {e}")

        return None, None, False

    def _get_project_node_id(self, owner: str, project_number: int) -> Optional[str]:
        """Get Project v2 node ID from owner and number."""
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ user(login:"{owner}") {{ '
                 f'projectV2(number:{project_number}) {{ id }} }} }}',
                 "--jq", ".data.user.projectV2.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            # Try as org
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ organization(login:"{owner}") {{ '
                 f'projectV2(number:{project_number}) {{ id }} }} }}',
                 "--jq", ".data.organization.projectV2.id"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # v1 → v2 field migration map: old_name → new_name (None = delete)
    # NOTE: GitHub Project v2 field names cannot contain colons.
    _FIELD_MIGRATION: Dict[str, Optional[str]] = {
        "Session Number": None,              # DELETE — redundant with GitHub issue number
        "Session Type":   "ATDD Issue Type",
        "Complexity":     "ATDD Complexity",
        "Archetypes":     "ATDD Archetypes",
        "Branch":         "ATDD Branch",
        "Train":          "ATDD Train",
        "Feature URN":    "ATDD Feature URN",
        "WMBT ID":        "ATDD WMBT ID",
        "WMBT Step":      "ATDD WMBT Step",
        "WMBT Phase":     "ATDD WMBT Phase",
    }

    def _query_project_field_names_and_ids(self, project_id: str) -> Dict[str, str]:
        """Query existing project fields. Returns {name: field_id}."""
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f",
                 f'query={{ node(id: "{project_id}") {{ ... on ProjectV2 {{ '
                 f'fields(first: 30) {{ nodes {{ '
                 f'... on ProjectV2Field {{ id name }} '
                 f'... on ProjectV2SingleSelectField {{ id name }} '
                 f'}} }} }} }} }}'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {
                    node["name"]: node["id"]
                    for node in data["data"]["node"]["fields"]["nodes"]
                    if node.get("name") and node.get("id")
                }
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return {}

    def _rename_project_field_raw(self, project_id: str, field_id: str, new_name: str) -> bool:
        """Rename a project field via GraphQL. Returns True on success."""
        mutation = (
            f'mutation {{ updateProjectV2Field(input: {{ '
            f'fieldId: "{field_id}", name: "{new_name}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id name }} '
            f'... on ProjectV2SingleSelectField {{ id name }} }} }} }}'
        )
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _delete_project_field_raw(self, project_id: str, field_id: str) -> bool:
        """Delete a project field via GraphQL. Returns True on success."""
        mutation = (
            f'mutation {{ deleteProjectV2Field(input: {{ '
            f'fieldId: "{field_id}" '
            f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} '
            f'... on ProjectV2SingleSelectField {{ id }} }} }} }}'
        )
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _create_project_fields(self, project_id: str) -> int:
        """Create/migrate custom fields on a Project v2 from schema. Returns count changed."""
        schema_path = self.package_root / "schemas" / "project_fields.schema.json"
        if not schema_path.exists():
            return 0

        with open(schema_path) as f:
            schema = json.load(f)

        # ------------------------------------------------------------------
        # Pass 1: Migrate — rename old-name fields, delete deprecated ones
        # ------------------------------------------------------------------
        existing = self._query_project_field_names_and_ids(project_id)
        migrated = 0

        for old_name, new_name in self._FIELD_MIGRATION.items():
            if old_name not in existing:
                continue
            field_id = existing[old_name]

            if new_name is None:
                # Delete deprecated field
                if self._delete_project_field_raw(project_id, field_id):
                    print(f"    Deleted field: {old_name}")
                    migrated += 1
            elif old_name != new_name and new_name not in existing:
                # Rename (preserves values)
                if self._rename_project_field_raw(project_id, field_id, new_name):
                    print(f"    Renamed field: {old_name} -> {new_name}")
                    migrated += 1

        # ------------------------------------------------------------------
        # Pass 2: Re-query after migration
        # ------------------------------------------------------------------
        if migrated:
            existing = self._query_project_field_names_and_ids(project_id)
        existing_names = set(existing.keys())

        # ------------------------------------------------------------------
        # Pass 3: Create any still-missing fields from schema
        # ------------------------------------------------------------------
        created = 0
        defs = schema.get("$defs", {})

        for scope in ["parent_fields", "sub_issue_fields"]:
            scope_def = defs.get(scope, {})
            for field_key, field_spec in scope_def.get("properties", {}).items():
                field_props = field_spec.get("properties", {})
                name = field_props.get("name", {}).get("const")
                data_type = field_props.get("data_type", {}).get("const")

                if not name or not data_type or name in existing_names:
                    continue

                if data_type == "SINGLE_SELECT":
                    options = field_spec.get("properties", {}).get("options", {})
                    option_items = options.get("prefixItems", [])
                    options_str = ", ".join(
                        f'{{name: "{item["properties"]["name"]["const"]}", '
                        f'description: "{item["properties"]["description"]["const"]}", '
                        f'color: {item["properties"]["color"]["const"]}}}'
                        for item in option_items
                        if "properties" in item
                    )
                    mutation = (
                        f'mutation {{ createProjectV2Field(input: {{ '
                        f'projectId: "{project_id}", dataType: {data_type}, '
                        f'name: "{name}", singleSelectOptions: [{options_str}] '
                        f'}}) {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ id }} }} }} }}'
                    )
                else:
                    mutation = (
                        f'mutation {{ createProjectV2Field(input: {{ '
                        f'projectId: "{project_id}", dataType: {data_type}, '
                        f'name: "{name}" '
                        f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} }} }} }}'
                    )

                try:
                    result = subprocess.run(
                        ["gh", "api", "graphql", "-f", f"query={mutation}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        created += 1
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

        return migrated + created

    # Default path → phase mappings for path-scoped validation
    DEFAULT_PATH_FILTERS = {
        "planner": ["plan/**"],
        "tester": ["contracts/**", "telemetry/**"],
        "coder": ["web/**", "python/**", "packages/**", "supabase/**", "src/**"],
        "coach": [".atdd/**", ".github/**"],
    }

    def _write_workflow(self, repo: str) -> bool:
        """Write .github/workflows/atdd-validate.yml with parallel phase jobs.

        Generates a detect-changes job using dorny/paths-filter to skip phases
        whose files haven't changed. Path filters default to DEFAULT_PATH_FILTERS
        but can be overridden via .atdd/config.yaml path_filters key.
        """
        workflows_dir = self.target_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflows_dir / "atdd-validate.yml"

        phases = ["planner", "tester", "coder", "coach"]

        # Merge default path filters with config overrides
        filters = dict(self.DEFAULT_PATH_FILTERS)
        config_path = self.target_dir / ".atdd" / "config.yaml"
        if config_path.exists():
            try:
                cfg = yaml.safe_load(config_path.read_text()) or {}
                if "path_filters" in cfg:
                    filters.update(cfg["path_filters"])
            except Exception:
                pass

        # Build dorny/paths-filter filter config (plain YAML, no f-string interpolation)
        filter_lines = []
        for phase in phases:
            paths = filters.get(phase, [])
            filter_lines.append(f"            {phase}:")
            for p in paths:
                filter_lines.append(f"              - '{p}'")
        filter_config = "\n".join(filter_lines)

        # Build detect-changes job as plain string (avoid f-string escaping for ${{ }})
        detect_changes_job = (
            "\n"
            "  detect-changes:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.event_name != 'issues'\n"
            "    outputs:\n"
            "      planner: ${{ steps.filter.outputs.planner }}\n"
            "      tester: ${{ steps.filter.outputs.tester }}\n"
            "      coder: ${{ steps.filter.outputs.coder }}\n"
            "      coach: ${{ steps.filter.outputs.coach }}\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - uses: dorny/paths-filter@v3\n"
            "        id: filter\n"
            "        with:\n"
            "          filters: |\n"
            f"{filter_config}\n"
        )

        # Build per-phase job YAML blocks
        label_condition = (
            "contains(github.event.issue.labels.*.name, 'atdd-issue') || "
            "contains(github.event.issue.labels.*.name, 'atdd-wmbt')"
        )

        phase_jobs = ""
        for phase in phases:
            phase_jobs += f"""
  validate-{phase}:
    needs: [detect-changes]
    runs-on: ubuntu-latest
    if: >-
      always() && (
        (github.event_name == 'issues' && ({label_condition})) ||
        (github.event_name != 'issues' && needs.detect-changes.outputs.{phase} == 'true')
      )
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{{{ runner.os }}}}-pip-atdd

      - name: Install ATDD toolkit
        run: pip3 install atdd

      - name: Run {phase} validators
        run: atdd validate {phase}{' -m "not github_api"' if phase == 'coach' else ''}
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
"""

        needs_list = ", ".join(f"validate-{p}" for p in phases)

        # Build validate-gate job as plain string (complex ${{ }} expressions)
        gate_job = (
            "\n"
            "  validate-gate:\n"
            "    needs: [validate-planner, validate-tester, validate-coder, validate-coach]\n"
            "    runs-on: ubuntu-latest\n"
            "    if: always()\n"
            "    permissions:\n"
            "      issues: write\n"
            "    steps:\n"
            "      - name: Check results\n"
            "        run: |\n"
            '          for result in "planner:${{ needs.validate-planner.result }}" \\\n'
            '                        "tester:${{ needs.validate-tester.result }}" \\\n'
            '                        "coder:${{ needs.validate-coder.result }}" \\\n'
            '                        "coach:${{ needs.validate-coach.result }}"; do\n'
            '            phase="${result%%:*}"\n'
            '            status="${result##*:}"\n'
            '            if [ "$status" != "success" ] && [ "$status" != "skipped" ]; then\n'
            '              echo "::error::$phase failed ($status)"\n'
            "              exit 1\n"
            "            fi\n"
            "          done\n"
            '          echo "All phases passed or were skipped"\n'
            "\n"
            "      - name: Post comment\n"
            "        if: github.event_name == 'issues'\n"
            "        uses: actions/github-script@v7\n"
            "        with:\n"
            "          script: |\n"
            "            const needs = ${{ toJSON(needs) }};\n"
            "            const failed = Object.entries(needs)\n"
            "              .filter(([, v]) => v.result !== 'success' && v.result !== 'skipped')\n"
            "              .map(([k]) => k);\n"
            "            const emoji = failed.length === 0 ? '✅' : '❌';\n"
            "            const status = failed.length === 0 ? 'success' : 'failure';\n"
            "            const detail = failed.length > 0\n"
            "              ? '\\nFailed: ' + failed.join(', ')\n"
            "              : '';\n"
            "            await github.rest.issues.createComment({\n"
            "              owner: context.repo.owner,\n"
            "              repo: context.repo.repo,\n"
            "              issue_number: context.issue.number,\n"
            "              body: `${emoji} ATDD validation: **${status}**${detail}`\n"
            "            });\n"
        )

        # Build baseline-sync job (runs only on push to main, after gate passes)
        baseline_sync_job = (
            "\n"
            "  baseline-sync:\n"
            "    needs: [validate-gate]\n"
            "    runs-on: ubuntu-latest\n"
            "    if: github.ref == 'refs/heads/main' && github.event_name == 'push'\n"
            "    concurrency:\n"
            "      group: baseline-sync-${{ github.repository }}\n"
            "      cancel-in-progress: false\n"
            "    permissions:\n"
            "      contents: write\n"
            "      pull-requests: write\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "\n"
            "      - uses: actions/setup-python@v5\n"
            "        with:\n"
            '          python-version: "3.12"\n'
            "\n"
            "      - uses: actions/cache@v4\n"
            "        with:\n"
            "          path: ~/.cache/pip\n"
            "          key: ${{ runner.os }}-pip-atdd\n"
            "\n"
            "      - name: Install ATDD toolkit\n"
            "        run: pip3 install atdd\n"
            "\n"
            "      - name: Update baselines\n"
            "        run: atdd baseline update\n"
            "\n"
            "      - name: Create PR if baselines changed\n"
            "        uses: peter-evans/create-pull-request@v7\n"
            "        with:\n"
            "          commit-message: 'chore: auto-update baselines [skip ci]'\n"
            "          branch: chore/auto-update-baselines\n"
            "          title: 'chore: auto-update baselines'\n"
            "          body: |\n"
            "            Automated baseline sync after merge to main.\n"
            "\n"
            "            Updated files:\n"
            "            - `.atdd/baselines/coder.yaml`\n"
            "            - `.atdd/baselines/tester.yaml` (if present)\n"
            "\n"
            "            This PR was created automatically by the `baseline-sync` job.\n"
            "            Merge to keep baselines in sync and prevent ratchet drift.\n"
            "          add-paths: .atdd/baselines/\n"
            "          delete-branch: true\n"
            "          labels: chore\n"
        )

        workflow = (
            "# ATDD Validation Workflow\n"
            "# Generated by `atdd init` — safe to overwrite on re-run\n"
            "name: ATDD Validate\n"
            "\n"
            "on:\n"
            "  push:\n"
            '    branches: [main, "feat/*", "fix/*", "refactor/*", "chore/*", "docs/*", "devops/*"]\n'
            "  pull_request:\n"
            "    branches: [main]\n"
            "  issues:\n"
            "    types: [opened, edited, closed, labeled, unlabeled]\n"
            "\n"
            f"jobs:{detect_changes_job}{phase_jobs}{gate_job}{baseline_sync_job}"
        )

        workflow_path.write_text(workflow)
        print(f"  Wrote: {workflow_path}")
        return True

    def _write_infra_workflow(self) -> bool:
        """Write .github/workflows/atdd-validate-infra.yml for github_api tests.

        Runs on a weekly cron schedule (Sunday 02:00 UTC) and on pushes that
        touch .atdd/** or .github/** paths.  These tests verify GitHub
        infrastructure state (labels, project fields, branch protection) and
        are intentionally non-blocking — failures are reported but never gate
        PR merges.
        """
        workflows_dir = self.target_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        infra_path = workflows_dir / "atdd-validate-infra.yml"

        workflow = (
            "# ATDD Infrastructure Validation (github_api tests)\n"
            "# Generated by `atdd init` — safe to overwrite on re-run\n"
            "#\n"
            "# Runs weekly + on .atdd/** or .github/** changes.\n"
            "# Non-blocking: failures are reported but never gate PR merges.\n"
            "name: ATDD Validate Infra\n"
            "\n"
            "on:\n"
            "  schedule:\n"
            '    - cron: "0 2 * * 0"   # Every Sunday at 02:00 UTC\n'
            "  push:\n"
            "    paths:\n"
            "      - '.atdd/**'\n"
            "      - '.github/**'\n"
            "  workflow_dispatch:        # manual trigger\n"
            "\n"
            "jobs:\n"
            "  validate-infra:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "\n"
            "      - uses: actions/setup-python@v5\n"
            "        with:\n"
            '          python-version: "3.12"\n'
            "\n"
            "      - uses: actions/cache@v4\n"
            "        with:\n"
            "          path: ~/.cache/pip\n"
            "          key: ${{ runner.os }}-pip-atdd\n"
            "\n"
            "      - name: Install ATDD toolkit\n"
            "        run: pip3 install atdd\n"
            "\n"
            '      - name: Run github_api validators\n'
            '        run: atdd validate coach -m github_api\n'
            "        env:\n"
            "          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"
        )

        infra_path.write_text(workflow)
        print(f"  Wrote: {infra_path}")
        return True

    def _write_publish_workflow(self) -> bool:
        """Write .github/workflows/publish.yml (tag + publish after validation)."""
        workflows_dir = self.target_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        publish_path = workflows_dir / "publish.yml"

        publish = """\
# Tag + Publish after ATDD Validate succeeds on main
# Generated by `atdd init` — safe to overwrite on re-run
# Triggered automatically via workflow_run (avoids GITHUB_TOKEN cross-workflow limitation).
# Version bump is done by the agent on the PR branch BEFORE merging.
# "Require branches to be up to date" in branch protection serializes merges.
name: Publish

on:
  workflow_run:
    workflows: ["ATDD Validate"]
    types: [completed]
    branches: [main]
  workflow_dispatch:            # manual fallback

jobs:
  tag-release:
    runs-on: ubuntu-latest
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.workflow_run.conclusion == 'success' &&
       github.event.workflow_run.event == 'push')
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Read version and create tag
        run: |
          pip3 install pyyaml -q
          TAG=$(python3 - <<'PYEOF'
          import yaml, re, json
          cfg = yaml.safe_load(open(".atdd/config.yaml"))
          vf = cfg["release"]["version_file"]
          prefix = cfg["release"].get("tag_prefix", "v")
          if vf.endswith(".toml"):
              text = open(vf).read()
              m = re.search(r'^version\\s*=\\s*["\\x27]([^"\\x27]+)["\\x27]', text, re.M)
              ver = m.group(1) if m else ""
          elif vf.endswith(".json"):
              ver = json.load(open(vf)).get("version", "")
          else:
              ver = open(vf).read().strip().split()[0]
          print(f"{prefix}{ver}")
          PYEOF
          )
          echo "TAG=$TAG" >> "$GITHUB_ENV"

      - name: Create and push tag (idempotent)
        run: |
          if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "Tag $TAG already exists, skipping"
            echo "CREATED=false" >> "$GITHUB_ENV"
          else
            git tag "$TAG"
            git push origin "$TAG"
            echo "Created and pushed tag $TAG"
            echo "CREATED=true" >> "$GITHUB_ENV"
          fi

      - name: Create GitHub Release
        if: env.CREATED == 'true'
        run: gh release create "$TAG" --generate-notes --title "$TAG"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # -------------------------------------------------------------------------
  # TODO: Add platform-specific publish steps below.
  # Examples:
  #   PyPI:   pypa/gh-action-pypi-publish@release/v1 (needs id-token: write + environment: pypi)
  #   npm:    npm publish (needs NODE_AUTH_TOKEN secret)
  #   Docker: docker/build-push-action (needs registry credentials)
  # -------------------------------------------------------------------------
"""
        publish_path.write_text(publish)
        print(f"  Wrote: {publish_path}")
        return True

    def _enable_auto_merge(self, repo: str) -> bool:
        """Enable auto-merge on the repository so PRs merge once CI passes."""
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}",
                 "--method", "PATCH", "-f", "allow_auto_merge=true"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                print("  Auto-merge: enabled")
                return True
            else:
                print("  Auto-merge: SKIPPED (may require admin access)")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _set_branch_protection(self, repo: str) -> bool:
        """Configure branch protection on main.

        Delegates to the shared branch_protection contract module which
        holds the single source of truth for the expected policy.

        Returns True if protection was set successfully.
        """
        from atdd.coach.commands.branch_protection import apply_branch_protection

        return apply_branch_protection(repo)

    def _update_config_github(
        self, repo: str, project_id: str, project_number: int
    ) -> None:
        """Add GitHub settings to .atdd/config.yaml."""
        if not self.config_file.exists():
            return

        with open(self.config_file) as f:
            config = yaml.safe_load(f) or {}

        config["github"] = {
            "repo": repo,
            "project_number": project_number,
            "project_id": project_id,
            "field_schema": "atdd/coach/schemas/project_fields.schema.json",
        }

        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"  Updated: {self.config_file} (github section)")
