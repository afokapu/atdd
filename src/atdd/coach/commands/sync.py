"""
Refresh an already-initialised ATDD checkout.

This module is NOT an agent-config sync any more, whatever its filename
suggests. #1811 retired the projection that combined a CONDUCTOR.md template
with per-agent overlays into managed blocks in CLAUDE.md / AGENTS.md /
GEMINI.md / GLM.md; #1861 swept its residue out of the gate, and #1940 deleted
the artifacts and the overlays it had left behind.

What `atdd sync` does now is the reason the verb still exists: `atdd init`
bails out on an initialised repo before it seeds anything and `atdd init
--force` is forbidden (#793), so this is the only sanctioned path that reaches
an existing checkout with a hook fix (#1492), the operational `.gitignore`
entries (#1325), exported schemas, or a toolkit stamp (#1641).

Usage:
    atdd sync                    # Refresh this checkout

Convention: src/atdd/coach/conventions/issue.convention.yaml
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from atdd.coach.utils.theme_map import DEFAULT_THEME_MAP, get_theme_map


class RepoRefresh:
    """Refresh an already-initialised checkout: hooks, gitignore, stamp."""




    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the AgentConfigSync.

        Args:
            target_dir: Target directory for agent config files. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package resource locations
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.templates_dir = self.package_root / "templates"

    def sync(self, agents: Optional[List[str]] = None) -> int:
        """Refresh what an already-initialised repo cannot refresh any other way.

        #1811 removed the agent-config projection this verb was built around.
        What remains is the reason the verb still has to exist: `atdd init` bails
        out on an initialised repo before it seeds anything, and `atdd init
        --force` is forbidden (#793), so this is the ONLY sanctioned path that
        reaches an existing checkout with a hook fix (#1492), the operational
        `.gitignore` entries (#1325), or a toolkit stamp (#1641).

        `agents` is accepted and ignored: the CLI flag is gone, and the parameter
        stays only so an out-of-tree caller passing it does not crash on upgrade.
        """
        del agents  # the projection it selected no longer exists

        # Refresh exported schemas if .atdd/schemas/ exists
        schemas_dir = self.atdd_config_dir / "schemas"
        if schemas_dir.is_dir():
            from atdd.coach.commands.initializer import ProjectInitializer
            schema_initializer = ProjectInitializer(self.target_dir)
            schema_initializer.export_schemas()

        # Refresh the installed git hooks (#1492).
        #
        # `atdd sync` is the verb the upgrade banner tells operators to run
        # ("Run: atdd sync && atdd init"), and it is the verb that stamps
        # toolkit.last_version to clear that banner — but it did not touch
        # hooks at all. Combined with `atdd init` bailing out on an already
        # initialised repo, NO sanctioned path refreshed a hook: the only one
        # was `atdd init --force`, which is forbidden (#793). So every hook fix
        # ever made reached only repos initialised after it landed.
        #
        # Only refresh a repo that already has hooks installed — sync is not
        # an installer, and must not create .atdd/hooks/ in a repo that never
        # ran `atdd init`.
        # Content only — sync must never write core.hooksPath. That setting is
        # shared by every worktree of the repo, and an unscoped write to it is
        # what caused #793; `sync` runs far too often to be touching it.
        if (self.atdd_config_dir / "hooks").is_dir():
            from atdd.coach.commands.initializer import ProjectInitializer
            hook_initializer = ProjectInitializer(self.target_dir)
            hook_initializer.refresh_hook_files()

        # Re-seed the .gitignore entries for atdd's operational artifacts (#1325
        # item 6), for the same reason the hooks above are refreshed (#1492).
        #
        # Seeding only at `atdd init` reaches brand-new repos and nobody else:
        # init bails out on an already-initialised repo before it seeds, and
        # `atdd init --force` is forbidden (#793). The case actually reported in
        # #1325 was a manifest→State-Store MIGRATION inside a repo that had long
        # since run init, which left `.atdd/state/state.sqlite` and
        # `.atdd/manifest.migrated.yaml` untracked. `atdd sync` is the sanctioned
        # refresh verb, so it is the path that reaches those repos.
        #
        # Guarded on `.atdd/` already existing: sync is a refresher, not an
        # installer, and must not write atdd's ignore entries into a repo that
        # never ran `atdd init`. Each entry is appended idempotently.
        if self.atdd_config_dir.is_dir():
            from atdd.coach.commands.initializer import ProjectInitializer
            gitignore_initializer = ProjectInitializer(self.target_dir)
            gitignore_initializer._seed_gitignore_entries()

        # Apply branch protection if upgrading
        self._apply_branch_protection_on_upgrade()

        # Record the sync in this checkout's untracked runtime record (#1641).
        # NOT .atdd/config.yaml: that file is git-tracked, so the stamp was
        # reverted by every checkout/stash and absent in every fresh worktree.
        from atdd.version_check import record_toolkit_sync
        if record_toolkit_sync(self.target_dir):
            from atdd import __version__
            print(f"Recorded toolkit sync at {__version__}")

        return 0

    def _apply_branch_protection_on_upgrade(self) -> None:
        """Apply branch protection if toolkit was upgraded.

        Detects upgrade by comparing installed version vs toolkit.last_version
        in .atdd/config.yaml. If upgraded, applies branch protection rules
        so consumer repos inherit the latest GitHub infrastructure, then
        verifies the result to surface drift or degraded mode.
        """
        from atdd import __version__
        from atdd.version_check import _is_newer, _get_last_toolkit_version

        config = self._load_config()
        last_version = _get_last_toolkit_version(config)

        # Only apply on upgrade (not first run or same version)
        if last_version is None or not _is_newer(__version__, last_version):
            return

        # Need repo from config
        github_config = config.get("github", {})
        repo = github_config.get("repo")
        if not repo:
            return

        print("\nApplying GitHub infrastructure updates...")
        from atdd.coach.commands.branch_protection import (
            apply_and_verify,
            ProtectionStatus,
        )

        status, details = apply_and_verify(repo)
        if status == ProtectionStatus.DRIFTED:
            print("  Branch protection: DRIFTED (policy mismatch after apply)")
            for d in details:
                print(f"    - {d}")
        elif status == ProtectionStatus.MISSING:
            print("  Branch protection: MISSING (not set on main)")
        elif status == ProtectionStatus.DEGRADED:
            print("  Branch protection: DEGRADED (cannot verify)")
            for d in details:
                print(f"    - {d}")
        elif status == ProtectionStatus.ENFORCED:
            print("  Branch protection: verified")

    # --- Private helpers ---

    def _load_config(self) -> Dict:
        """
        Read .atdd/config.yaml.

        Returns:
            Config dict or empty dict if file doesn't exist.
        """
        if not self.config_file.exists():
            return {}

        with open(self.config_file) as f:
            return yaml.safe_load(f) or {}

