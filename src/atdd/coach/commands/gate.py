"""
ATDD Gate verification command.

Ensures agents have loaded and confirmed ATDD rules before starting work.
Outputs the expected hash and key constraints for verification.

Usage:
    atdd gate                    # Show gate verification info
    atdd gate --json             # Output as JSON for programmatic use
"""
import hashlib
import json as json_module
from pathlib import Path
from typing import Dict, List, Optional

from atdd.coach.commands.sync import AgentConfigSync


class ATDDGate:
    """ATDD Gate verification."""

    # Key constraints agents must acknowledge
    KEY_CONSTRAINTS = [
        "No ad-hoc tests - follow ATDD conventions",
        "Domain layer NEVER imports from other layers",
        "Phase transitions require quality gates (INIT → PLANNED → RED → GREEN → REFACTOR)",
    ]

    def __init__(self, target_dir: Optional[Path] = None):
        """
        Initialize the ATDDGate.

        Args:
            target_dir: Target directory containing agent config files.
        """
        self.target_dir = target_dir or Path.cwd()
        self.syncer = AgentConfigSync(self.target_dir)
        self.package_root = Path(__file__).parent.parent  # src/atdd/coach
        self.session_convention = self.package_root / "conventions" / "session.convention.yaml"

    def _load_session_convention(self) -> Optional[str]:
        """
        Load the session convention content.

        Returns:
            File content or None if missing.
        """
        if not self.session_convention.exists():
            return None
        return self.session_convention.read_text()

    def _compute_block_hash(self, content: str) -> Optional[str]:
        """
        Compute SHA256 hash of the managed block in content.

        Args:
            content: File content.

        Returns:
            SHA256 hash or None if no managed block found.
        """
        block, _, _ = self.syncer._extract_managed_block(content)
        if block is None:
            return None

        return hashlib.sha256(block.encode()).hexdigest()

    def _get_synced_files(self) -> Dict[str, Dict]:
        """
        Get info about synced agent config files.

        Returns:
            Dict mapping agent name to file info.
        """
        agents = self.syncer._get_enabled_agents()
        result = {}

        for agent in agents:
            target_file = self.syncer.AGENT_FILES.get(agent)
            if not target_file:
                continue

            target_path = self.target_dir / target_file
            if not target_path.exists():
                result[agent] = {
                    "file": target_file,
                    "exists": False,
                    "hash": None,
                }
                continue

            content = target_path.read_text()
            block_hash = self._compute_block_hash(content)

            result[agent] = {
                "file": target_file,
                "exists": True,
                "has_block": block_hash is not None,
                "hash": block_hash[:16] if block_hash else None,  # Short hash for display
                "hash_full": block_hash,
            }

        return result

    def verify(self, json: bool = False) -> int:
        """
        Output gate verification info.

        Args:
            json: If True, output as JSON.

        Returns:
            0 on success, 1 if no synced files found.
        """
        files = self._get_synced_files()

        if not files:
            print("No agent config files configured.")
            print("Run 'atdd init' to set up ATDD in this repo.")
            return 1

        session_convention = self._load_session_convention()

        if json:
            output = {
                "files": files,
                "constraints": self.KEY_CONSTRAINTS,
                "session_convention": session_convention,
            }
            print(json_module.dumps(output, indent=2))
            return 0

        # Human-readable output
        print("=" * 60)
        print("ATDD Gate Verification")
        print("=" * 60)

        print("\nLoaded files:")
        for agent, info in files.items():
            if info["exists"] and info.get("has_block"):
                print(f"  - {info['file']} (hash: {info['hash']}...)")
            elif info["exists"]:
                print(f"  - {info['file']} (no managed block)")
            else:
                print(f"  - {info['file']} (missing)")

        print("\nKey constraints:")
        for i, constraint in enumerate(self.KEY_CONSTRAINTS, 1):
            print(f"  {i}. {constraint}")

        print("\n" + "=" * 60)
        print("Session Convention")
        print("=" * 60)

        if session_convention is None:
            print(f"Warning: session convention not found at {self.session_convention}")
        else:
            print(session_convention.rstrip())

        print("\n" + "-" * 60)
        print("Before starting work, confirm you have loaded these rules.")
        print("-" * 60)

        return 0

    def get_confirmation_template(self) -> str:
        """
        Get a template agents can use to confirm gate compliance.

        Returns:
            Markdown template for gate confirmation.
        """
        files = self._get_synced_files()

        lines = [
            "## ATDD Gate Confirmation",
            "",
            "**Files loaded:**",
        ]

        for agent, info in files.items():
            if info["exists"] and info.get("has_block"):
                lines.append(f"- {info['file']} (hash: `{info['hash']}...`)")

        lines.extend([
            "",
            "**Key constraints acknowledged:**",
        ])

        for constraint in self.KEY_CONSTRAINTS:
            lines.append(f"- {constraint}")

        return "\n".join(lines)
