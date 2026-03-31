"""
ATDD upgrade orchestration.

Shows what changed between installed and last_version,
then runs sync + init --force with confirmation.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from atdd import __version__
from atdd.version_check import (
    get_upgrade_notes,
    _load_repo_config,
    _get_last_toolkit_version,
    update_toolkit_version,
)


class Upgrader:
    """Orchestrates atdd upgrade in a consumer repo."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()

    def run(self, yes: bool = False) -> int:
        """Run the upgrade process.

        Args:
            yes: Skip confirmation prompts.

        Returns:
            0 on success, 1 on failure.
        """
        config, config_path = _load_repo_config()
        if config is None:
            print("Not an ATDD repo (no .atdd/config.yaml). Nothing to upgrade.")
            return 1

        last_version = _get_last_toolkit_version(config) or "unknown"
        current = __version__

        print(f"ATDD upgrade: {last_version} → {current}")
        print()

        # Show what changed
        if last_version != "unknown":
            notes = get_upgrade_notes(last_version, current)
            if notes:
                print("What changed:")
                for version, note in notes:
                    print(f"  {version}: {note}")
                print()
            else:
                print("No notable changes between these versions.")
                print()

        if last_version == current:
            print("Already up to date.")
            return 0

        # Confirm
        if not yes:
            print("This will run:")
            print("  1. atdd sync       (update agent config files)")
            print("  2. atdd init --force (update GitHub infrastructure)")
            print()
            answer = input("Proceed? [Y/n] ").strip().lower()
            if answer and answer != "y":
                print("Aborted.")
                return 1

        # Run sync
        print()
        print("Running: atdd sync")
        rc = subprocess.run(
            [sys.executable, "-m", "atdd", "sync"],
            cwd=str(self.repo_root),
        ).returncode
        if rc != 0:
            print(f"atdd sync failed (exit {rc})")
            return 1

        # Run init --force
        print()
        print("Running: atdd init --force")
        rc = subprocess.run(
            [sys.executable, "-m", "atdd", "init", "--force"],
            cwd=str(self.repo_root),
        ).returncode
        if rc != 0:
            print(f"atdd init --force failed (exit {rc})")
            return 1

        # Update last_version
        if config_path:
            update_toolkit_version(config_path)
            print(f"\nUpdated toolkit.last_version to {current}")

        print(f"\nUpgrade complete: {last_version} → {current}")
        return 0
