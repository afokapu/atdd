#!/usr/bin/env python3
"""
ATDD Platform - Unified command-line interface.

The coach orchestrates all ATDD lifecycle operations:
- validate: Run validators (planner/tester/coder/coach)
- inventory: Catalog repository artifacts
- status: Show platform status
- registry: Update registries from source files
- init: Initialize ATDD structure in consumer repos
- new/list/update/archive/close-wmbt: Manage GitHub Issues
- sync: Sync ATDD rules to agent config files
- gate: Verify agents loaded ATDD rules

Usage:
    atdd init                                # Initialize ATDD in consumer repo
    atdd new my-feature                      # Create new issue + WMBT sub-issues
    atdd list                                # List all issues
    atdd update 11 --status RED              # Update issue fields
    atdd archive 11                          # Archive issue
    atdd close-wmbt 11 D005                  # Close WMBT sub-issue
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
        quick: bool = False
    ) -> int:
        """Run ATDD validators."""
        if quick:
            return self.validator_runner.quick_check()

        return self.validator_runner.run_tests(
            phase=phase,
            verbose=verbose,
            coverage=coverage,
            html_report=html,
            parallel=True
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

  # Issue management
  %(prog)s new my-feature                 Create GitHub issue + WMBT sub-issues
  %(prog)s new my-feature --type migration
  %(prog)s list                           List all issues
  %(prog)s update 11 --status RED         Update issue fields
  %(prog)s archive 11                     Archive issue
  %(prog)s close-wmbt 11 D005             Close WMBT sub-issue

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

    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

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

    # ----- atdd new <slug> -----
    new_parser = subparsers.add_parser(
        "new",
        help="Create new issue with WMBT sub-issues",
        description="Create a new GitHub Issue with Project v2 fields and WMBT sub-issues"
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
        help="Archive an issue (close parent + sub-issues)"
    )
    archive_top_parser.add_argument("session_id", type=str, help="Issue number to archive")

    # ----- atdd update <issue_number> -----
    update_top_parser = subparsers.add_parser(
        "update",
        help="Update issue Project fields and labels"
    )
    update_top_parser.add_argument("session_id", type=str, help="Issue number")
    update_top_parser.add_argument("--status", "-s", type=str, help="ATDD: Status (INIT/PLANNED/RED/GREEN/REFACTOR/COMPLETE/BLOCKED)")
    update_top_parser.add_argument("--phase", "-p", type=str, help="ATDD: Phase (Planner/Tester/Coder)")
    update_top_parser.add_argument("--branch", "-b", type=str, help="ATDD: Branch name")
    update_top_parser.add_argument("--train", type=str, help="ATDD: Train URN")
    update_top_parser.add_argument("--feature-urn", type=str, help="ATDD: Feature URN")
    update_top_parser.add_argument("--archetypes", type=str, help="ATDD: Archetypes (comma-separated)")
    update_top_parser.add_argument("--complexity", type=str, help="ATDD: Complexity (e.g., 4-High)")
    update_top_parser.add_argument("--force", "-f", action="store_true", help="Bypass gate/body checks on COMPLETE (train still enforced)")

    # ----- atdd close-wmbt <issue_number> <wmbt_id> -----
    close_wmbt_top_parser = subparsers.add_parser(
        "close-wmbt",
        help="Close a WMBT sub-issue"
    )
    close_wmbt_top_parser.add_argument("session_id", type=str, help="Parent issue number")
    close_wmbt_top_parser.add_argument("wmbt_id", type=str, help="WMBT ID (e.g., D001, E003)")
    close_wmbt_top_parser.add_argument("--force", "-f", action="store_true", help="Close even if ATDD cycle checkboxes are unchecked")

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

    # atdd validate [phase]
    if args.command == "validate":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        coach = ATDDCoach(repo_root=repo_path)
        return coach.run_validators(
            phase=args.phase,
            verbose=args.verbose,
            coverage=args.coverage,
            html=args.html,
            quick=args.quick
        )

    # atdd inventory
    elif args.command == "inventory":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
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
        return initializer.init(force=args.force)

    # atdd new <slug>
    elif args.command == "new":
        manager = IssueManager()
        return manager.new(
            slug=args.slug,
            issue_type=args.type,
            train=getattr(args, 'train', None),
            archetypes=getattr(args, 'archetypes', None),
        )

    # atdd list (top-level shorthand)
    elif args.command == "list":
        manager = IssueManager()
        return manager.list()

    # atdd archive <issue_id> (top-level shorthand)
    elif args.command == "archive":
        manager = IssueManager()
        return manager.archive(issue_id=args.session_id)

    # atdd update <issue_id> (top-level shorthand)
    elif args.command == "update":
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

    # atdd close-wmbt <issue_id> <wmbt_id> (top-level shorthand)
    elif args.command == "close-wmbt":
        manager = IssueManager()
        return manager.close_wmbt(
            issue_id=args.session_id,
            wmbt_id=args.wmbt_id,
            force=args.force,
        )

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
    print_upgrade_sync_notice()

    try:
        result = main()
    finally:
        # Check for newer versions on PyPI (at end)
        print_update_notice()
    return result


if __name__ == "__main__":
    sys.exit(cli())
