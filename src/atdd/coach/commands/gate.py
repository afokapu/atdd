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

import yaml

from atdd.coach.commands.sync import AgentConfigSync
from atdd.coach.utils.repo import detect_worktree_layout


class ATDDGate:
    """ATDD Gate verification."""

    # Key constraints agents must acknowledge
    KEY_CONSTRAINTS = [
        "No ad-hoc tests - follow ATDD conventions",
        "Domain layer NEVER imports from other layers",
        "Phase transitions require quality gates (INIT → PLANNED → RED → GREEN → SMOKE → REFACTOR)",
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
        self.issue_convention = self.package_root / "conventions" / "issue.convention.yaml"

    def _load_agent_rules(self) -> Optional[list]:
        """Load portable agent behavioral rules from .atdd/agent-rules.yaml.

        Returns list of rule dicts, or None if the file does not exist.
        E015: minimize agent-behavioral-rules visible only in per-user memory (#657).
        """
        rules_path = self.target_dir / ".atdd" / "agent-rules.yaml"
        if not rules_path.exists():
            return None
        try:
            data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
            return data.get("rules") if isinstance(data, dict) else None
        except Exception:
            return None

    def _load_issue_convention(self) -> Optional[str]:
        """
        Load the issue convention content.

        Returns:
            File content or None if missing.
        """
        if not self.issue_convention.exists():
            return None
        return self.issue_convention.read_text()

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

        issue_convention = self._load_issue_convention()
        layout = detect_worktree_layout(self.target_dir)

        if json:
            output = {
                "files": files,
                "constraints": self.KEY_CONSTRAINTS,
                "issue_convention": issue_convention,
                "worktree_layout": layout,
                "diagnostic_commands": [
                    "atdd repo validate",
                    "atdd repo broken",
                    "atdd repo orphans",
                    "atdd repo resolve <urn>",
                    "atdd repo rules",
                    "atdd repo wmbt-rules <wmbt-urn>",
                    "atdd rules show <rule-id>",
                    "atdd rules grep <pattern>",
                ],
            }
            if layout == "flat":
                output["worktree_advisory"] = "Run: atdd init --worktree-layout"
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

        if layout == "flat":
            print("\n  Advisory: Repo uses flat layout (not worktree-ready).")
            print("  Run: atdd init --worktree-layout")

        print("\nKey constraints:")
        for i, constraint in enumerate(self.KEY_CONSTRAINTS, 1):
            print(f"  {i}. {constraint}")

        print("\n" + "=" * 60)
        print("Issue Convention")
        print("=" * 60)

        if issue_convention is None:
            print(f"Warning: issue convention not found at {self.issue_convention}")
        else:
            print(issue_convention.rstrip())

        print("\n" + "=" * 60)
        print("Repo Diagnostic Commands")
        print("=" * 60)
        print("  atdd repo validate              # URN traceability (0 errors = clean)")
        print("  atdd repo broken                # grammar violations in plan/ URNs")
        print("  atdd repo orphans               # declared URNs with no parent refs")
        print("  atdd repo resolve <urn>         # trace a single URN to its artifact")
        print("  atdd repo rules                 # repo rules derived from WMBT accs")
        print("  atdd repo wmbt-rules <wmbt-urn> # rules for a specific WMBT")
        print("  atdd rules show <rule-id>       # resolve a rule-ID via bind_rule()")
        print("  atdd rules grep <pattern>       # search rule descriptions and aliases")
        print("\nRun these locally — no network needed. Call before committing to")
        print("catch URN grammar drift and broken references early.")

        # E015: inject portable agent behavioral rules when .atdd/agent-rules.yaml exists (#657).
        agent_rules = self._load_agent_rules()
        if agent_rules:
            print("\n" + "=" * 60)
            print("Agent Behavioral Rules")
            print("=" * 60)
            print("(from .atdd/agent-rules.yaml — enforceable subset, LLM-agnostic)")
            for rule in agent_rules:
                rule_id = rule.get("id", "?")
                rule_text = rule.get("rule", "")
                classification = rule.get("classification", "")
                print(f"  [{rule_id}] ({classification}) {rule_text}")

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
