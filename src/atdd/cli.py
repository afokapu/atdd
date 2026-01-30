#!/usr/bin/env python3
"""
ATDD Platform - Unified command-line interface.

The coach orchestrates all ATDD lifecycle operations:
- Inventory: Catalog repository artifacts
- Test: Run meta-tests (planner/tester/coder)
- Report: Generate test reports
- Validate: Validate artifacts against conventions
- Init: Initialize ATDD structure in consumer repos
- Session: Manage session files
- Sync: Sync ATDD rules to agent config files
- Gate: Verify agents loaded ATDD rules

Usage:
    atdd init                                # Initialize ATDD in consumer repo
    atdd session new my-feature              # Create new session
    atdd session list                        # List all sessions
    atdd session archive 01                  # Archive session
    atdd sync                                # Sync ATDD rules to agent configs
    atdd sync --verify                       # Check if files are in sync
    atdd sync --agent claude                 # Sync specific agent only
    atdd gate                                # Show ATDD gate verification
    atdd --inventory                         # Generate inventory
    atdd --test all                          # Run all meta-tests
    atdd --test planner                      # Run planner phase tests
    atdd --test tester                       # Run tester phase tests
    atdd --test coder                        # Run coder phase tests
    atdd --test all --coverage               # With coverage report
    atdd --test all --html                   # With HTML report
    atdd --help                              # Show help
"""

import argparse
import sys
from pathlib import Path

ATDD_DIR = Path(__file__).parent

from atdd.coach.commands.inventory import RepositoryInventory
from atdd.coach.commands.test_runner import TestRunner
from atdd.coach.commands.registry import RegistryUpdater
from atdd.coach.commands.initializer import ProjectInitializer
from atdd.coach.commands.session import SessionManager
from atdd.coach.commands.sync import AgentConfigSync
from atdd.coach.commands.gate import ATDDGate
from atdd.coach.utils.repo import find_repo_root
from atdd.version_check import print_update_notice


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
        self.test_runner = TestRunner(self.repo_root)
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

    def run_tests(
        self,
        phase: str = "all",
        verbose: bool = False,
        coverage: bool = False,
        html: bool = False,
        quick: bool = False
    ) -> int:
        """Run ATDD meta-tests."""
        if quick:
            return self.test_runner.quick_check()

        return self.test_runner.run_tests(
            phase=phase,
            verbose=verbose,
            coverage=coverage,
            html_report=html,
            parallel=True
        )

    def update_registries(self, registry_type: str = "all") -> int:
        """Update registries from source files."""
        if registry_type == "wagons":
            self.registry_updater.update_wagon_registry()
        elif registry_type == "contracts":
            self.registry_updater.update_contract_registry()
        elif registry_type == "telemetry":
            self.registry_updater.update_telemetry_registry()
        else:  # all
            self.registry_updater.update_all()
        return 0

    def show_status(self) -> int:
        """Show quick status summary."""
        print("=" * 60)
        print("ATDD Platform Status")
        print("=" * 60)
        print("\nDirectory structure:")
        print(f"  📋 Planner tests: {ATDD_DIR / 'planner'}")
        print(f"  🧪 Tester tests:  {ATDD_DIR / 'tester'}")
        print(f"  ⚙️  Coder tests:   {ATDD_DIR / 'coder'}")
        print(f"  🎯 Coach:         {ATDD_DIR / 'coach'}")

        # Quick stats
        planner_tests = len(list((ATDD_DIR / "planner").glob("test_*.py")))
        tester_tests = len(list((ATDD_DIR / "tester").glob("test_*.py")))
        coder_tests = len(list((ATDD_DIR / "coder").glob("test_*.py")))

        print(f"\nTest files:")
        print(f"  Planner: {planner_tests} files")
        print(f"  Tester:  {tester_tests} files")
        print(f"  Coder:   {coder_tests} files")
        print(f"  Total:   {planner_tests + tester_tests + coder_tests} files")

        return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ATDD Platform - Coach orchestrates all ATDD operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize ATDD in consumer repo
  %(prog)s init                           Create atdd-sessions/, .atdd/
  %(prog)s init --force                   Overwrite if exists

  # Session management
  %(prog)s session new my-feature         Create SESSION-NN-my-feature.md
  %(prog)s session new my-feature --type migration
  %(prog)s session list                   List all sessions
  %(prog)s session archive 01             Archive SESSION-01-*.md

  # Agent config sync
  %(prog)s sync                           Sync ATDD rules to agent configs
  %(prog)s sync --verify                  Check if files are in sync (CI)
  %(prog)s sync --agent claude            Sync specific agent only
  %(prog)s sync --status                  Show sync status

  # ATDD gate verification
  %(prog)s gate                           Show gate verification info
  %(prog)s gate --json                    Output as JSON

  # Existing flag-based commands (backwards compatible)
  %(prog)s --inventory                    Generate full inventory (YAML)
  %(prog)s --inventory --format json      Generate inventory (JSON)
  %(prog)s --test all                     Run all meta-tests
  %(prog)s --test planner                 Run planner phase tests
  %(prog)s --test tester                  Run tester phase tests
  %(prog)s --test coder                   Run coder phase tests
  %(prog)s --test all --coverage          Run with coverage report
  %(prog)s --test all --html              Run with HTML report
  %(prog)s --test all --verbose           Run with verbose output
  %(prog)s --quick                        Quick smoke test
  %(prog)s --status                       Show platform status

Phase descriptions:
  planner - Validates planning artifacts (wagons, trains, URNs)
  tester  - Validates testing artifacts (contracts, telemetry)
  coder   - Validates implementation (architecture, quality)
        """
    )

    # Subparsers for new commands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ----- atdd init -----
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize ATDD structure in consumer repo",
        description="Create atdd-sessions/ and .atdd/ directories with manifest"
    )
    init_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing files"
    )

    # ----- atdd session {new,list,archive,sync} -----
    session_parser = subparsers.add_parser(
        "session",
        help="Manage session files",
        description="Create, list, and archive session files"
    )
    session_subparsers = session_parser.add_subparsers(
        dest="session_command",
        help="Session commands"
    )

    # atdd session new <slug>
    new_parser = session_subparsers.add_parser(
        "new",
        help="Create new session from template",
        description="Create a new session file with next available number"
    )
    new_parser.add_argument(
        "slug",
        type=str,
        help="Session name (will be converted to kebab-case)"
    )
    new_parser.add_argument(
        "--type", "-t",
        type=str,
        default="implementation",
        choices=["implementation", "migration", "refactor", "analysis", "planning", "cleanup", "tracking"],
        help="Session type (default: implementation)"
    )

    # atdd session list
    session_subparsers.add_parser(
        "list",
        help="List all sessions from manifest"
    )

    # atdd session archive <session_id>
    archive_parser = session_subparsers.add_parser(
        "archive",
        help="Move session to archive/",
        description="Archive a completed session"
    )
    archive_parser.add_argument(
        "session_id",
        type=str,
        help="Session ID to archive (e.g., '01' or '1')"
    )

    # atdd session sync
    session_subparsers.add_parser(
        "sync",
        help="Sync manifest with actual session files"
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

    # ----- Existing flag-based arguments (backwards compatible) -----

    # Repository root override
    parser.add_argument(
        "--repo",
        type=str,
        metavar="PATH",
        help="Target repository root (default: auto-detect from .atdd/)"
    )

    # Main command groups
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Generate repository inventory"
    )

    parser.add_argument(
        "--test",
        type=str,
        choices=["all", "planner", "tester", "coder"],
        metavar="PHASE",
        help="Run tests for specific phase (all, planner, tester, coder)"
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show platform status summary"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick smoke test (no parallel, no reports)"
    )

    parser.add_argument(
        "--update-registry",
        type=str,
        choices=["all", "wagons", "contracts", "telemetry"],
        metavar="TYPE",
        help="Update registry from source files (all, wagons, contracts, telemetry)"
    )

    # Options for inventory
    parser.add_argument(
        "--format",
        type=str,
        choices=["yaml", "json"],
        default="yaml",
        help="Inventory output format (default: yaml)"
    )

    # Options for tests
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose test output"
    )

    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report"
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML test report"
    )

    args = parser.parse_args()

    # ----- Handle subcommands -----

    # atdd init
    if args.command == "init":
        initializer = ProjectInitializer()
        return initializer.init(force=args.force)

    # atdd session {new,list,archive,sync}
    elif args.command == "session":
        manager = SessionManager()

        if args.session_command == "new":
            return manager.new(slug=args.slug, session_type=args.type)
        elif args.session_command == "list":
            return manager.list()
        elif args.session_command == "archive":
            return manager.archive(session_id=args.session_id)
        elif args.session_command == "sync":
            return manager.sync()
        else:
            session_parser.print_help()
            return 0

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

    # ----- Handle flag-based commands (backwards compatible) -----

    # Create coach instance with optional repo override
    repo_path = Path(args.repo) if args.repo else None
    coach = ATDDCoach(repo_root=repo_path)

    # Handle commands
    if args.inventory:
        return coach.run_inventory(format=args.format)

    elif args.test:
        return coach.run_tests(
            phase=args.test,
            verbose=args.verbose,
            coverage=args.coverage,
            html=args.html,
            quick=False
        )

    elif args.quick:
        return coach.run_tests(quick=True)

    elif args.status:
        return coach.show_status()

    elif args.update_registry:
        return coach.update_registries(registry_type=args.update_registry)

    else:
        # No command specified - show help
        parser.print_help()
        return 0


def cli() -> int:
    """CLI entry point with version check."""
    try:
        result = main()
    finally:
        print_update_notice()
    return result


if __name__ == "__main__":
    sys.exit(cli())
