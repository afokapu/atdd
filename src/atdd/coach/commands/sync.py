"""
Agent config file sync for ATDD managed blocks.

Syncs ATDD rules to agent config files (CLAUDE.md, AGENTS.md, etc.) using
managed blocks that preserve user content while keeping rules in sync.

Block format:
    # --- ATDD:BEGIN (managed by atdd, do not edit) ---
    <content from ATDD.md>
    <optional overlay for that agent>
    # --- ATDD:END ---

Usage:
    atdd sync                    # Sync all enabled agents from config
    atdd sync --agent claude     # Sync specific agent only
    atdd sync --verify           # Check if files are in sync (for CI)

Convention: src/atdd/coach/conventions/session.convention.yaml
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


class AgentConfigSync:
    """Sync managed ATDD blocks to agent config files."""

    AGENT_FILES = {
        "claude": "CLAUDE.md",
        "codex": "AGENTS.md",
        "gemini": "GEMINI.md",
        "qwen": "QWEN.md",
    }

    BLOCK_BEGIN = "# --- ATDD:BEGIN (managed by atdd, do not edit) ---"
    BLOCK_END = "# --- ATDD:END ---"

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
        self.overlays_dir = self.package_root / "overlays"
        self.atdd_template = self.templates_dir / "ATDD.md"

    def sync(self, agents: Optional[List[str]] = None) -> int:
        """
        Sync managed blocks to agent config files.

        Args:
            agents: List of agents to sync. If None, read from config.

        Returns:
            0 on success, 1 on error.
        """
        # Determine which agents to sync
        if agents is None:
            agents = self._get_enabled_agents()

        if not agents:
            print("No agents configured for sync.")
            print("Add agents to .atdd/config.yaml or use --agent flag.")
            return 0

        # Validate agent names
        invalid_agents = [a for a in agents if a not in self.AGENT_FILES]
        if invalid_agents:
            print(f"Error: Unknown agent(s): {', '.join(invalid_agents)}")
            print(f"Valid agents: {', '.join(sorted(self.AGENT_FILES.keys()))}")
            return 1

        # Load base content
        base_content = self._load_base_content()
        if base_content is None:
            print(f"Error: ATDD template not found: {self.atdd_template}")
            return 1

        synced_count = 0
        unchanged_count = 0

        for agent in agents:
            target_file = self.AGENT_FILES[agent]
            target_path = self.target_dir / target_file

            # Generate new managed block
            new_block = self._generate_block(agent, base_content)

            # Read existing content
            existing_content = self._read_target(agent)

            # Update content
            if self._has_managed_block(existing_content):
                updated_content = self._replace_managed_block(existing_content, new_block)
            else:
                updated_content = self._append_managed_block(existing_content, new_block)

            # Write only if changed
            if updated_content != existing_content:
                target_path.write_text(updated_content)
                print(f"Synced: {target_file}")
                synced_count += 1
            else:
                print(f"Up to date: {target_file}")
                unchanged_count += 1

        print(f"\nSync complete: {synced_count} updated, {unchanged_count} unchanged")
        return 0

    def verify(self) -> int:
        """
        Verify that agent config files are in sync with ATDD template.

        Returns:
            0 if all files are in sync, 1 if any file is out of sync.
        """
        agents = self._get_enabled_agents()

        if not agents:
            print("No agents configured for verification.")
            return 0

        base_content = self._load_base_content()
        if base_content is None:
            print(f"Error: ATDD template not found: {self.atdd_template}")
            return 1

        out_of_sync = []
        missing = []

        for agent in agents:
            target_file = self.AGENT_FILES[agent]
            target_path = self.target_dir / target_file

            if not target_path.exists():
                missing.append(target_file)
                continue

            # Generate expected block
            expected_block = self._generate_block(agent, base_content)

            # Read existing content
            existing_content = target_path.read_text()

            # Extract existing managed block
            existing_block, _, _ = self._extract_managed_block(existing_content)

            if existing_block is None:
                out_of_sync.append((target_file, "missing managed block"))
            elif existing_block.strip() != expected_block.strip():
                out_of_sync.append((target_file, "content mismatch"))

        # Report results
        if missing:
            print("Missing files:")
            for f in missing:
                print(f"  - {f}")

        if out_of_sync:
            print("Out of sync:")
            for f, reason in out_of_sync:
                print(f"  - {f}: {reason}")

        if missing or out_of_sync:
            print(f"\nRun 'atdd sync' to fix.")
            return 1

        print("All agent config files are in sync.")
        return 0

    def status(self) -> int:
        """
        Show sync status for all agent config files.

        Returns:
            0 on success.
        """
        agents = self._get_enabled_agents()

        print("\n" + "=" * 60)
        print("ATDD Agent Config Sync Status")
        print("=" * 60)

        print(f"\nConfig file: {self.config_file}")
        print(f"ATDD template: {self.atdd_template}")
        print(f"Overlays dir: {self.overlays_dir}")

        print(f"\n{'Agent':<10} {'File':<15} {'Status':<20}")
        print("-" * 50)

        for agent, target_file in sorted(self.AGENT_FILES.items()):
            target_path = self.target_dir / target_file
            enabled = agent in agents

            if not enabled:
                status = "disabled"
            elif not target_path.exists():
                status = "missing"
            elif not self._has_managed_block(target_path.read_text()):
                status = "no managed block"
            else:
                status = "synced"

            enabled_marker = "*" if enabled else " "
            print(f"{enabled_marker} {agent:<8} {target_file:<15} {status:<20}")

        print("-" * 50)
        print("* = enabled in config")

        # Show overlay status
        print("\nOverlays:")
        for agent in sorted(self.AGENT_FILES.keys()):
            overlay_path = self.overlays_dir / f"{agent}.md"
            if overlay_path.exists():
                print(f"  - {agent}.md (found)")

        return 0

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

    def _get_enabled_agents(self) -> List[str]:
        """
        Return agents from config.

        Returns:
            List of agent names enabled for sync.
        """
        config = self._load_config()
        sync_config = config.get("sync", {})
        return sync_config.get("agents", [])

    def _load_base_content(self) -> Optional[str]:
        """
        Read ATDD.md from package.

        Returns:
            Content of ATDD.md or None if not found.
        """
        if not self.atdd_template.exists():
            return None

        return self.atdd_template.read_text()

    def _load_overlay(self, agent: str) -> Optional[str]:
        """
        Read overlays/<agent>.md if exists.

        Args:
            agent: Agent name.

        Returns:
            Overlay content or None if not found.
        """
        overlay_path = self.overlays_dir / f"{agent}.md"
        if not overlay_path.exists():
            return None

        return overlay_path.read_text()

    def _generate_block(self, agent: str, base_content: str) -> str:
        """
        Combine base + overlay into managed block.

        Args:
            agent: Agent name.
            base_content: Content from ATDD.md.

        Returns:
            Complete managed block with markers.
        """
        parts = [self.BLOCK_BEGIN, "", base_content.strip()]

        overlay = self._load_overlay(agent)
        if overlay:
            parts.append("")
            parts.append(f"# Agent-specific: {agent}")
            parts.append(overlay.strip())

        parts.append("")
        parts.append(self.BLOCK_END)

        return "\n".join(parts)

    def _read_target(self, agent: str) -> str:
        """
        Read existing agent config file or return empty string.

        Args:
            agent: Agent name.

        Returns:
            File content or empty string if file doesn't exist.
        """
        target_file = self.AGENT_FILES[agent]
        target_path = self.target_dir / target_file

        if not target_path.exists():
            return ""

        return target_path.read_text()

    def _has_managed_block(self, content: str) -> bool:
        """
        Check if content has a managed ATDD block.

        Args:
            content: File content.

        Returns:
            True if managed block exists.
        """
        return self.BLOCK_BEGIN in content and self.BLOCK_END in content

    def _extract_managed_block(self, content: str) -> Tuple[Optional[str], int, int]:
        """
        Extract managed block from content.

        Args:
            content: File content.

        Returns:
            Tuple of (block_content, start_index, end_index).
            Returns (None, -1, -1) if block not found.
        """
        begin_idx = content.find(self.BLOCK_BEGIN)
        if begin_idx == -1:
            return (None, -1, -1)

        end_idx = content.find(self.BLOCK_END, begin_idx)
        if end_idx == -1:
            # Malformed: BEGIN without END
            print(f"Warning: Malformed block (BEGIN without END)")
            return (None, -1, -1)

        # Include the END marker
        end_idx += len(self.BLOCK_END)

        block = content[begin_idx:end_idx]
        return (block, begin_idx, end_idx)

    def _replace_managed_block(self, content: str, new_block: str) -> str:
        """
        Replace existing managed block with new block.

        Args:
            content: Existing file content.
            new_block: New managed block content.

        Returns:
            Updated content.
        """
        block, start_idx, end_idx = self._extract_managed_block(content)

        if block is None:
            # No block found, append instead
            return self._append_managed_block(content, new_block)

        # Check for multiple blocks (warn but only update first)
        remaining = content[end_idx:]
        if self.BLOCK_BEGIN in remaining:
            print("Warning: Multiple managed blocks found, updating first only")

        return content[:start_idx] + new_block + content[end_idx:]

    def _append_managed_block(self, content: str, new_block: str) -> str:
        """
        Append managed block to content.

        Args:
            content: Existing file content.
            new_block: New managed block content.

        Returns:
            Content with block appended.
        """
        if content and not content.endswith("\n"):
            content += "\n"

        if content:
            content += "\n"

        return content + new_block + "\n"
