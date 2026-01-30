"""
Project initializer for ATDD structure in consumer repos.

Creates the following structure:
    consumer-repo/
    ├── CLAUDE.md                (with managed ATDD block)
    ├── atdd-sessions/
    │   ├── SESSION-TEMPLATE.md  (copied from package)
    │   └── archive/
    └── .atdd/
        ├── manifest.yaml        (machine-readable session tracking)
        └── config.yaml          (agent sync configuration)

Usage:
    atdd init                    # Initialize ATDD structure
    atdd init --force            # Overwrite existing files

Convention: src/atdd/coach/conventions/session.convention.yaml
"""
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


class ProjectInitializer:
    """Initialize ATDD structure in consumer repo."""

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the ProjectInitializer.

        Args:
            target_dir: Target directory for initialization. Defaults to cwd.
        """
        self.target_dir = target_dir or Path.cwd()
        self.sessions_dir = self.target_dir / "atdd-sessions"
        self.archive_dir = self.sessions_dir / "archive"
        self.atdd_config_dir = self.target_dir / ".atdd"
        self.manifest_file = self.atdd_config_dir / "manifest.yaml"
        self.config_file = self.atdd_config_dir / "config.yaml"

        # Package template location
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.template_source = self.package_root / "templates" / "SESSION-TEMPLATE.md"

    def init(self, force: bool = False) -> int:
        """
        Create atdd-sessions/ and .atdd/ structure.

        Args:
            force: If True, overwrite existing files.

        Returns:
            0 on success, 1 on error.
        """
        # Check if already initialized
        if self.sessions_dir.exists() and not force:
            print(f"ATDD already initialized at {self.target_dir}")
            print("Use --force to reinitialize")
            return 1

        try:
            # Create atdd-sessions/ directory
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.sessions_dir}")

            # Create archive subdirectory
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.archive_dir}")

            # Create .atdd/ config directory
            self.atdd_config_dir.mkdir(parents=True, exist_ok=True)
            print(f"Created: {self.atdd_config_dir}")

            # Copy SESSION-TEMPLATE.md to atdd-sessions/
            template_dest = self.sessions_dir / "SESSION-TEMPLATE.md"
            if self.template_source.exists():
                shutil.copy2(self.template_source, template_dest)
                print(f"Copied: SESSION-TEMPLATE.md -> {template_dest}")
            else:
                print(f"Warning: Template not found at {self.template_source}")

            # Create manifest.yaml
            self._create_manifest(force)

            # Create config.yaml
            self._create_config(force)

            # Sync agent config files
            from atdd.coach.commands.sync import AgentConfigSync
            syncer = AgentConfigSync(self.target_dir)
            syncer.sync()

            # Print next steps
            print("\n" + "=" * 60)
            print("ATDD initialized successfully!")
            print("=" * 60)
            print("\nNext steps:")
            print("  1. Create a new session:")
            print("     atdd session new my-feature")
            print("")
            print("  2. List existing sessions:")
            print("     atdd session list")
            print("")
            print("  3. Archive completed sessions:")
            print("     atdd session archive 01")
            print("")
            print("Structure created:")
            print(f"  {self.sessions_dir}/")
            print(f"  {self.sessions_dir}/archive/")
            print(f"  {self.sessions_dir}/SESSION-TEMPLATE.md")
            print(f"  {self.atdd_config_dir}/")
            print(f"  {self.manifest_file}")
            print(f"  {self.config_file}")
            print(f"  CLAUDE.md (with ATDD managed block)")

            return 0

        except PermissionError as e:
            print(f"Error: Permission denied - {e}")
            return 1
        except OSError as e:
            print(f"Error: {e}")
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
            "version": "1.0",
            "sessions_dir": "atdd-sessions",
            "created": date.today().isoformat(),
            "sessions": [],
        }

        with open(self.manifest_file, "w") as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {self.manifest_file}")

    def _create_config(self, force: bool = False) -> None:
        """
        Create or update .atdd/config.yaml.

        Args:
            force: If True, overwrite existing config.
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

        config = {
            "version": "1.0",
            "sync": {
                "agents": ["claude"],  # Default: only Claude
            },
            "toolkit": {
                "last_version": toolkit_version,  # Track installed version
            },
        }

        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"Created: {self.config_file}")

    def is_initialized(self) -> bool:
        """Check if ATDD is already initialized in target directory."""
        return self.sessions_dir.exists() and self.manifest_file.exists()
