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
    is_outdated,
    auto_upgrade,
)


class Upgrader:
    """Orchestrates atdd upgrade in a consumer repo."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()

    def run(self, yes: bool = False, no_pypi: bool = False) -> int:
        """Run the upgrade process.

        Args:
            yes: Skip confirmation prompts.
            no_pypi: Skip the live PyPI check (use local state only).

        Returns:
            0 on success, 1 on failure.
        """
        config, config_path = _load_repo_config()
        if config is None:
            print("Not an ATDD repo (no .atdd/config.yaml). Nothing to upgrade.")
            return 1

        installed = __version__
        latest: Optional[str] = None

        # 1. Query PyPI for the real latest version (unless --no-pypi).
        if not no_pypi:
            outdated, _, latest = is_outdated()
            if latest and outdated:
                print(f"New version on PyPI: {installed} → {latest}")
                if not yes:
                    answer = input(
                        f"Run `pip install --upgrade atdd` now? [Y/n] "
                    ).strip().lower()
                    if answer and answer != "y":
                        print("Skipping pip upgrade. Continuing with sync step only.")
                    else:
                        print("Running: pip install --upgrade atdd")
                        if not auto_upgrade():
                            print(
                                "pip upgrade failed. Run manually: "
                                "pip install --upgrade atdd"
                            )
                            return 1
                        print(
                            f"pip upgraded atdd to {latest}. "
                            "Re-run `atdd upgrade` to finish sync with the new version."
                        )
                        return 0
                else:
                    print("Running: pip install --upgrade atdd")
                    if not auto_upgrade():
                        print(
                            "pip upgrade failed. Run manually: "
                            "pip install --upgrade atdd"
                        )
                        return 1
                    print(
                        f"pip upgraded atdd to {latest}. "
                        "Re-run `atdd upgrade` to finish sync with the new version."
                    )
                    return 0
            elif not latest:
                print("(Could not reach PyPI — skipping live version check.)")

        # 2. Local sync path: compare stamped last_version against installed.
        last_version = _get_last_toolkit_version(config) or "unknown"

        print(f"ATDD sync: {last_version} → {installed}")
        print()

        # Show what changed
        if last_version != "unknown":
            notes = get_upgrade_notes(last_version, installed)
            if notes:
                print("What changed:")
                for version, note in notes:
                    print(f"  {version}: {note}")
                print()
            else:
                print("No notable changes between these versions.")
                print()

        if last_version == installed:
            print("Already in sync with installed version.")
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
            print(f"\nUpdated toolkit.last_version to {installed}")

        print(f"\nSync complete: {last_version} → {installed}")
        return 0
