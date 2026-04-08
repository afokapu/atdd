#!/usr/bin/env python3
"""
ATDD Platform - Unified command-line interface.

The coach orchestrates all ATDD lifecycle operations:
- validate: Run validators (planner/tester/coder/coach)
- inventory: Catalog repository artifacts
- status: Show platform status
- registry: Update registries from source files
- init: Initialize ATDD structure in consumer repos
- issue: Unified issue lifecycle (create, enter, transition, close-wmbt)
- list/branch/pr: Issue shortcuts
- sync: Sync ATDD rules to agent config files
- gate: Verify agents loaded ATDD rules

Usage:
    atdd init                                # Initialize ATDD in consumer repo
    atdd issue my-feature                    # Create new issue + WMBT sub-issues
    atdd issue 11                            # Enter issue #11 (state-driven)
    atdd issue 11 --status RED               # Transition issue status
    atdd issue 11 --close-wmbt D005          # Close WMBT sub-issue
    atdd issue open                          # List open issues
    atdd list                                # List all issues
    atdd sync                                # Sync ATDD rules to agent configs
    atdd sync --verify                       # Check if files are in sync
    atdd sync --agent claude                 # Sync specific agent only
    atdd gate                                # Show ATDD gate verification
    atdd validate                            # Run all validators
    atdd validate planner                    # Run planner validators
    atdd validate tester                     # Run tester validators
    atdd validate coder                      # Run coder validators
    atdd validate --quick                    # Quick smoke test
    atdd validate --coverage                 # With coverage report
    atdd inventory                           # Generate inventory (YAML)
    atdd inventory --format json             # Generate inventory (JSON)
    atdd status                              # Show platform status
    atdd registry update                     # Update all registries
    atdd --help                              # Show help
"""

import argparse
import sys
import warnings
from pathlib import Path

ATDD_DIR = Path(__file__).parent

from atdd.coach.commands.inventory import RepositoryInventory
from atdd.coach.commands.test_runner import TestRunner
from atdd.coach.commands.registry import RegistryUpdater
from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.commands.issue import IssueManager
from atdd.coach.commands.sync import AgentConfigSync
from atdd.coach.commands.gate import ATDDGate
from atdd.coach.commands.urn import URNCommand
from atdd.coach.commands.upgrader import Upgrader
from atdd.coach.utils.repo import find_repo_root
from atdd.version_check import print_update_notice, print_upgrade_sync_notice


def _deprecation_warning(old: str, new: str) -> None:
    """Emit a deprecation warning for legacy flags."""
    print(f"\033[33m⚠️  Deprecated: '{old}' will be removed. Use '{new}' instead.\033[0m")


class ATDDCoach:
    """
    ATDD Platform Coach - orchestrates all operations.

    The coach role coordinates across the three ATDD phases:
    - Planner: Planning phase validation
    - Tester: Testing phase validation (contracts-as-code)
    - Coder: Implementation phase validation
    """

    def __init__(self, repo_root: Path = None):
        self.repo_root = repo_root or find_repo_root()
        self.inventory = RepositoryInventory(self.repo_root)
        self.validator_runner = TestRunner(self.repo_root)
        self.registry_updater = RegistryUpdater(self.repo_root)

    def run_inventory(self, format: str = "yaml") -> int:
        """Generate repository inventory."""
        print("📊 Generating repository inventory...")
        data = self.inventory.generate()

        if format == "json":
            import json
            print(json.dumps(data, indent=2))
        else:
            import yaml
            print("\n" + "=" * 60)
            print("Repository Inventory")
            print("=" * 60 + "\n")
            print(yaml.dump(data, default_flow_style=False, sort_keys=False))

        return 0

    def run_validators(
        self,
        phase: str = "all",
        verbose: bool = False,
        coverage: bool = False,
        html: bool = False,
        quick: bool = False,
        split: bool = True,
        local: bool = False,
        skip_api: bool = False,
    ) -> int:
        """Run ATDD validators."""
        if quick:
            return self.validator_runner.quick_check()

        markers = ["not github_api"] if skip_api else None

        return self.validator_runner.run_tests(
            phase=phase,
            verbose=verbose,
            coverage=coverage,
            html_report=html,
            parallel=True,
            split=split,
            local=local,
            markers=markers,
        )

    def update_registries(
        self,
        registry_type: str = "all",
        apply: bool = False,
        check: bool = False
    ) -> int:
        """Update registries from source files.

        Args:
            registry_type: Which registry to update (all, wagons, trains, contracts, etc.)
            apply: If True, apply changes without prompting (CI mode)
            check: If True, only check for drift without applying (exit 1 if drift)

        Returns:
            0 on success, 1 if --check and drift detected
        """
        # Convert flags to mode string
        if check:
            mode = "check"
        elif apply:
            mode = "apply"
        else:
            mode = "interactive"

        # Registry type handlers
        handlers = {
            "wagons": self.registry_updater.update_wagon_registry,
            "trains": self.registry_updater.build_trains,
            "contracts": self.registry_updater.update_contract_registry,
            "telemetry": self.registry_updater.update_telemetry_registry,
            "tester": self.registry_updater.build_tester,
            "coder": self.registry_updater.build_coder,
            "supabase": self.registry_updater.build_supabase,
        }

        if registry_type == "all":
            result = self.registry_updater.build_all(mode=mode)
            # In check mode, return 1 if any registry has changes
            if check:
                has_changes = any(
                    r.get("has_changes", False) or r.get("new", 0) > 0 or len(r.get("changes", [])) > 0
                    for r in result.values()
                )
                return 1 if has_changes else 0
        elif registry_type in handlers:
            result = handlers[registry_type](mode=mode)
            # In check mode, return 1 if this registry has changes
            if check:
                has_changes = result.get("has_changes", False) or result.get("new", 0) > 0 or len(result.get("changes", [])) > 0
                return 1 if has_changes else 0
        else:
            print(f"Unknown registry type: {registry_type}")
            return 1

        return 0

    def show_status(self) -> int:
        """Show quick status summary."""
        print("=" * 60)
        print("ATDD Platform Status")
        print("=" * 60)
        print("\nDirectory structure:")
        print(f"  📋 Planner validators: {ATDD_DIR / 'planner' / 'validators'}")
        print(f"  🧪 Tester validators:  {ATDD_DIR / 'tester' / 'validators'}")
        print(f"  ⚙️  Coder validators:   {ATDD_DIR / 'coder' / 'validators'}")
        print(f"  🎯 Coach validators:   {ATDD_DIR / 'coach' / 'validators'}")

        # Quick stats
        planner_validators = len(list((ATDD_DIR / "planner" / "validators").glob("test_*.py")))
        tester_validators = len(list((ATDD_DIR / "tester" / "validators").glob("test_*.py")))
        coder_validators = len(list((ATDD_DIR / "coder" / "validators").glob("test_*.py")))
        coach_validators = len(list((ATDD_DIR / "coach" / "validators").glob("test_*.py")))

        print(f"\nValidator files:")
        print(f"  Planner: {planner_validators} files")
        print(f"  Tester:  {tester_validators} files")
        print(f"  Coder:   {coder_validators} files")
        print(f"  Coach:   {coach_validators} files")
        print(f"  Total:   {planner_validators + tester_validators + coder_validators + coach_validators} files")

        return 0


def main():
    """Main CLI entry point."""
    from importlib.metadata import version as pkg_version

    atdd_version = pkg_version("atdd")

    parser = argparse.ArgumentParser(
        description="ATDD Platform - Coach orchestrates all ATDD operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize ATDD in consumer repo
  %(prog)s init                           Bootstrap GitHub infra + .atdd/ config
  %(prog)s init --force                   Overwrite existing config

  # Run validators
  %(prog)s validate                       Run all validators
  %(prog)s validate planner               Run planner validators only
  %(prog)s validate tester                Run tester validators only
  %(prog)s validate coder                 Run coder validators only
  %(prog)s validate --quick               Quick smoke test
  %(prog)s validate --coverage            With coverage report
  %(prog)s validate --html                With HTML report
  %(prog)s validate -v                    Verbose output

  # Repository inspection
  %(prog)s inventory                      Generate full inventory (YAML)
  %(prog)s inventory --format json        Generate inventory (JSON)
  %(prog)s status                         Show platform status

  # Registry management
  %(prog)s registry update                Update all registries
  %(prog)s registry update wagons         Update wagon registry only
  %(prog)s registry update contracts      Update contract registry only
  %(prog)s registry update telemetry      Update telemetry registry only

  # Issue lifecycle (unified command)
  %(prog)s issue my-feature               Create issue + WMBT sub-issues
  %(prog)s issue 11                       Enter issue #11 (state-driven)
  %(prog)s issue 11 --status RED          Transition issue status
  %(prog)s issue 11 --close-wmbt D005     Close WMBT sub-issue
  %(prog)s issue open                     List open issues
  %(prog)s list                           List all issues
  %(prog)s branch 69                      Create worktree from issue #69
  %(prog)s branch 69 --prefix fix         Override branch prefix

  # Create PR from issue
  %(prog)s pr 69                          Create PR for issue #69
  %(prog)s pr 69 --draft                  Create as draft PR
  %(prog)s pr 69 --base develop           Override base branch

  # Agent config sync
  %(prog)s sync                           Sync ATDD rules to agent configs
  %(prog)s sync --verify                  Check if files are in sync (CI)
  %(prog)s sync --agent claude            Sync specific agent only
  %(prog)s sync --status                  Show sync status

  # ATDD gate verification
  %(prog)s gate                           Show gate verification info
  %(prog)s gate --json                    Output as JSON

Phase descriptions:
  planner - Validates planning artifacts (wagons, trains, URNs)
  tester  - Validates testing artifacts (contracts, telemetry)
  coder   - Validates implementation (architecture, quality)
  coach   - Validates coach artifacts (issues, registries)
        """
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"atdd {atdd_version}",
    )

    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ----- atdd version -----
    subparsers.add_parser(
        "version",
        help="Print installed version and exit",
    )

    # ----- atdd validate [phase] -----
    validate_parser = subparsers.add_parser(
        "validate",
        help="Run ATDD validators",
        description="Run validators to check artifacts against conventions"
    )
    validate_parser.add_argument(
        "phase",
        nargs="?",
        type=str,
        default="all",
        choices=["all", "planner", "tester", "coder", "coach"],
        help="Phase to validate (default: all)"
    )
    validate_parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick smoke test (no parallel, no reports)"
    )
    validate_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    validate_parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )
    validate_parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report"
    )
    validate_parser.add_argument(
        "--no-split",
        action="store_true",
        dest="no_split",
        help="Run all tests in one pass (default: two-stage split)"
    )
    validate_parser.add_argument(
        "--local",
        action="store_true",
        help="Run validators locally (default: GH Actions only)"
    )
    validate_parser.add_argument(
        "--skip-api",
        action="store_true",
        dest="skip_api",
        help="Skip github_api tests (for offline development)"
    )
    validate_parser.add_argument(
        "--verify-baseline",
        action="store_true",
        dest="verify_baseline",
        help="Verify validation baseline freshness (<10s, no test execution)"
    )

    # ----- atdd inventory -----
    inventory_parser = subparsers.add_parser(
        "inventory",
        help="Generate repository inventory",
        description="Catalog all ATDD artifacts in the repository"
    )
    inventory_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["yaml", "json"],
        default="yaml",
        help="Output format (default: yaml)"
    )
    inventory_parser.add_argument(
        "--trace",
        action="store_true",
        help="Print URN traceability matrix with coverage and orphan detection"
    )

    # ----- atdd status -----
    subparsers.add_parser(
        "status",
        help="Show platform status",
        description="Display ATDD platform status and validator counts"
    )

    # ----- atdd registry {update} -----
    registry_parser = subparsers.add_parser(
        "registry",
        help="Manage registries",
        description="Update registries from source files"
    )
    registry_subparsers = registry_parser.add_subparsers(
        dest="registry_command",
        help="Registry commands"
    )

    # atdd registry update [type]
    registry_update_parser = registry_subparsers.add_parser(
        "update",
        help="Update registries from source files"
    )
    registry_update_parser.add_argument(
        "type",
        nargs="?",
        type=str,
        default="all",
        choices=["all", "wagons", "trains", "contracts", "telemetry", "tester", "coder", "supabase"],
        help="Registry type to update (default: all)"
    )
    registry_update_parser.add_argument(
        "--yes", "--apply",
        action="store_true",
        dest="apply",
        help="Apply changes without prompting (for CI/automation)"
    )
    registry_update_parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift without applying (exit 1 if changes detected)"
    )

    # ----- atdd init -----
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize ATDD structure in consumer repo",
        description="Bootstrap GitHub infrastructure (labels, Project v2, fields) and .atdd/ config"
    )
    init_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing files"
    )
    init_parser.add_argument(
        "--worktree-layout",
        action="store_true",
        help="Migrate repo to flat-sibling worktree layout (moves contents into main/)"
    )
    init_parser.add_argument(
        "--export-schemas",
        action="store_true",
        dest="export_schemas",
        help="Export convention YAML and schema JSON files to .atdd/schemas/"
    )

    # ----- atdd schemas --check -----
    schemas_parser = subparsers.add_parser(
        "schemas",
        help="Manage exported convention/schema files",
        description="Check or refresh exported convention and schema files in .atdd/schemas/"
    )
    schemas_parser.add_argument(
        "--check",
        action="store_true",
        help="Compare .atdd/schemas/.version against installed atdd version"
    )

    # ----- atdd new <slug> -----
    new_parser = subparsers.add_parser(
        "new",
        help="[DEPRECATED] Use 'atdd issue <slug>' instead",
        description="DEPRECATED: Use 'atdd issue <slug>' instead.\n\nCreate a new GitHub Issue with Project v2 fields and WMBT sub-issues"
    )
    new_parser.add_argument(
        "slug",
        type=str,
        help="Issue name (kebab-case)"
    )
    new_parser.add_argument(
        "--type", "-t",
        type=str,
        default="implementation",
        choices=["implementation", "migration", "refactor", "analysis", "planning", "cleanup", "tracking"],
        help="Issue type (default: implementation)"
    )
    new_parser.add_argument(
        "--train",
        type=str,
        help="Train ID to assign (e.g., 0001-auth-session-standard)"
    )
    new_parser.add_argument(
        "--archetypes", "-a",
        type=str,
        help="Comma-separated archetypes (e.g., be,contracts,wmbt)"
    )

    # NOTE: 'session' subcommand removed in E009; replaced by top-level issue commands.

    # ----- atdd list -----
    subparsers.add_parser(
        "list",
        help="List all ATDD issues"
    )

    # ----- atdd archive <issue_number> -----
    archive_top_parser = subparsers.add_parser(
        "archive",
        help="[DEPRECATED] Use 'atdd issue <N> --status COMPLETE' instead"
    )
    archive_top_parser.add_argument("session_id", type=str, help="Issue number to archive")

    # ----- atdd update <issue_number> -----
    update_top_parser = subparsers.add_parser(
        "update",
        help="[DEPRECATED] Use 'atdd issue <N> --status <S>' instead"
    )
    update_top_parser.add_argument("session_id", type=str, help="Issue number")
    update_top_parser.add_argument("--status", "-s", type=str, help="ATDD Status (INIT/PLANNED/RED/GREEN/SMOKE/REFACTOR/COMPLETE/BLOCKED)")
    update_top_parser.add_argument("--phase", "-p", type=str, help="ATDD Phase (Planner/Tester/Coder)")
    update_top_parser.add_argument("--branch", "-b", type=str, help="ATDD Branch name")
    update_top_parser.add_argument("--train", type=str, help="ATDD Train URN")
    update_top_parser.add_argument("--feature-urn", type=str, help="ATDD Feature URN")
    update_top_parser.add_argument("--archetypes", type=str, help="ATDD Archetypes (comma-separated)")
    update_top_parser.add_argument("--complexity", type=str, help="ATDD Complexity (e.g., 4-High)")
    update_top_parser.add_argument("--force", "-f", action="store_true", help="Bypass gate/body checks on COMPLETE (train still enforced)")

    # ----- atdd branch <issue_number> -----
    branch_parser = subparsers.add_parser(
        "branch",
        help="Create worktree branch from issue metadata",
        description="Create a git worktree with the correct prefix/slug naming derived from issue metadata"
    )
    branch_parser.add_argument("issue_number", type=int, help="Issue number")
    branch_parser.add_argument(
        "--prefix",
        type=str,
        help="Override branch prefix (feat, fix, refactor, chore, docs, devops)"
    )

    # ----- atdd pr <issue_number> -----
    pr_parser = subparsers.add_parser(
        "pr",
        help="Create PR linked to an ATDD issue",
        description=(
            "Create a GitHub pull request with closing keywords for automatic issue closure.\n\n"
            "  atdd pr 69                Create PR for issue #69\n"
            "  atdd pr 69 --draft        Create as draft PR\n"
            "  atdd pr 69 --base develop Override base branch\n"
            "  atdd pr 69 --auto         Create PR and enable auto-merge\n"
            "  atdd pr 69 --auto --merge-strategy rebase\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pr_parser.add_argument("issue_number", type=int, help="Issue number to link")
    pr_parser.add_argument(
        "--draft",
        action="store_true",
        help="Create as a draft PR"
    )
    pr_parser.add_argument(
        "--base",
        type=str,
        default="main",
        help="Base branch for the PR (default: main)"
    )
    pr_parser.add_argument(
        "--auto",
        action="store_true",
        help="Enable auto-merge after PR creation (requires repo setting)"
    )
    pr_parser.add_argument(
        "--merge-strategy",
        type=str,
        choices=["squash", "merge", "rebase"],
        default="squash",
        help="Merge strategy for auto-merge (default: squash)"
    )

    # ----- atdd close-wmbt <issue_number> <wmbt_id> -----
    close_wmbt_top_parser = subparsers.add_parser(
        "close-wmbt",
        help="[DEPRECATED] Use 'atdd issue <N> --close-wmbt <ID>' instead"
    )
    close_wmbt_top_parser.add_argument("session_id", type=str, help="Parent issue number")
    close_wmbt_top_parser.add_argument("wmbt_id", type=str, help="WMBT ID (e.g., D001, E003)")
    close_wmbt_top_parser.add_argument("--force", "-f", action="store_true", help="Close even if ATDD cycle checkboxes are unchecked")

    # ----- atdd issue <target> -----
    issue_parser = subparsers.add_parser(
        "issue",
        help="Unified issue lifecycle command",
        description=(
            "Enter an existing issue (by number) or create a new one (by slug).\n\n"
            "  atdd issue 126              Enter issue #126 (state-driven)\n"
            "  atdd issue my-feature       Create new issue and enter at INIT\n"
            "  atdd issue 126 --status RED Transition status\n"
            "  atdd issue open             List open issues\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    issue_parser.add_argument(
        "target",
        type=str,
        nargs="?",
        help="Issue number (integer) to enter, slug (string) to create, or 'open' to list"
    )
    issue_parser.add_argument(
        "--status", "-s",
        type=str,
        help="Transition issue to this status"
    )
    issue_parser.add_argument(
        "--close-wmbt",
        type=str,
        dest="close_wmbt",
        help="Close a WMBT sub-issue by ID"
    )
    issue_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Bypass gate/body checks (train still enforced)"
    )
    issue_parser.add_argument(
        "--label", "-l",
        type=str,
        help="Filter by label (for 'open' target)"
    )
    issue_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=30,
        help="Maximum issues to list (for 'open' target, default: 30)"
    )
    issue_parser.add_argument(
        "--assignee",
        type=str,
        help="Filter by assignee (for 'open' target)"
    )
    issue_parser.add_argument(
        "--type", "-t",
        type=str,
        default="implementation",
        choices=["implementation", "migration", "refactor", "analysis", "planning", "cleanup", "tracking"],
        help="Issue type for creation (default: implementation)"
    )
    issue_parser.add_argument(
        "--train",
        type=str,
        help="Train ID to assign on creation"
    )
    issue_parser.add_argument(
        "--archetypes", "-a",
        type=str,
        help="Comma-separated archetypes on creation (e.g., be,contracts,wmbt)"
    )

    # ----- atdd color [value] -----
    color_parser = subparsers.add_parser(
        "color",
        help="Set workspace title/status bar color",
        description="Set workspace color via named preset or hex value",
    )
    color_parser.add_argument(
        "value",
        nargs="?",
        type=str,
        default=None,
        help="Color preset name (yellow, blue, green, red, orange, purple) or hex (#RRGGBB)",
    )

    # ----- atdd sync -----
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync ATDD rules to agent config files",
        description="Sync managed ATDD blocks to agent config files (CLAUDE.md, AGENTS.md, etc.)"
    )
    sync_parser.add_argument(
        "--verify",
        action="store_true",
        help="Check if files are in sync (for CI)"
    )
    sync_parser.add_argument(
        "--agent",
        type=str,
        choices=["claude", "codex", "gemini", "qwen"],
        help="Sync specific agent only"
    )
    sync_parser.add_argument(
        "--status",
        action="store_true",
        help="Show sync status for all agents"
    )

    # ----- atdd gate -----
    gate_parser = subparsers.add_parser(
        "gate",
        help="Show ATDD gate verification info",
        description="Verify agents have loaded ATDD rules before starting work"
    )
    gate_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON for programmatic use"
    )

    # ----- atdd upgrade -----
    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Show what changed and run sync + init --force",
        description="Upgrade ATDD infrastructure after pip install --upgrade atdd"
    )
    upgrade_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts"
    )

    # ----- atdd baseline {update,show} -----
    baseline_parser = subparsers.add_parser(
        "baseline",
        help="Manage ratchet baselines for coder validators",
        description="View and update violation count baselines (.atdd/baselines/coder.yaml)"
    )
    baseline_subparsers = baseline_parser.add_subparsers(
        dest="baseline_command",
        help="Baseline commands"
    )

    # atdd baseline update
    baseline_update_parser = baseline_subparsers.add_parser(
        "update",
        help="Run validators and write current violation counts to baseline file"
    )
    baseline_update_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would be written without modifying the baseline file"
    )
    baseline_update_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show per-validator violation details"
    )

    # atdd baseline show
    baseline_show_parser = baseline_subparsers.add_parser(
        "show",
        help="Display baseline vs current violation counts"
    )
    baseline_show_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Include per-validator detail"
    )

    # ----- atdd urn {graph,orphans,broken,validate,resolve,declarations,viz} -----
    urn_parser = subparsers.add_parser(
        "urn",
        help="URN traceability analysis",
        description="Analyze URN coverage, traceability, and resolution"
    )
    urn_subparsers = urn_parser.add_subparsers(
        dest="urn_command",
        help="URN commands"
    )

    # atdd urn graph
    urn_graph_parser = urn_subparsers.add_parser(
        "graph",
        help="Generate URN traceability graph"
    )
    urn_graph_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["json", "dot"],
        default="json",
        help="Output format (default: json)"
    )
    urn_graph_parser.add_argument(
        "--root",
        type=str,
        help="Root URN for subgraph extraction"
    )
    urn_graph_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_graph_parser.add_argument(
        "--depth",
        type=int,
        default=-1,
        help="Maximum depth for subgraph (-1 for unlimited)"
    )
    urn_graph_parser.add_argument(
        "--full",
        action="store_true",
        help="Output full raw nodes + edges (default: agent-optimized summary)"
    )

    # atdd urn orphans
    urn_orphans_parser = urn_subparsers.add_parser(
        "orphans",
        help="Find orphaned URNs (declared but not referenced)"
    )
    urn_orphans_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_orphans_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd urn broken
    urn_broken_parser = urn_subparsers.add_parser(
        "broken",
        help="Find broken URN references"
    )
    urn_broken_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_broken_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd urn validate
    urn_validate_parser = urn_subparsers.add_parser(
        "validate",
        help="Validate URN traceability"
    )
    urn_validate_parser.add_argument(
        "--phase",
        type=str,
        choices=["warn", "fail"],
        default="warn",
        help="Validation phase: warn (errors as warnings) or fail (strict)"
    )
    urn_validate_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_validate_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    urn_validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings too"
    )
    urn_validate_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix urn:jel:* contract IDs by deriving from file path"
    )
    urn_validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what --fix would change without modifying files"
    )

    # atdd urn resolve
    urn_resolve_parser = urn_subparsers.add_parser(
        "resolve",
        help="Resolve a URN to its artifact(s)"
    )
    urn_resolve_parser.add_argument(
        "urn",
        type=str,
        help="The URN to resolve"
    )
    urn_resolve_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd urn declarations
    urn_declarations_parser = urn_subparsers.add_parser(
        "declarations",
        help="List all URN declarations"
    )
    urn_declarations_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_declarations_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd urn families
    urn_subparsers.add_parser(
        "families",
        help="List registered URN families"
    )

    # atdd urn viz
    urn_viz_parser = urn_subparsers.add_parser(
        "viz",
        help="Launch interactive URN graph visualizer (requires atdd[viz])"
    )
    urn_viz_parser.add_argument(
        "--port",
        type=int,
        default=8502,
        help="Streamlit server port (default: 8502)"
    )
    urn_viz_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Streamlit server address (default: 127.0.0.1)"
    )
    urn_viz_parser.add_argument(
        "--root",
        type=str,
        help="Root URN for subgraph extraction"
    )
    urn_viz_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    urn_viz_parser.add_argument(
        "--depth",
        type=int,
        default=-1,
        help="Maximum depth for subgraph (-1 for unlimited)"
    )

    # ----- Legacy flag-based arguments (deprecated, kept for backwards compatibility) -----

    # Repository root override (not deprecated - still useful)
    parser.add_argument(
        "--repo",
        type=str,
        metavar="PATH",
        help="Target repository root (default: auto-detect from .atdd/)"
    )

    # DEPRECATED: --test → atdd validate
    parser.add_argument(
        "--test",
        type=str,
        choices=["all", "planner", "tester", "coder"],
        metavar="PHASE",
        help=argparse.SUPPRESS  # Hide from help, deprecated
    )

    # DEPRECATED: --inventory → atdd inventory
    parser.add_argument(
        "--inventory",
        action="store_true",
        help=argparse.SUPPRESS  # Hide from help, deprecated
    )

    # DEPRECATED: --status → atdd status
    parser.add_argument(
        "--status",
        action="store_true",
        help=argparse.SUPPRESS  # Hide from help, deprecated
    )

    # DEPRECATED: --quick → atdd validate --quick
    parser.add_argument(
        "--quick",
        action="store_true",
        help=argparse.SUPPRESS  # Hide from help, deprecated
    )

    # DEPRECATED: --update-registry → atdd registry update
    parser.add_argument(
        "--update-registry",
        type=str,
        choices=["all", "wagons", "contracts", "telemetry"],
        metavar="TYPE",
        help=argparse.SUPPRESS  # Hide from help, deprecated
    )

    # Options that work with both legacy and modern commands
    parser.add_argument(
        "--format",
        type=str,
        choices=["yaml", "json"],
        default="yaml",
        help=argparse.SUPPRESS  # Hide, use subcommand option instead
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help=argparse.SUPPRESS  # Hide, use subcommand option instead
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help=argparse.SUPPRESS  # Hide, use subcommand option instead
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help=argparse.SUPPRESS  # Hide, use subcommand option instead
    )

    args = parser.parse_args()

    # ----- Handle modern subcommands -----

    # atdd version
    if args.command == "version":
        print(f"atdd {atdd_version}")
        return 0

    # atdd validate [phase]
    elif args.command == "validate":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None

        # --verify-baseline: fast path, no test execution
        if getattr(args, 'verify_baseline', False):
            from atdd.coach.commands.validation_baseline import (
                verify_validation_baseline,
            )
            return verify_validation_baseline(
                phase=args.phase,
                repo_root=repo_path,
            )

        coach = ATDDCoach(repo_root=repo_path)
        skip_api = getattr(args, 'skip_api', False)
        rc = coach.run_validators(
            phase=args.phase,
            verbose=args.verbose,
            coverage=args.coverage,
            html=args.html,
            quick=args.quick,
            split=not args.no_split and not skip_api,
            local=args.local,
            skip_api=skip_api,
        )

        # Write baseline on success
        if rc == 0:
            from atdd.coach.commands.validation_baseline import (
                write_validation_baseline,
            )
            write_validation_baseline(
                phase=args.phase,
                skipped_api=skip_api,
                repo_root=repo_path,
            )

        return rc

    # atdd inventory
    elif args.command == "inventory":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        if getattr(args, 'trace', False):
            from atdd.coach.commands.inventory import TraceabilityReport
            report = TraceabilityReport(repo_root=repo_path)
            return report.generate()
        coach = ATDDCoach(repo_root=repo_path)
        return coach.run_inventory(format=args.format)

    # atdd status
    elif args.command == "status":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        coach = ATDDCoach(repo_root=repo_path)
        return coach.show_status()

    # atdd registry {update}
    elif args.command == "registry":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        coach = ATDDCoach(repo_root=repo_path)

        if args.registry_command == "update":
            return coach.update_registries(
                registry_type=args.type,
                apply=args.apply,
                check=args.check
            )
        else:
            registry_parser.print_help()
            return 0

    # atdd init
    elif args.command == "init":
        initializer = ProjectInitializer()
        if args.export_schemas:
            return initializer.export_schemas()
        return initializer.init(force=args.force, worktree_layout=args.worktree_layout)

    # atdd new <slug> — DEPRECATED, delegates to atdd issue <slug>
    elif args.command == "new":
        _deprecation_warning("atdd new <slug>", "atdd issue <slug>")
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()
        return lifecycle.create(
            slug=args.slug,
            issue_type=getattr(args, 'type', 'implementation'),
            train=getattr(args, 'train', None),
            archetypes=getattr(args, 'archetypes', None),
        )

    # atdd list (top-level shorthand)
    elif args.command == "list":
        manager = IssueManager()
        return manager.list()

    # atdd archive <issue_id> — DEPRECATED, delegates to atdd issue <N> --status COMPLETE
    elif args.command == "archive":
        _deprecation_warning("atdd archive <N>", "atdd issue <N> --status COMPLETE")
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()
        issue_number = int(args.session_id)
        return lifecycle.transition(issue_number, "COMPLETE", force=False)

    # atdd update <issue_id> — DEPRECATED, delegates to atdd issue <N> --status <S>
    elif args.command == "update":
        status = getattr(args, 'status', None)
        if status:
            _deprecation_warning("atdd update <N> --status <S>", "atdd issue <N> --status <S>")
            from atdd.coach.commands.issue_lifecycle import IssueLifecycle
            lifecycle = IssueLifecycle()
            issue_number = int(args.session_id)
            return lifecycle.transition(
                issue_number, status,
                force=getattr(args, 'force', False),
            )
        # Non-status field updates have no atdd issue equivalent yet — pass through
        _deprecation_warning("atdd update", "atdd issue")
        manager = IssueManager()
        return manager.update(
            issue_id=args.session_id,
            status=args.status, phase=args.phase,
            branch=args.branch, train=getattr(args, 'train', None),
            feature_urn=getattr(args, 'feature_urn', None),
            archetypes=getattr(args, 'archetypes', None),
            complexity=getattr(args, 'complexity', None),
            force=getattr(args, 'force', False),
        )

    # atdd branch <issue_number>
    elif args.command == "branch":
        from atdd.coach.commands.branch import BranchManager
        manager = BranchManager()
        return manager.branch(
            issue_number=args.issue_number,
            prefix=getattr(args, 'prefix', None),
        )

    # atdd pr <issue_number>
    elif args.command == "pr":
        from atdd.coach.commands.pr import PRManager
        manager = PRManager()
        return manager.pr(
            issue_number=args.issue_number,
            draft=getattr(args, 'draft', False),
            base=getattr(args, 'base', 'main'),
            auto_merge=getattr(args, 'auto', False),
            merge_strategy=getattr(args, 'merge_strategy', 'squash'),
        )

    # atdd close-wmbt <issue_id> <wmbt_id> — DEPRECATED, delegates to atdd issue <N> --close-wmbt <ID>
    elif args.command == "close-wmbt":
        _deprecation_warning("atdd close-wmbt <N> <ID>", "atdd issue <N> --close-wmbt <ID>")
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()
        issue_number = int(args.session_id)
        return lifecycle.close_wmbt(
            issue_number,
            args.wmbt_id,
            force=args.force,
        )

    # atdd issue <target>
    elif args.command == "issue":
        target = getattr(args, 'target', None)
        if not target:
            issue_parser.print_help()
            return 0

        # atdd issue open — list open issues
        if target == "open":
            manager = IssueManager()
            return manager.open_issues(
                label=getattr(args, 'label', None),
                limit=getattr(args, 'limit', 30),
                assignee=getattr(args, 'assignee', None),
            )

        # Detect mode: integer → enter, string → create (future)
        try:
            issue_number = int(target)
        except ValueError:
            # Slug mode — create new issue and enter at INIT
            from atdd.coach.commands.issue_lifecycle import IssueLifecycle
            lifecycle = IssueLifecycle()
            return lifecycle.create(
                slug=target,
                issue_type=getattr(args, 'type', 'implementation'),
                train=getattr(args, 'train', None),
                archetypes=getattr(args, 'archetypes', None),
            )

        # Mutations or enter
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()

        if getattr(args, 'status', None):
            return lifecycle.transition(
                issue_number,
                args.status,
                force=getattr(args, 'force', False),
            )

        if getattr(args, 'close_wmbt', None):
            return lifecycle.close_wmbt(
                issue_number,
                args.close_wmbt,
                force=getattr(args, 'force', False),
            )

        # Default: enter existing issue
        return lifecycle.enter(issue_number)

    # atdd color [value]
    elif args.command == "color":
        from atdd.coach.commands.color import ColorManager
        manager = ColorManager()
        return manager.color(value=args.value)

    # atdd schemas
    elif args.command == "schemas":
        if args.check:
            return ProjectInitializer.check_schema_version()
        # Default: export (same as atdd init --export-schemas)
        initializer = ProjectInitializer()
        return initializer.export_schemas()

    # atdd sync
    elif args.command == "sync":
        syncer = AgentConfigSync()
        if args.status:
            return syncer.status()
        if args.verify:
            return syncer.verify()
        return syncer.sync(agents=[args.agent] if args.agent else None)

    # atdd gate
    elif args.command == "gate":
        gate = ATDDGate()
        return gate.verify(json=args.json)

    elif args.command == "upgrade":
        upgrader = Upgrader()
        return upgrader.run(yes=args.yes)

    # atdd baseline {update,show}
    elif args.command == "baseline":
        from atdd.coach.commands.baseline import BaselineCommand
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        cmd = BaselineCommand(repo_root=repo_path)

        if args.baseline_command == "update":
            return cmd.update(
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
        elif args.baseline_command == "show":
            return cmd.show(verbose=args.verbose)
        else:
            baseline_parser.print_help()
            return 0

    # atdd urn {graph,orphans,broken,validate,resolve,declarations,families,viz}
    elif args.command == "urn":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        cmd = URNCommand(repo_root=repo_path)

        if args.urn_command == "graph":
            return cmd.graph(
                format=args.format,
                root=args.root,
                families=args.families,
                max_depth=args.depth,
                full=args.full,
            )
        elif args.urn_command == "orphans":
            return cmd.orphans(
                families=args.families,
                format=args.format
            )
        elif args.urn_command == "broken":
            return cmd.broken(
                families=args.families,
                format=args.format
            )
        elif args.urn_command == "validate":
            return cmd.validate(
                phase=args.phase,
                families=args.families,
                format=args.format,
                strict=args.strict,
                fix=args.fix,
                dry_run=args.dry_run
            )
        elif args.urn_command == "resolve":
            return cmd.resolve(
                urn=args.urn,
                format=args.format
            )
        elif args.urn_command == "declarations":
            return cmd.declarations(
                families=args.families,
                format=args.format
            )
        elif args.urn_command == "families":
            return cmd.list_families()
        elif args.urn_command == "viz":
            return cmd.viz(
                port=args.port,
                host=args.host,
                root=args.root,
                families=args.families,
                max_depth=args.depth,
            )
        else:
            urn_parser.print_help()
            return 0

    # ----- Handle deprecated flag-based commands -----

    repo_path = Path(args.repo) if args.repo else None
    coach = ATDDCoach(repo_root=repo_path)

    # DEPRECATED: --inventory
    if args.inventory:
        _deprecation_warning("atdd --inventory", "atdd inventory")
        return coach.run_inventory(format=args.format)

    # DEPRECATED: --test
    elif args.test:
        _deprecation_warning(f"atdd --test {args.test}", f"atdd validate {args.test}")
        return coach.run_validators(
            phase=args.test,
            verbose=args.verbose,
            coverage=args.coverage,
            html=args.html,
            quick=False
        )

    # DEPRECATED: --quick
    elif args.quick:
        _deprecation_warning("atdd --quick", "atdd validate --quick")
        return coach.run_validators(quick=True)

    # DEPRECATED: --status
    elif args.status:
        _deprecation_warning("atdd --status", "atdd status")
        return coach.show_status()

    # DEPRECATED: --update-registry
    elif args.update_registry:
        _deprecation_warning(
            f"atdd --update-registry {args.update_registry}",
            f"atdd registry update {args.update_registry}"
        )
        return coach.update_registries(registry_type=args.update_registry)

    else:
        # No command specified - show help
        parser.print_help()
        return 0


def cli() -> int:
    """CLI entry point with version and upgrade checks."""
    # Check if repo needs sync after ATDD upgrade (at startup)
    # Skip if running 'atdd upgrade' — it handles its own messaging
    if not (len(sys.argv) > 1 and sys.argv[1] == "upgrade"):
        print_upgrade_sync_notice()

    try:
        result = main()
    finally:
        # Check for newer versions on PyPI (at end)
        print_update_notice()
    return result


if __name__ == "__main__":
    sys.exit(cli())
