"""
Project initializer for ATDD structure in consumer repos.

Creates the following structure:
    consumer-repo/
    ├── CLAUDE.md                (with managed ATDD block)
    └── .atdd/
        └── config.yaml          (agent sync + GitHub integration config)
    (Operational issue state lives in the State Store under .atdd/state/, not a
    .atdd/manifest.yaml mirror — the mirror was deleted in #1270 Slice G.)

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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# Known branch prefixes for slug → branch name mapping
_BRANCH_PREFIXES = ("feat", "fix", "refactor", "chore", "docs", "devops")


# Domain-agnostic prompt copy for `atdd init` theme declaration (#291,
# Decision #7). Lists the 10 built-in names and the three mode choices
# without referencing any product category.
THEMES_PROMPT_COPY = """\
ATDD ships with 10 built-in theme names mapped to digits 0-9:

  0: commons        5: player
  1: mechanic       6: league
  2: scenario       7: audience
  3: match          8: monetization
  4: sensory        9: partnership

These defaults may not match your domain. You can declare custom theme
names in `.atdd/config.yaml` under the `themes:` key.

Choose one:
  - defaults  Keep the 10 built-in names. No `themes:` block is written.
  - custom    Declare your own digit-to-name mapping now. Existing
              `plan/**/*.yaml` is scanned first so detected themes are
              pre-populated; low-confidence candidates from top-level
              directories and package keywords are shown as suggestions.
  - skip      Same as defaults, plus a reminder of where to configure
              themes later (`.atdd/config.yaml` → `themes:`).

Define themes now? [defaults / custom / skip]
"""


# Modes accepted by the non-interactive `--themes` flag.
_THEME_MODES = frozenset({"defaults", "custom", "skip"})


# -----------------------------------------------------------------------------
# Substrate mode (issue #415, spec v12 §9.3)
# -----------------------------------------------------------------------------
# Toolkit-self vs consumer-repo is detected by heuristic, with explicit flag
# override. The substrate's pytest plugin is registered via pytest11 entry-point
# in pyproject.toml; the plugin checks `repo.substrate.enabled` at collect time
# and is a no-op in toolkit mode.

SUBSTRATE_MODE_CONSUMER = "consumer-repo"
SUBSTRATE_MODE_TOOLKIT = "toolkit"
SUBSTRATE_PLUGIN_ENTRY_POINT = "atdd.tester.substrate.plugin"
SUBSTRATE_DEFAULT_TEST_ROOT = "tests/"
SUBSTRATE_DEFAULT_PLAN_ROOT = "plan/"


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


_DEFAULT_WORKSPACE_BG = "#FFC107"


def _workspace_folders(parent: Path) -> List[dict]:
    """The git-worktree siblings to show as multi-root folders, ``main`` first."""
    folders = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
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

    return folders


def _saved_workspace_color(config_path: Path) -> Optional[str]:
    """The workspace color persisted in .atdd/config.yaml, if any."""
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return config.get("workspace", {}).get("color")
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return None


def _existing_workspace_color(workspace_path: Path) -> Optional[str]:
    """A user-set title-bar color already present in the workspace file."""
    try:
        existing = json.loads(workspace_path.read_text())
        return (
            existing.get("settings", {})
            .get("workbench.colorCustomizations", {})
            .get("titleBar.activeBackground")
        )
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return None


def _persist_workspace_color(config_path: Path, bg: str) -> None:
    """Persist a discovered color to config so future runs reuse it."""
    if not config_path.exists():
        return

    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        cfg.setdefault("workspace", {})["color"] = bg
        with open(config_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        pass


def _resolve_workspace_color(config_path: Path, workspace_path: Path) -> str:
    """Background color: config → existing workspace file → default yellow."""
    bg = _saved_workspace_color(config_path) or _DEFAULT_WORKSPACE_BG

    # Still default? An existing workspace file may carry a user-set color.
    if bg != _DEFAULT_WORKSPACE_BG or not workspace_path.exists():
        return bg

    existing_bg = _existing_workspace_color(workspace_path)
    if existing_bg and existing_bg != _DEFAULT_WORKSPACE_BG:
        _persist_workspace_color(config_path, existing_bg)
        return existing_bg

    return bg


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

    folders = _workspace_folders(parent)
    bg = _resolve_workspace_color(target_dir / ".atdd" / "config.yaml", workspace_path)

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
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach

    def _is_linked_worktree(self) -> bool:
        """Return True when target_dir is a linked (non-main) git worktree.

        Uses the 'git rev-parse' approach: in a linked worktree --git-dir
        points to .git/worktrees/<name> while --git-common-dir points to the
        shared .git.  In the main checkout they are equal.
        """
        try:
            common = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            git_dir = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if common.returncode != 0 or git_dir.returncode != 0:
                return False
            return common.stdout.strip() != git_dir.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return False

    def _ensure_worktree_config_extension(self) -> None:
        """Enable extensions.worktreeConfig idempotently if not already set.

        Required before 'git config --worktree' writes land in the worktree-
        local config.worktree file.  Has no effect if already true.
        """
        try:
            check = subprocess.run(
                ["git", "config", "--get", "extensions.worktreeConfig"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            if check.returncode == 0 and check.stdout.strip().lower() == "true":
                return  # already enabled — idempotent
            subprocess.run(
                ["git", "config", "extensions.worktreeConfig", "true"],
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning(
                "Could not enable extensions.worktreeConfig: %s", exc,
                extra={"path": str(self.target_dir)},
            )

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
        except (FileNotFoundError, subprocess.TimeoutExpired):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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

    def _prompt_themes(
        self,
        mode: str,
        *,
        repo_root: Optional[Path] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Resolve the themes block to write under `.atdd/config.yaml → themes:`.

        Implements Decision #7 of #291 non-interactively. Interactive
        prompting can be layered on top of this method by the CLI
        wrapper; unit tests drive the non-interactive path directly.

        Args:
            mode: One of "defaults", "custom", or "skip".
            repo_root: Repo root to scan for pre-existing themes.
                Defaults to ``self.target_dir``.

        Returns:
            None  — caller writes no `themes:` block
                    (`defaults` / `skip` / empty `custom` scan).
            dict  — caller writes `themes: <dict>`.

        Raises:
            ValueError: If ``mode`` is not one of the accepted values.
        """
        if mode not in _THEME_MODES:
            raise ValueError(
                f"Unknown themes mode {mode!r}. "
                f"Expected one of: {sorted(_THEME_MODES)}."
            )

        if mode in ("defaults", "skip"):
            return None

        # mode == "custom"
        from atdd.coach.utils.theme_scanner import scan_existing_themes

        scan_root = Path(repo_root) if repo_root is not None else self.target_dir
        result = scan_existing_themes(scan_root)

        if not result.detected:
            # Blind-prompt path: no detections to seed. Non-interactive
            # callers receive None (caller may fall back to defaults
            # behavior or write an empty `themes: {}` block).
            return None

        # Assign detected themes to digits starting at 1 so digit 0
        # (commons) is never overridden implicitly — W-THEME-001.
        mapping: Dict[str, str] = {}
        digit = 1
        for theme in result.detected:
            if digit > 9:
                break
            mapping[str(digit)] = theme
            digit += 1
        return mapping

    def _prompt_workspace_color(self) -> None:
        """Prompt user to pick a workspace color if unset or default yellow."""
        config_path = self.target_dir / ".atdd" / "config.yaml"
        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
                except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
                    pass
            try:
                main_dir.rmdir()
            except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
                pass
            raise RuntimeError(f"Migration failed (rolled back): {e}") from e

        return main_dir

    def _update_target_dir(self, new_root: Path) -> None:
        """Repoint all paths to the new repo root after migration."""
        self.target_dir = new_root
        self.atdd_config_dir = new_root / ".atdd"
        self.config_file = self.atdd_config_dir / "config.yaml"

    def _apply_worktree_layout(self, layout: str, force: bool) -> Optional[int]:
        """Handle ``--worktree-layout`` for the detected layout.

        Returns an exit code when init must stop, or None to carry on.
        """
        if layout == "worktree-ready":
            print("Already in worktree-ready layout (repo root is main/).")
            self._write_workspace()
            return None

        if layout == "worktree":
            print("Error: You are inside a linked worktree.")
            print("Run this command from the main checkout instead.")
            return 1

        if layout == "no-git":
            print("Error: No git repository found.")
            print("Initialize git first: git init")
            return 1

        if layout != "flat":
            return None

        if not self._worktree_migration_safe():
            return 1
        if not self._confirm_worktree_migration(force):
            return 1

        # Migrate
        try:
            new_root = self._migrate_to_worktree_layout()
            self._update_target_dir(new_root)
            print(f"Migrated to worktree layout: {new_root}")
            self._write_workspace()
            print(f"\n  ** After init completes, run: cd main **\n")
        except RuntimeError as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {e}")
            return 1

        return None

    def _worktree_migration_safe(self) -> bool:
        """Refuse to migrate from a subdirectory, or while linked worktrees exist."""
        from atdd.coach.utils.repo import find_repo_root

        # Safety: must be at repo root, not a subdirectory
        try:
            repo_root = find_repo_root(self.target_dir)
            if repo_root.resolve() != self.target_dir.resolve():
                print("Error: Not at repository root.")
                print(f"Run from: {repo_root}")
                return False
        except RuntimeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            pass

        # Safety: no linked worktrees (their .git files would break)
        linked = self._has_linked_worktrees()
        if linked:
            print("Error: Existing linked worktrees would break after migration.")
            print("Remove them first:")
            for wt in linked:
                print(f"  git worktree remove {wt}")
            return False

        return True

    def _confirm_worktree_migration(self, force: bool) -> bool:
        """Show what the migration will move, and ask before doing it."""
        items = [i.name for i in self.target_dir.iterdir()]
        print(f"This will move all {len(items)} items into {self.target_dir / 'main'}:")
        for name in sorted(items)[:10]:
            print(f"  {name}")
        if len(items) > 10:
            print(f"  ... and {len(items) - 10} more")

        if force:
            return True

        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            return True

        print("Aborted.")
        return False

    def init(
        self,
        force: bool = False,
        worktree_layout: bool = False,
        consumer_repo: bool = False,
        toolkit: bool = False,
    ) -> int:
        """
        Bootstrap .atdd/ config and GitHub infrastructure.

        Args:
            force: If True, overwrite existing files.
            worktree_layout: If True, migrate repo to flat-sibling worktree layout.
            consumer_repo: If True, force consumer-repo substrate mode (writes
                substrate fields to .atdd/config.yaml). Mutually exclusive with
                ``toolkit``. Spec v12 §9.3, issue #415.
            toolkit: If True, force toolkit mode (removes substrate fields).
                Mutually exclusive with ``consumer_repo``.

        Returns:
            0 on success, 1 on error.
        """
        if consumer_repo and toolkit:
            print("Error: --consumer-repo and --toolkit are mutually exclusive.")
            return 1
        from atdd.coach.utils.repo import detect_worktree_layout

        layout = detect_worktree_layout(self.target_dir)

        if worktree_layout:
            stop_code = self._apply_worktree_layout(layout, force)
            if stop_code is not None:
                return stop_code
        elif layout == "flat":
            print("Advisory: Repo uses flat layout (not worktree-ready).")
            print("  Run: atdd init --worktree-layout\n")

        # Check if already initialized
        #
        # #1492: this early return is why the skip-if-exists inside
        # _install_hooks was only the SECOND gate — plain `atdd init` never
        # reached it. The hook refresh deliberately does NOT live here: `init`
        # on an initialised repo is contractually a no-op (R004/#720 asserts a
        # zero-change snapshot for `--worktree-layout` on an already-flat repo),
        # and quietly turning it into a writer would redefine that contract.
        # `atdd sync` is the sanctioned refresh instead — it is the verb the
        # upgrade banner names ("Run: atdd sync && atdd init") and the verb that
        # stamps toolkit.last_version.
        if self.atdd_config_dir.exists() and not force:
            print(f"ATDD already initialized at {self.target_dir}")
            print("Use --force to reinitialize")
            return 1

        try:
            # Create .atdd/ config directory
            self.atdd_config_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.atdd_config_dir}")

            # Ensure .atdd/cache/ is gitignored
            self._ensure_gitignore_entry(".atdd/cache/")
            # Issue #449: validation diagnostics artifact directory.
            # Written by `atdd validate` on every run — local artifact,
            # not git history.
            self._ensure_gitignore_entry(".atdd/diagnostics/")

            # #1270 Slice G: the ``.atdd/manifest.yaml`` mirror was deleted — the
            # State Store is the sole operational registry. Genesis no longer
            # writes a manifest; a cold store self-seeds from registered sync
            # providers on first read (WorkItemReader).

            # Create config.yaml
            self._create_config(force)

            # Resolve substrate mode (consumer-repo vs toolkit) and write/remove
            # the `repo:` block in .atdd/config.yaml — issue #415, spec v12 §9.3.
            substrate_mode = self._apply_substrate_mode(
                force_consumer=consumer_repo,
                force_toolkit=toolkit,
            )
            print(f"Substrate mode: {substrate_mode}")

            # Prompt for workspace color if unset or default yellow
            self._prompt_workspace_color()

            # Install git hooks (pre-commit worktree enforcement)
            self._install_hooks(force)

            # Install the gh-issue-create L3 enforcement layer: PATH shim,
            # .envrc PATH_add, and pre-commit grep (#816). Soft-fails on
            # missing direnv.
            self.install_path_shim_enforcement(force)

            # Install train-render harness when consumer repo has a frontend (#335)
            self._install_harness(force)

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
            print(f"  {self.config_file}")
            print(f"  CLAUDE.md (with ATDD managed block)")
            if github_summary:
                print(f"\n{github_summary}")

            return 0

        except PermissionError as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: Permission denied - {e}")
            return 1
        except OSError as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {e}")
            return 1

    def _ensure_gitignore_entry(self, entry: str) -> None:
        """Append *entry* to the repo .gitignore if not already present."""
        gitignore = self.target_dir / ".gitignore"
        if gitignore.is_file():
            content = gitignore.read_text()
            if entry in content:
                return
            if not content.endswith("\n"):
                content += "\n"
        else:
            content = ""
        content += f"{entry}\n"
        gitignore.write_text(content)
        print(f"Added '{entry}' to .gitignore")

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

        package_root = Path(__file__).parent.parent.parent  # src/atdd  # atdd:suppress(coach.code-roots.no-source-depth-walk) — #1499 ratchet: pre-existing source-depth walk; destination is zero
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

    # -------------------------------------------------------------------------
    # Substrate mode (issue #415, spec v12 §9.3)
    # -------------------------------------------------------------------------
    def detect_substrate_mode_heuristic(self) -> str:
        """Resolve substrate mode purely from filesystem layout.

        Default heuristic per spec v12 §9.3: presence of ``plan/`` AND absence
        of ``src/atdd/`` → consumer-repo mode. Otherwise toolkit mode.

        The toolkit's own checkout has both signals, so the heuristic correctly
        classifies it as toolkit; the override flag (`--consumer-repo`) is
        needed only for dogfooding.
        """
        has_plan = (self.target_dir / "plan").is_dir()
        has_src_atdd = (self.target_dir / "src" / "atdd").is_dir()
        if has_plan and not has_src_atdd:
            return SUBSTRATE_MODE_CONSUMER
        return SUBSTRATE_MODE_TOOLKIT

    def resolve_substrate_mode(
        self,
        force_consumer: bool = False,
        force_toolkit: bool = False,
    ) -> str:
        """Resolve the substrate mode to apply on this `atdd init` run.

        Precedence (high → low):
          1. ``--toolkit`` flag
          2. ``--consumer-repo`` flag
          3. Existing ``repo.substrate.mode`` in ``.atdd/config.yaml``
             (a subsequent bare `atdd init` stays in mode)
          4. Filesystem heuristic (`plan/` ^ `src/atdd/`)
        """
        if force_toolkit:
            return SUBSTRATE_MODE_TOOLKIT
        if force_consumer:
            return SUBSTRATE_MODE_CONSUMER

        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    cfg = yaml.safe_load(f) or {}
            except (yaml.YAMLError, OSError) as exc:
                logger.debug(
                    "substrate mode: cannot read config %s: %s",
                    self.config_file, exc,
                    extra={"path": str(self.config_file), "error_type": type(exc).__name__},
                )
                cfg = {}
            existing_mode = (
                cfg.get("repo", {}).get("substrate", {}).get("mode")
                if isinstance(cfg, dict) else None
            )
            if existing_mode in (SUBSTRATE_MODE_CONSUMER, SUBSTRATE_MODE_TOOLKIT):
                return existing_mode

        return self.detect_substrate_mode_heuristic()

    def _apply_substrate_mode(
        self,
        force_consumer: bool = False,
        force_toolkit: bool = False,
    ) -> str:
        """Resolve mode and write/remove the `repo:` block in `.atdd/config.yaml`.

        Returns the resolved mode string for the caller to print/log.
        """
        mode = self.resolve_substrate_mode(force_consumer, force_toolkit)
        if mode == SUBSTRATE_MODE_CONSUMER:
            self._write_substrate_config()
        else:
            self._remove_substrate_config()
        return mode

    def _write_substrate_config(self) -> None:
        """Write the `repo:` block to `.atdd/config.yaml` (consumer-repo mode).

        Idempotent: rewriting with the same defaults yields no diff. Existing
        non-default values for `test_root` / `plan_root` are preserved.
        """
        if not self.config_file.exists():
            return

        with open(self.config_file) as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict):
            cfg = {}

        existing_repo = cfg.get("repo") if isinstance(cfg.get("repo"), dict) else {}
        existing_substrate = (
            existing_repo.get("substrate")
            if isinstance(existing_repo.get("substrate"), dict) else {}
        )

        repo_block = {
            "test_root": existing_repo.get("test_root", SUBSTRATE_DEFAULT_TEST_ROOT),
            "plan_root": existing_repo.get("plan_root", SUBSTRATE_DEFAULT_PLAN_ROOT),
            "substrate": {
                "enabled": existing_substrate.get("enabled", True),
                "plugin": existing_substrate.get("plugin", SUBSTRATE_PLUGIN_ENTRY_POINT),
                "mode": SUBSTRATE_MODE_CONSUMER,
            },
        }

        if cfg.get("repo") == repo_block:
            return  # already current — no-op

        cfg["repo"] = repo_block
        with open(self.config_file, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        print(f"  Wrote substrate fields to {self.config_file}")

    def _remove_substrate_config(self) -> None:
        """Remove the `repo:` block from `.atdd/config.yaml` (toolkit mode)."""
        if not self.config_file.exists():
            return

        with open(self.config_file) as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict) or "repo" not in cfg:
            return

        del cfg["repo"]
        with open(self.config_file, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        print(f"  Removed substrate fields from {self.config_file}")

    #: Marker identifying a file we wrote, so a refresh can tell an installed
    #: dispatcher apart from something the operator put there.
    _DISPATCHER_MARKER = "ATDD managed hook dispatcher"

    def _dispatcher_body(self, hook_name: str) -> Optional[str]:
        """Render the dispatcher that will be installed for *hook_name*."""
        tpl = self.package_root / "templates" / "hook-dispatcher.sh"
        if not tpl.is_file():
            logger.warning(
                "Hook dispatcher template not found: %s",
                tpl, extra={"path": str(tpl)},
            )
            return None
        return tpl.read_text().replace("__ATDD_HOOK_NAME__", hook_name)

    def _refresh_hook_files(self, force: bool = False) -> int:
        """Install/refresh the git hook dispatcher FILES in .atdd/hooks/ (#1492).

        Each installed hook is a FIXED-CONTENT dispatcher that execs the hook
        shipped inside the installed atdd package. That makes drift structurally
        impossible rather than merely detectable: there is no copied logic left
        to go stale, so `pipx upgrade atdd` propagates a hook fix on its own.

        This used to `shutil.copy2` the template and skip any hook that already
        existed unless ``force``. The installed hook was therefore a point-in-time
        fork, refreshable only by ``atdd init --force`` — the flag that caused
        #793 and is forbidden. Every hook fix reached only repos initialised
        after it landed, and 6 of 11 hooks were never installed at all.

        A refresh is authoritative: it always wins. A hook whose content we do
        not recognise (hand-edited, or stale from a much older version) is
        preserved as ``<hook>.local.bak`` before being replaced, so the refresh
        is non-destructive without ever declining to update.

        Args:
            force: Unused for content decisions — a refresh always rewrites a
                stale hook. Retained for signature compatibility with the
                surrounding init flow.
        """
        hooks_dir = self.atdd_config_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        template_dir = self.package_root / "templates" / "hooks"
        if not template_dir.exists():
            logger.warning("Hook template directory not found: %s", template_dir, extra={"path": str(template_dir)})
            return

        refreshed = 0
        preserved = 0
        for hook_src in sorted(template_dir.iterdir()):
            if hook_src.name.startswith(("__", ".")) or hook_src.is_dir():
                continue

            desired = self._dispatcher_body(hook_src.name)
            if desired is None:
                # Missing dispatcher template: install no content, but still
                # wire core.hooksPath in the caller — that wiring is independent
                # of hook content, and skipping it would leave git pointed at
                # nothing.
                break

            did_refresh, did_preserve = self._refresh_one_hook(
                hook_src, hooks_dir / hook_src.name, desired
            )
            refreshed += int(did_refresh)
            preserved += int(did_preserve)

        if refreshed:
            print(f"Hooks: {refreshed} installed/refreshed → {hooks_dir}")
        else:
            print("Hooks: all current.")
        if preserved:
            print(f"Hooks: {preserved} pre-existing file(s) preserved as *.local.bak")
        return refreshed

    def _refresh_one_hook(
        self, hook_src: Path, hook_dst: Path, desired: str
    ) -> Tuple[bool, bool]:
        """Bring a single installed hook to *desired*, preserving the unknown.

        Returns:
            (refreshed, preserved) — whether the file was written, and whether
            unrecognised prior content was saved as ``<hook>.local.bak`` first.
        """
        preserved = False
        if hook_dst.is_file():
            current = hook_dst.read_text(errors="replace")
            if current == desired:
                return False, False  # already current — nothing to say

            # Recognised content is ours to replace silently: either an older
            # dispatcher, or a pristine copy of the packaged template left by
            # the pre-#1492 copy-install. Anything else is the operator's, and
            # is preserved before being overwritten — the refresh always wins,
            # but never destroys (#1492 Decision #2).
            recognised = (
                self._DISPATCHER_MARKER in current
                or current == hook_src.read_text(errors="replace")
            )
            if not recognised:
                backup = hook_dst.with_name(hook_dst.name + ".local.bak")
                shutil.copy2(hook_dst, backup)
                preserved = True
                print(f"  ! {hook_dst.name}: unrecognised content preserved → {backup.name}")

        hook_dst.write_text(desired)
        os.chmod(hook_dst, hook_dst.stat().st_mode | 0o111)
        return True, preserved

    def refresh_hook_files(self) -> int:
        """Refresh installed hook CONTENT only. Writes no git config (#1492).

        Deliberately separate from ``_install_hooks``: refreshing hook content
        and wiring ``core.hooksPath`` are different concerns with very different
        blast radii. core.hooksPath is a single shared setting governing every
        worktree of the repository, and an unscoped write to it is what caused
        #793. A refresh — which now runs from plain `atdd init` and `atdd sync`,
        i.e. far more often than a first install ever did — must therefore never
        touch git config: it only replaces the files in .atdd/hooks/.

        Returns:
            The number of hooks installed or refreshed.
        """
        return self._refresh_hook_files()

    def _install_hooks(self, force: bool = False) -> None:
        """Install the hook dispatchers AND point git at them.

        First-install path: refreshes the hook files, then wires core.hooksPath.
        Callers that only want current hook content must use
        :meth:`refresh_hook_files` instead — see #793.
        """
        hooks_dir = self.atdd_config_dir / "hooks"
        self._refresh_hook_files(force)

        # Point git to the hooks directory.
        # Wave 12 contamination fix (#793): when running inside a linked (non-main)
        # worktree the unscoped 'git config core.hooksPath' writes to the shared
        # .git/config, contaminating all sibling worktrees.  Use '--worktree' so
        # the entry lands in .git/worktrees/<name>/config.worktree only.
        abs_hooks = str(hooks_dir.resolve())
        try:
            in_linked_worktree = self._is_linked_worktree()
            if in_linked_worktree:
                self._ensure_worktree_config_extension()
                git_config_cmd = ["git", "config", "--worktree", "core.hooksPath", abs_hooks]
            else:
                git_config_cmd = ["git", "config", "core.hooksPath", abs_hooks]
            subprocess.run(
                git_config_cmd,
                capture_output=True, text=True, timeout=10,
                cwd=self.target_dir,
            )
            print(f"Set git core.hooksPath → {abs_hooks}")
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not set core.hooksPath: %s", exc, extra={"path": str(abs_hooks)})

    def install_path_shim_enforcement(self, force: bool = False) -> None:
        """Install the gh-issue-create L3 enforcement layer (issue #816).

        Three idempotent installs that block ``gh issue create`` outside the
        Claude Code PreToolUse hook (#668, L1):

          * ``.atdd/bin/gh`` — the L3a PATH shim (executable) that intercepts
            ``gh issue create`` in any worktree shell and forwards every other
            gh subcommand to the next real gh on PATH.
          * ``.atdd/bin/git`` — the agent-agnostic git shim (#884) that blocks
            unscoped ``git config core.bare``/``core.worktree`` (and
            ``core.hooksPath`` in a linked worktree) writes which would poison
            the shared .git/config, forwarding every other git invocation
            unchanged to the next real git on PATH.
          * ``.envrc`` — a ``PATH_add .atdd/bin`` line so direnv puts the shim
            first on PATH. Appended only when absent (operator edits preserved).
          * ``.atdd/hooks/pre-commit-gh-issue-create.sh`` — the L3b pre-commit
            hook that greps the staged diff for baked-in ``gh issue create``
            calls (``*.md`` exempt).

        Soft-fails (warns, never raises) when ``direnv`` is not on PATH — the
        shim is installed but inert until the operator installs/hooks direnv.

        Convention: src/atdd/coach/conventions/path_shim_gh.convention.yaml
        """
        templates = self.package_root / "templates"
        self._install_executable_template(
            templates / "bin" / "gh.shim",
            self.atdd_config_dir / "bin" / "gh",
            missing_label="gh shim",
        )
        # Agent-agnostic git shim (#884): blocks unscoped core.bare/core.worktree
        # (and core.hooksPath in a linked worktree) writes that poison the shared
        # .git/config, forwarding every other git invocation unchanged.
        self._install_executable_template(
            templates / "bin" / "git.shim",
            self.atdd_config_dir / "bin" / "git",
            missing_label="git shim",
        )
        self._append_envrc_path_add()
        self._install_executable_template(
            templates / "hooks" / "pre-commit-gh-issue-create.sh",
            self.atdd_config_dir / "hooks" / "pre-commit-gh-issue-create.sh",
            missing_label="gh pre-commit hook",
        )
        self._warn_if_direnv_missing()

    def _install_executable_template(
        self, src: Path, dst: Path, *, missing_label: str
    ) -> None:
        """Copy *src* → *dst* (creating parents) and mark it executable.

        Logs a warning and no-ops when the template is absent so a partial
        package install degrades gracefully rather than raising.
        """
        if not src.exists():
            logger.warning(
                "%s template not found: %s", missing_label, src,
                extra={"path": str(src)},
            )
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        os.chmod(dst, dst.stat().st_mode | 0o111)
        print(f"Installed: {dst}")

    def _append_envrc_path_add(self) -> None:
        """Append ``PATH_add .atdd/bin`` to ``.envrc`` if not already present.

        Idempotent: a re-run never duplicates the line, and existing operator
        edits to ``.envrc`` are preserved (the line is appended, not rewritten).
        """
        envrc = self.target_dir / ".envrc"
        path_add_line = "PATH_add .atdd/bin"
        existing = envrc.read_text() if envrc.is_file() else ""
        if any(ln.strip() == path_add_line for ln in existing.splitlines()):
            return
        if existing and not existing.endswith("\n"):
            existing += "\n"
        envrc.write_text(f"{existing}{path_add_line}\n")
        print(f"Added '{path_add_line}' to .envrc")

    def _warn_if_direnv_missing(self) -> None:
        """Print a soft-fail notice when ``direnv`` is absent from PATH."""
        if shutil.which("direnv") is None:
            print(
                "Warning: direnv not found on PATH — the .atdd/bin/gh shim is "
                "installed but will not take effect until you install direnv "
                "and run `direnv allow`. (gh issue create stays blocked by the "
                "L1 hook and L3b pre-commit in the meantime.)"
            )

    def _install_harness(self, force: bool = False) -> None:
        """Install train-render harness templates into ``.atdd/harness/``.

        Only runs when the consumer repo has a ``web/`` directory — repos
        without a frontend (toolkit-self, BE-only consumers) get nothing
        and the validator opt-in stays at its default ``enabled: false``.

        See ``src/atdd/tester/conventions/smoke.convention.yaml >
        behavioral_render`` for the harness contract (#335).
        """
        if not (self.target_dir / "web").exists():
            return

        harness_dir = self.atdd_config_dir / "harness"
        harness_dir.mkdir(parents=True, exist_ok=True)

        template_dir = self.package_root / "templates" / "harness"
        if not template_dir.exists():
            logger.warning(
                "Harness template directory not found: %s",
                template_dir,
                extra={"path": str(template_dir)},
            )
            return

        installed = 0
        for src in sorted(template_dir.iterdir()):
            if src.name.startswith(("__", ".")) or src.is_dir():
                continue
            dst = harness_dir / src.name
            if dst.exists() and not force:
                print(f"Harness file exists (skip): {dst}")
                continue
            shutil.copy2(src, dst)
            print(f"Installed: {dst}")
            installed += 1

        if installed == 0 and not force:
            print("All harness templates already installed.")

    def is_initialized(self) -> bool:
        """Check if ATDD is already initialized in target directory.

        #1270 Slice G: keyed on ``.atdd/config.yaml`` — the manifest mirror it
        used to check was deleted and is no longer written at genesis.
        """
        return self.atdd_config_dir.exists() and self.config_file.exists()

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
        except (FileNotFoundError, subprocess.TimeoutExpired):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (FileNotFoundError, subprocess.TimeoutExpired):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
            except (yaml.YAMLError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
                pass

        if skip_workflows:
            print("Workflows: skipped (init.skip_workflows=true in config)")
            workflow_written = False
            publish_written = False
        else:
            workflow_written = self._write_workflow(repo)
            infra_written = self._write_infra_workflow()
            publish_written = self._write_publish_workflow()
            self._write_auto_phase_workflow()

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
        """Projects v2 board decommissioned (#1051/#1072) — no-op stub.

        The coach no longer creates or syncs an "ATDD Sessions" Project v2
        board; phase state is the ``atdd:<phase>`` label + ``.atdd/manifest
        .yaml`` (the source of truth). Returns the ``(id, number, created)``
        contract as ``(None, None, False)`` so callers guarded on
        ``if project_id:`` skip all board work.
        """
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
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            return False

    def _create_project_fields(self, project_id: str) -> int:
        """Create/migrate custom fields on a Project v2 from schema. Returns count changed."""
        schema_path = self.package_root / "schemas" / "project_fields.schema.json"
        if not schema_path.exists():
            return 0

        with open(schema_path) as f:
            schema = json.load(f)

        # Pass 1: migrate — rename old-name fields, delete deprecated ones
        existing = self._query_project_field_names_and_ids(project_id)
        migrated = self._migrate_project_fields(project_id, existing)

        # Pass 2: re-query after migration
        if migrated:
            existing = self._query_project_field_names_and_ids(project_id)

        # Pass 3: create any still-missing fields from schema
        created = self._create_missing_fields(project_id, schema, set(existing.keys()))

        return migrated + created

    def _migrate_project_fields(self, project_id: str, existing: Dict[str, str]) -> int:
        """Rename renamed fields and delete deprecated ones. Returns count changed."""
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

        return migrated

    def _create_missing_fields(
        self, project_id: str, schema: dict, existing_names: set
    ) -> int:
        """Create every schema-declared field the project does not carry yet."""
        created = 0
        defs = schema.get("$defs", {})

        for scope in ["parent_fields", "sub_issue_fields"]:
            for field_spec in defs.get(scope, {}).get("properties", {}).values():
                field_props = field_spec.get("properties", {})
                name = field_props.get("name", {}).get("const")
                data_type = field_props.get("data_type", {}).get("const")

                if not name or not data_type or name in existing_names:
                    continue

                mutation = self._field_create_mutation(
                    project_id, name, data_type, field_spec
                )
                if self._run_field_mutation(mutation):
                    created += 1

        return created

    @staticmethod
    def _field_create_mutation(
        project_id: str, name: str, data_type: str, field_spec: dict
    ) -> str:
        """The createProjectV2Field mutation for one field."""
        if data_type != "SINGLE_SELECT":
            return (
                f'mutation {{ createProjectV2Field(input: {{ '
                f'projectId: "{project_id}", dataType: {data_type}, '
                f'name: "{name}" '
                f'}}) {{ projectV2Field {{ ... on ProjectV2Field {{ id }} }} }} }}'
            )

        options = field_spec.get("properties", {}).get("options", {})
        options_str = ", ".join(
            f'{{name: "{item["properties"]["name"]["const"]}", '
            f'description: "{item["properties"]["description"]["const"]}", '
            f'color: {item["properties"]["color"]["const"]}}}'
            for item in options.get("prefixItems", [])
            if "properties" in item
        )
        return (
            f'mutation {{ createProjectV2Field(input: {{ '
            f'projectId: "{project_id}", dataType: {data_type}, '
            f'name: "{name}", singleSelectOptions: [{options_str}] '
            f'}}) {{ projectV2Field {{ ... on ProjectV2SingleSelectField {{ id }} }} }} }}'
        )

    @staticmethod
    def _run_field_mutation(mutation: str) -> bool:
        """Run one field mutation via gh. False when gh is absent or times out."""
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            return False

    # Default path → phase mappings for path-scoped validation
    DEFAULT_PATH_FILTERS = {
        "planner": ["plan/**"],
        "tester": ["contracts/**", "telemetry/**"],
        "coder": ["web/**", "python/**", "packages/**", "supabase/**", "src/**"],
        "coach": [".atdd/**", ".github/**"],
        # SMOKE phase (issue #293): trigger when web/ or e2e/ change so the
        # opt-in Playwright job runs against the current branch's deploy preview.
        "smoke": ["web/**", "e2e/**"],
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
        # SMOKE phase (issue #293) participates in the gate but ships its own
        # job shape (Playwright + opt-in via SMOKE_BASE_URL), so it is fanned
        # in via validate-gate.needs but not generated through phase_jobs.
        gate_phases = phases + ["smoke"]

        # Merge default path filters with config overrides
        filters = dict(self.DEFAULT_PATH_FILTERS)
        config_path = self.target_dir / ".atdd" / "config.yaml"
        if config_path.exists():
            try:
                cfg = yaml.safe_load(config_path.read_text()) or {}
                if "path_filters" in cfg:
                    filters.update(cfg["path_filters"])
            except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
                pass

        # Build dorny/paths-filter filter config (plain YAML, no f-string interpolation)
        filter_lines = []
        for phase in gate_phases:
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
            "      smoke: ${{ steps.filter.outputs.smoke }}\n"
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
        run: atdd validate {phase}{' --skip-api' if phase == 'coach' else ''}
        env:
          GH_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
"""

        needs_list = ", ".join(f"validate-{p}" for p in gate_phases)

        # SMOKE phase job (issue #293): opt-in via SMOKE_BASE_URL repo secret.
        # When unset, the job exits success after a no-op step and the gate
        # fan-in accepts it. When set, Playwright runs e2e/**/*smoke*.spec.ts
        # against that base URL and the gate fails on any failure.
        smoke_job = (
            "\n"
            "  validate-smoke:\n"
            "    needs: [detect-changes]\n"
            "    runs-on: ubuntu-latest\n"
            "    if: >-\n"
            "      always() && (\n"
            f"        (github.event_name == 'issues' && ({label_condition})) ||\n"
            "        (github.event_name != 'issues' && needs.detect-changes.outputs.smoke == 'true')\n"
            "      )\n"
            "    env:\n"
            "      SMOKE_BASE_URL: ${{ secrets.SMOKE_BASE_URL }}\n"
            "    steps:\n"
            "      - name: Skip when SMOKE_BASE_URL is unset\n"
            "        if: env.SMOKE_BASE_URL == ''\n"
            "        run: |\n"
            '          echo "SMOKE_BASE_URL not configured — skipping Playwright smoke run."\n'
            '          echo "(Set the SMOKE_BASE_URL repo secret to enable runtime smoke verification.)"\n'
            "\n"
            "      - uses: actions/checkout@v4\n"
            "        if: env.SMOKE_BASE_URL != ''\n"
            "        with:\n"
            "          fetch-depth: 0\n"
            "\n"
            "      - uses: actions/setup-node@v4\n"
            "        if: env.SMOKE_BASE_URL != ''\n"
            "        with:\n"
            '          node-version: "20"\n'
            "\n"
            "      - name: Install Playwright\n"
            "        if: env.SMOKE_BASE_URL != ''\n"
            "        run: |\n"
            "          if [ -f package.json ]; then\n"
            "            npm ci\n"
            "          else\n"
            "            npm init -y\n"
            "            npm install --save-dev @playwright/test\n"
            "          fi\n"
            "          npx playwright install --with-deps chromium\n"
            "\n"
            "      - name: Run e2e smoke specs\n"
            "        if: env.SMOKE_BASE_URL != ''\n"
            '        run: npx playwright test "e2e/**/*smoke*.spec.ts"\n'
        )

        # Build validate-gate job as plain string (complex ${{ }} expressions)
        gate_job = (
            "\n"
            "  validate-gate:\n"
            "    needs: [validate-planner, validate-tester, validate-coder, validate-coach, validate-smoke]\n"
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
            '                        "coach:${{ needs.validate-coach.result }}" \\\n'
            '                        "smoke:${{ needs.validate-smoke.result }}"; do\n'
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

        # NOTE: the `baseline-sync` job was RETIRED (#481). It emitted
        # `run: atdd baseline update` — a subcommand the 3.x CLI never
        # declared — which failed `invalid choice: 'baseline'` on every
        # push to main. Ratchet baselines (#223) were superseded by
        # disposition gates (#395), so the job was dead scaffolding.
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
            f"jobs:{detect_changes_job}{phase_jobs}{smoke_job}{gate_job}"
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
            '        run: atdd validate coach --api-only\n'
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

    def _write_auto_phase_workflow(self) -> bool:
        """Copy .github/workflows/atdd-auto-phase.yml from the package template.

        Required by issue #355 / test_auto_phase_workflow_exists.py: the
        coach validator hard-fails if this file is missing from the consumer
        repo. The template is shipped under
        ``src/atdd/coach/templates/workflows/atdd-auto-phase.yml`` so it
        installs with the package.
        """
        template = self.package_root / "templates" / "workflows" / "atdd-auto-phase.yml"
        if not template.is_file():
            logger.warning(
                "Auto-phase workflow template missing: %s", template,
                extra={"path": str(template)},
            )
            return False

        workflows_dir = self.target_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        dest = workflows_dir / "atdd-auto-phase.yml"

        shutil.copy2(template, dest)
        print(f"  Wrote: {dest}")
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
        except (subprocess.TimeoutExpired, FileNotFoundError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
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


# Public alias: the class is named ProjectInitializer internally, but
# external callers (tests, `atdd init` CLI) import it as `Initializer`
# so the type name matches the command surface.
Initializer = ProjectInitializer
