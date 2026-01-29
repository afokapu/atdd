#!/usr/bin/env python3
"""
ATDD Platform - Unified command-line interface.

The coach orchestrates all ATDD lifecycle operations:
- Inventory: Catalog repository artifacts
- Test: Run meta-tests (planner/tester/coder)
- Report: Generate test reports
- Validate: Validate artifacts against conventions

Usage:
    ./atdd.py --inventory                    # Generate inventory
    ./atdd.py --test all                     # Run all meta-tests
    ./atdd.py --test planner                 # Run planner phase tests
    ./atdd.py --test tester                  # Run tester phase tests
    ./atdd.py --test coder                   # Run coder phase tests
    ./atdd.py --test all --coverage          # With coverage report
    ./atdd.py --test all --html              # With HTML report
    ./atdd.py --help                         # Show help
"""

import argparse
import sys
from pathlib import Path

ATDD_DIR = Path(__file__).parent

from atdd.coach.commands.inventory import RepositoryInventory
from atdd.coach.commands.test_runner import TestRunner
from atdd.coach.commands.registry import RegistryUpdater


class ATDDCoach:
    """
    ATDD Platform Coach - orchestrates all operations.

    The coach role coordinates across the three ATDD phases:
    - Planner: Planning phase validation
    - Tester: Testing phase validation (contracts-as-code)
    - Coder: Implementation phase validation
    """

    def __init__(self):
        self.repo_root = ATDD_DIR.parent
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
  %(prog)s --inventory                  Generate full inventory (YAML)
  %(prog)s --inventory --format json    Generate inventory (JSON)
  %(prog)s --test all                   Run all meta-tests
  %(prog)s --test planner               Run planner phase tests
  %(prog)s --test tester                Run tester phase tests
  %(prog)s --test coder                 Run coder phase tests
  %(prog)s --test all --coverage        Run with coverage report
  %(prog)s --test all --html            Run with HTML report
  %(prog)s --test all --verbose         Run with verbose output
  %(prog)s --quick                      Quick smoke test
  %(prog)s --status                     Show platform status

Phase descriptions:
  planner - Validates planning artifacts (wagons, trains, URNs)
  tester  - Validates testing artifacts (contracts, telemetry)
  coder   - Validates implementation (architecture, quality)
        """
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

    # Create coach instance
    coach = ATDDCoach()

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


if __name__ == "__main__":
    sys.exit(main())
