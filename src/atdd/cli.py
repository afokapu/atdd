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
import os
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


def _print_sync_labels_delta(
    issue_number: int,
    delta: dict,
    dry_run: bool,
) -> None:
    """Print the add/remove delta produced by ``IssueManager.sync_labels``."""
    to_add = delta.get("to_add", [])
    to_remove = delta.get("to_remove", [])
    verb = "would" if dry_run else "did"
    if not to_add and not to_remove:
        print(f"#{issue_number}: labels already match body metadata (no-op)")
        return
    print(f"#{issue_number}: sync-labels {'dry-run' if dry_run else 'applied'}")
    if to_add:
        print(f"  {verb} add:    {', '.join(to_add)}")
    if to_remove:
        print(f"  {verb} remove: {', '.join(to_remove)}")


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
        api_only: bool = False,
        no_diagnostics: bool = False,
    ) -> int:
        """Run ATDD validators."""
        if quick:
            return self.validator_runner.quick_check()

        # Issue #473: --skip-api and --api-only are symmetric counterparts.
        # The argparse layer enforces mutual exclusivity; here we map either
        # flag to the appropriate pytest marker filter.
        if skip_api:
            markers = ["not github_api"]
        elif api_only:
            markers = ["github_api"]
        else:
            markers = None

        return self.validator_runner.run_tests(
            phase=phase,
            verbose=verbose,
            coverage=coverage,
            html_report=html,
            parallel=True,
            split=split,
            local=local,
            markers=markers,
            no_diagnostics=no_diagnostics,
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
    from atdd import __version__ as atdd_version

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
    # Issue #473: --skip-api / --api-only are mutually exclusive (running both
    # at once would resolve to an empty marker set and silently skip all tests).
    api_group = validate_parser.add_mutually_exclusive_group()
    api_group.add_argument(
        "--skip-api",
        action="store_true",
        dest="skip_api",
        help="Skip github_api tests (for offline development)"
    )
    api_group.add_argument(
        "--api-only",
        action="store_true",
        dest="api_only",
        help="Run ONLY github_api tests (counterpart to --skip-api)"
    )
    validate_parser.add_argument(
        "--verify-baseline",
        action="store_true",
        dest="verify_baseline",
        help="Verify validation baseline freshness (<10s, no test execution)"
    )
    validate_parser.add_argument(
        "--no-diagnostics",
        action="store_true",
        dest="no_diagnostics",
        help=(
            "Suppress the validation diagnostics artifact and stdout summary "
            "(issue #449). Default: enabled — `.atdd/diagnostics/validation/<phase>.yaml` "
            "is written on every run."
        ),
    )
    validate_parser.add_argument(
        "--diagnostics-only",
        action="store_true",
        dest="diagnostics_only",
        help=(
            "Read and print the most recent diagnostics artifact in <100 ms "
            "without running pytest. Issue #449."
        ),
    )
    validate_parser.add_argument(
        "--no-cache",
        action="store_true",
        dest="no_cache",
        help="Bypass graph disk cache and force a full rebuild"
    )
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Attempt programmatic fixes for selected coach validators "
            "(currently: hand-rolled GitHubClient stubs → autospec). "
            "Scope: coach only."
        ),
    )
    validate_parser.add_argument(
        "--smoke-required",
        metavar="ISSUE",
        type=int,
        default=None,
        help=(
            "Record smoke evidence for ISSUE (.atdd/smoke-evidence/<N>.yaml) "
            "and exit. Unblocks SMOKE→REFACTOR for COACH-RATCHET-PRES-001 "
            "(presentation-layer ratchet improvements over 20%%). Issue #358."
        ),
    )
    validate_parser.add_argument(
        "--permissive-coherence",
        action="store_true",
        dest="permissive_coherence",
        help=(
            "Demote rule-id registry coherence drift to WARN (exit 0). "
            "Default is strict — drift fails the gate (exit 1) when an "
            "emission references a rule_id not declared in any convention "
            "rules: block. Active when phase=coach or all. "
            "Issue #394 (replaces --strict-coherence)."
        ),
    )
    validate_parser.add_argument(
        "--allow-orphan-rules",
        action="store_true",
        dest="allow_orphan_rules",
        help=(
            "Skip the reverse-coherence gate (test_rule_validator_binding). "
            "Emergency unblock only — prefer fixing the violation by adding "
            "a validator: <module>::<func> back-reference to the rule, or "
            "flipping its disposition to documentation-only. "
            "Issue #399."
        ),
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
    # Substrate mode (issue #415, spec v12 §9.3) — mutually exclusive overrides.
    init_substrate_group = init_parser.add_mutually_exclusive_group()
    init_substrate_group.add_argument(
        "--consumer-repo",
        action="store_true",
        dest="consumer_repo",
        help="Force consumer-repo substrate mode (writes repo.* fields to .atdd/config.yaml)"
    )
    init_substrate_group.add_argument(
        "--toolkit",
        action="store_true",
        help="Force toolkit mode (removes substrate fields; only existing toolkit init behavior)"
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
    pr_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Skip the base-branch validation guard (#477). Use only for "
            "legitimate non-default merges (release-train branches, stacked PRs)."
        ),
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
            "  atdd issue 126                     Enter issue #126 (state-driven)\n"
            "  atdd issue my-feature              Create new issue and enter at INIT\n"
            "  atdd issue 126 --status RED        Transition status\n"
            "  atdd issue open                    List open issues\n"
            "  atdd issue sync-labels 126         Re-derive labels from body metadata\n"
            "  atdd issue sync-labels --all       Re-derive labels across every atdd-issue\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    issue_parser.add_argument(
        "target",
        type=str,
        nargs="?",
        help="Issue number (int), slug (str), 'open' (list), or 'sync-labels'"
    )
    issue_parser.add_argument(
        "number",
        type=str,
        nargs="?",
        help="Issue number when target is 'sync-labels'"
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
        "--check",
        action="store_true",
        dest="check",
        help="Run template compliance check and print structured feedback"
    )
    issue_parser.add_argument(
        "--sync-wmbts",
        action="store_true",
        dest="sync_wmbts",
        help="Backfill missing GitHub WMBT sub-issues from plan YAMLs (idempotent)"
    )
    issue_parser.add_argument(
        "--orchestrate",
        action="store_true",
        dest="orchestrate",
        help="Walk the dep graph from this issue and launch atdd orchestrate on the computed wave"
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
        "--all",
        action="store_true",
        dest="all_issues",
        help="Apply sync-labels to every atdd-issue (and atdd-wmbt) in the repo"
    )
    issue_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Report sync-labels delta without mutating GitHub"
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
        choices=["claude", "codex", "gemini", "qwen", "glm", "mistral"],
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

    # ----- atdd session-template <issue-number> -----
    session_template_parser = subparsers.add_parser(
        "session-template",
        help="Generate a parallel-agent launch script from an issue body",
        description=(
            "Read a GitHub issue body and render a self-contained launch "
            "script (SESSION-LAUNCH-TEMPLATE.md) for a parallel agent session."
        ),
    )
    session_template_parser.add_argument(
        "issue_number",
        type=int,
        help="Issue number to render the launch script for",
    )
    session_template_parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Write the rendered script to this path (default: stdout)",
    )
    session_template_parser.add_argument(
        "--worktree-path",
        type=str,
        default="",
        dest="worktree_path",
        help="Worktree path to embed in the launch script (default: derived from branch)",
    )
    session_template_parser.add_argument(
        "--from-checkpoint",
        action="store_true",
        dest="from_checkpoint",
        help=(
            "Inline `.atdd/worker-state-<N>.json` (if present) into the launch "
            "script so a /clear+reload restores worker state without manual "
            "re-briefing. Falls back to default behavior when no checkpoint "
            "exists. See issue #378."
        ),
    )

    # ----- atdd orchestrate <issue-numbers...> -----
    orchestrate_parser = subparsers.add_parser(
        "orchestrate",
        help="Launch parallel agent sessions for a set of issues",
        description=(
            "Compute dependency waves, create worktrees, generate launch "
            "scripts, and launch multiplexer sessions for a list of issues."
        ),
    )
    orchestrate_parser.add_argument(
        "issue_numbers",
        type=int,
        nargs="+",
        help="Issue numbers to orchestrate",
    )
    orchestrate_parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Allow sessions to proceed past REFACTOR without user confirmation",
    )
    orchestrate_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previous orchestrate run from state file",
    )
    orchestrate_parser.add_argument(
        "--multiplexer",
        type=str,
        choices=["cmux", "zellij", "tmux"],
        default=None,
        help="Force multiplexer backend (default: auto-detect)",
    )
    orchestrate_parser.add_argument(
        "--multiplexer-mode",
        type=str,
        choices=["workspace", "pane"],
        default="workspace",
        dest="multiplexer_mode",
        help=(
            "Session unit per issue: 'workspace' spawns a new cmux workspace per issue "
            "(default, back-compat); 'pane' creates a new surface inside the current "
            "workspace (cmux only — mirrors the project/main + project/feat-* worktree "
            "sibling layout)"
        ),
    )
    orchestrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print waves and planned worktrees without creating anything",
    )
    orchestrate_parser.add_argument(
        "--state-file",
        type=str,
        default=".atdd/orchestrate-state.json",
        dest="state_file",
        help="Path to the orchestrate state file (default: .atdd/orchestrate-state.json)",
    )

    # ----- atdd coach <issue-numbers...> -----
    # J1 (#496): state-machine skeleton + §5.1 CLI surface only.
    # Watchers/validators/observers/spawn/two-phase-commit/decision-log
    # writers/resume reconstruction land in adjacent tracks.
    coach_parser = subparsers.add_parser(
        "coach",
        help="Durable per-issue orchestrator (coach v9 skeleton)",
        description=(
            "Initialize a per-issue state machine in INIT and print the "
            "planned state path. Multi-issue invocations reuse "
            "compute_waves() from `atdd orchestrate`."
        ),
    )
    coach_parser.add_argument("issue_numbers", type=int, nargs="+")
    coach_parser.add_argument("--max-retries", type=int, default=None, dest="max_retries")
    coach_parser.add_argument(
        "--escalation-channel", type=str, default=None, dest="escalation_channel"
    )
    coach_parser.add_argument(
        "--multiplexer", type=str, choices=["cmux", "zellij", "tmux"], default=None,
    )
    coach_parser.add_argument(
        "--multiplexer-mode",
        type=str,
        choices=["workspace", "pane"],
        default="workspace",
        dest="multiplexer_mode",
    )
    coach_parser.add_argument("--auto-merge", action="store_true", dest="auto_merge")
    coach_parser.add_argument("--strict-deps", action="store_true", dest="strict_deps")
    coach_parser.add_argument("--llm", type=str, default=None)
    coach_parser.add_argument(
        "--persona-llm",
        type=str,
        default=None,
        dest="persona_llm",
        help="tester=MODEL,coder=MODEL,reviewer=MODEL",
    )
    coach_parser.add_argument("--judge-llm", type=str, default=None, dest="judge_llm")
    coach_parser.add_argument(
        "--require-issue-review",
        type=str,
        choices=["warn", "block", "auto"],
        default="warn",
        dest="require_issue_review",
    )
    coach_parser.add_argument(
        "--review-phases", type=str, default=None, dest="review_phases",
    )
    coach_parser.add_argument("--skip-review", action="store_true", dest="skip_review")
    coach_parser.add_argument(
        "--risk-threshold-block", type=int, default=None, dest="risk_threshold_block",
    )
    coach_parser.add_argument(
        "--allow-stale-suppressions",
        action="store_true",
        dest="allow_stale_suppressions",
    )
    coach_parser.add_argument(
        "--resume", type=str, default=None, metavar="RUN_ID",
        help="Carried for #J6 resume runner; J1 parses but does not reconstruct.",
    )
    coach_parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    # ----- atdd checkpoint <issue-number> -----
    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="Persist worker state to .atdd/worker-state-<issue>.json",
        description=(
            "Write a per-issue worker checkpoint after a phase transition so "
            "that `atdd session-template <N> --from-checkpoint` can rebuild the "
            "launch prompt without manual re-briefing (issue #378)."
        ),
    )
    checkpoint_parser.add_argument(
        "issue_number",
        type=int,
        help="Issue number this checkpoint belongs to",
    )
    checkpoint_parser.add_argument(
        "--phase",
        type=str,
        required=True,
        choices=[
            "INIT", "PLANNED", "RED", "GREEN",
            "SMOKE", "REFACTOR", "COMPLETE", "BLOCKED",
        ],
        help="ATDD phase the worker had just completed",
    )
    checkpoint_parser.add_argument(
        "--summary",
        type=str,
        default="",
        help="Short progress summary (≤500 chars; longer is truncated)",
    )
    checkpoint_parser.add_argument(
        "--open-files",
        type=str,
        default="",
        dest="open_files",
        help="Comma-separated list of open files",
    )
    checkpoint_parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="Branch name (default: detected from git)",
    )
    checkpoint_parser.add_argument(
        "--last-commit",
        type=str,
        default=None,
        dest="last_commit",
        help="Last commit short SHA (default: detected from git)",
    )

    # ----- atdd babysit -----
    babysit_parser = subparsers.add_parser(
        "babysit",
        help="Monitor parallel agent sessions and auto-approve known-safe prompts",
        description=(
            "Periodically read multiplexer screens, auto-approve known-safe "
            "tool prompts, escalate unknowns, and detect policy violations."
        ),
    )
    babysit_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Screen read interval in seconds (default: 60)",
    )
    babysit_parser.add_argument(
        "--workspaces",
        type=str,
        default=None,
        help="Comma-separated workspace refs (default: all known)",
    )
    babysit_parser.add_argument(
        "--stale-warn",
        type=int,
        default=15,
        dest="stale_warn",
        help="Warn after this many minutes of no screen change (default: 15)",
    )
    babysit_parser.add_argument(
        "--stale-escalate",
        type=int,
        default=30,
        dest="stale_escalate",
        help="Escalate after this many minutes of no screen change (default: 30)",
    )
    babysit_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one screen-read cycle and exit (useful for tests/cron)",
    )
    babysit_parser.add_argument(
        "--multiplexer",
        type=str,
        choices=["cmux", "zellij", "tmux"],
        default=None,
        help="Force multiplexer backend (default: auto-detect)",
    )
    babysit_parser.add_argument(
        "--dashboard",
        action="store_true",
        help=(
            "Render an aggregate per-surface dashboard each interval "
            "instead of streaming events to stdout (issue #377)"
        ),
    )
    babysit_parser.add_argument(
        "--approve-all-safe",
        action="store_true",
        dest="approve_all_safe",
        help=(
            "Sweep every monitored surface once, auto-approve prompts that "
            "match the bash allowlist, and exit. Escalations are kept for "
            "manual review (issue #377)"
        ),
    )
    babysit_parser.add_argument(
        "--token-alert-threshold",
        type=int,
        default=None,
        dest="token_alert_threshold",
        help=(
            "Token-count threshold that triggers an escalate alert (default: "
            "loaded from .atdd/config.yaml::babysit.token_alert_threshold or "
            "400000). Source: `claude --print-context-status`. See issue #378."
        ),
    )

    # ----- atdd merge-cascade <pr-numbers...> -----
    merge_cascade_parser = subparsers.add_parser(
        "merge-cascade",
        help="Wave-ordered PR merge with CI gating and update-branch loops",
        description=(
            "For each PR in order, update-branch, wait for required CI checks, "
            "merge. Halt on conflict with a report of the offending PR."
        ),
    )
    merge_cascade_parser.add_argument(
        "pr_numbers",
        type=int,
        nargs="+",
        help="PR numbers to merge in wave order",
    )
    merge_cascade_parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-merge without per-PR prompts",
    )
    merge_cascade_parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        dest="poll_interval",
        help="CI poll interval in seconds (default: 30)",
    )
    merge_cascade_parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-PR timeout in seconds (default: 1800)",
    )
    merge_cascade_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print the merge plan without executing",
    )

    # ----- atdd auto-phase <pr-number> -----
    auto_phase_parser = subparsers.add_parser(
        "auto-phase",
        help="Auto-transition the parent atdd-issue's phase when its PR merges",
        description=(
            "Resolve a PR's parent atdd-issue, read its current phase label, "
            "and run `atdd issue <N> --status <NEXT>` to advance one step "
            "(RED→GREEN, GREEN→SMOKE, SMOKE→REFACTOR, REFACTOR→COMPLETE). "
            "Driven by .github/workflows/atdd-auto-phase.yml on PR merge."
        ),
    )
    auto_phase_parser.add_argument(
        "pr_number",
        type=int,
        help="PR number whose merge triggered the transition",
    )
    auto_phase_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Report the planned transition without executing it",
    )

    # ----- atdd upgrade -----
    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Check PyPI, pip-upgrade if needed, then sync + init --force",
        description=(
            "Query PyPI for a newer atdd release and run "
            "pip install --upgrade if available; otherwise sync the consumer repo "
            "with the installed version."
        ),
    )
    upgrade_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts"
    )
    upgrade_parser.add_argument(
        "--no-pypi",
        action="store_true",
        help="Skip the live PyPI check (use local stamp only)",
    )

    # ----- atdd repo {graph,orphans,broken,validate,resolve,declarations,viz} -----
    # Renamed from the legacy `urn` namespace per spec §9.1 (issue #414).
    # A deprecation shim for the legacy command is registered further down
    # so legacy callers get a clear migration error.
    repo_parser = subparsers.add_parser(
        "repo",
        help="Repo traceability analysis (URN graph, validation, rules)",
        description="Analyze URN coverage, traceability, resolution, and repo rules"
    )
    repo_subparsers = repo_parser.add_subparsers(
        dest="repo_command",
        help="Repo commands"
    )

    # atdd repo graph
    repo_graph_parser = repo_subparsers.add_parser(
        "graph",
        help="Generate URN traceability graph"
    )
    repo_graph_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["json", "dot"],
        default="json",
        help="Output format (default: json)"
    )
    repo_graph_parser.add_argument(
        "--root",
        type=str,
        help="Root URN for subgraph extraction"
    )
    repo_graph_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_graph_parser.add_argument(
        "--depth",
        type=int,
        default=-1,
        help="Maximum depth for subgraph (-1 for unlimited)"
    )
    repo_graph_parser.add_argument(
        "--full",
        action="store_true",
        help="Output full raw nodes + edges (default: agent-optimized summary)"
    )

    # atdd repo orphans
    repo_orphans_parser = repo_subparsers.add_parser(
        "orphans",
        help="Find orphaned URNs (declared but not referenced)"
    )
    repo_orphans_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_orphans_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd repo broken
    repo_broken_parser = repo_subparsers.add_parser(
        "broken",
        help="Find broken URN references"
    )
    repo_broken_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_broken_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd repo validate
    repo_validate_parser = repo_subparsers.add_parser(
        "validate",
        help="Validate URN traceability"
    )
    repo_validate_parser.add_argument(
        "--phase",
        type=str,
        choices=["warn", "fail"],
        default="warn",
        help="Validation phase: warn (errors as warnings) or fail (strict)"
    )
    repo_validate_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_validate_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    repo_validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on warnings too"
    )
    repo_validate_parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix urn:jel:* contract IDs by deriving from file path"
    )
    repo_validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what --fix would change without modifying files"
    )

    # atdd repo resolve
    repo_resolve_parser = repo_subparsers.add_parser(
        "resolve",
        help="Resolve a URN to its artifact(s)"
    )
    repo_resolve_parser.add_argument(
        "urn",
        type=str,
        help="The URN to resolve"
    )
    repo_resolve_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd repo declarations
    repo_declarations_parser = repo_subparsers.add_parser(
        "declarations",
        help="List all URN declarations"
    )
    repo_declarations_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_declarations_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    # atdd repo families
    repo_subparsers.add_parser(
        "families",
        help="List registered URN families"
    )

    # atdd repo viz
    repo_viz_parser = repo_subparsers.add_parser(
        "viz",
        help="Launch interactive URN graph visualizer (requires atdd[viz])"
    )
    repo_viz_parser.add_argument(
        "--port",
        type=int,
        default=8502,
        help="Streamlit server port (default: 8502)"
    )
    repo_viz_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Streamlit server address (default: 127.0.0.1)"
    )
    repo_viz_parser.add_argument(
        "--root",
        type=str,
        help="Root URN for subgraph extraction"
    )
    repo_viz_parser.add_argument(
        "--family",
        type=str,
        action="append",
        dest="families",
        help="Filter by URN families (can be repeated)"
    )
    repo_viz_parser.add_argument(
        "--depth",
        type=int,
        default=-1,
        help="Maximum depth for subgraph (-1 for unlimited)"
    )

    # atdd repo rules — list every repo-derived rule grouped by parent URN
    repo_rules_parser = repo_subparsers.add_parser(
        "rules",
        help="List all repo rules derived from plan/ acceptances",
    )
    repo_rules_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # atdd repo wmbt-rules <wmbt-urn>
    repo_wmbt_rules_parser = repo_subparsers.add_parser(
        "wmbt-rules",
        help="List repo rules derived from a WMBT URN",
    )
    repo_wmbt_rules_parser.add_argument(
        "wmbt_urn",
        type=str,
        help="WMBT URN (e.g. wmbt:govern-lifecycle:D010)",
    )
    repo_wmbt_rules_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # atdd repo train-rules <train-urn>
    repo_train_rules_parser = repo_subparsers.add_parser(
        "train-rules",
        help="List repo rules derived from a train URN",
    )
    repo_train_rules_parser.add_argument(
        "train_urn",
        type=str,
        help="Train URN (e.g. train:0001-self-compliance-validate)",
    )
    repo_train_rules_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # atdd repo security-rules <feature-urn>
    repo_security_rules_parser = repo_subparsers.add_parser(
        "security-rules",
        help="List repo security rules derived from a feature URN",
    )
    repo_security_rules_parser.add_argument(
        "feature_urn",
        type=str,
        help="Feature URN (e.g. feature:auth:session-management)",
    )
    repo_security_rules_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # ----- legacy `urn` deprecation shim (issue #414, spec §9.1) -----
    # The legacy `urn` namespace was renamed to `atdd repo`. The shim prints
    # the canonical deprecation error string and exits non-zero so legacy
    # callers get a clear migration pointer. argparse.REMAINDER swallows any
    # subcommand/flags so legacy invocations of every flavor still hit the
    # dispatcher rather than falling through to argparse's own error path.
    urn_shim_parser = subparsers.add_parser(
        "urn",
        help="(deprecated) renamed to `atdd repo`",
        description="Deprecated — use `atdd repo` instead.",
    )
    urn_shim_parser.add_argument(
        "_legacy_args",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )

    # ----- atdd rules {show,where,grep} (substrate spec v12 §9.2 — issue #409) -----
    rules_parser = subparsers.add_parser(
        "rules",
        help="Inspect the merged rule registry (toolkit + repo-derived)",
        description=(
            "Inspect rules registered in the merged registry. Combines "
            "toolkit conventions and repo-derived acceptance rules from plan/."
        ),
    )
    rules_subparsers = rules_parser.add_subparsers(
        dest="rules_command",
        help="rules commands",
    )

    rules_show_parser = rules_subparsers.add_parser(
        "show",
        help="Print the bound RuleMetadata for a rule-id",
    )
    rules_show_parser.add_argument(
        "rule_id",
        type=str,
        help="Canonical rule-id or legacy alias",
    )
    rules_show_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    rules_where_parser = rules_subparsers.add_parser(
        "where",
        help="Print the rule's source path and YAML location",
    )
    rules_where_parser.add_argument(
        "rule_id",
        type=str,
        help="Canonical rule-id or legacy alias",
    )
    rules_where_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    rules_grep_parser = rules_subparsers.add_parser(
        "grep",
        help="Filter rule-ids/descriptions by regex",
    )
    rules_grep_parser.add_argument(
        "pattern",
        type=str,
        help="Regex matched against rule_id and description",
    )
    rules_grep_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # ----- atdd rules disposition / archetype / suppressions (issue #494) -----
    rules_disposition_parser = rules_subparsers.add_parser(
        "disposition",
        help="List rules by disposition (strict / suppress-and-clean / advisory / documentation-only)",
    )
    rules_disposition_parser.add_argument(
        "value",
        type=str,
        help="Disposition value to filter by",
    )
    rules_disposition_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    rules_archetype_parser = rules_subparsers.add_parser(
        "archetype",
        help="List rules by archetype (coder / coach / tester / planner / repo)",
    )
    rules_archetype_parser.add_argument(
        "value",
        type=str,
        help="Archetype to filter by",
    )
    rules_archetype_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    rules_suppressions_parser = rules_subparsers.add_parser(
        "suppressions",
        help="List active atdd:suppress(...) markers",
    )
    rules_suppressions_parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Filter to markers whose UNTIL date has passed today",
    )
    rules_suppressions_parser.add_argument(
        "--rule",
        type=str,
        default=None,
        metavar="RULE_ID",
        help="Filter to markers for the given rule-id",
    )
    rules_suppressions_parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
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

        # --diagnostics-only: read+print the most recent artifact without
        # invoking pytest. Must complete in <100 ms (issue #449).
        if getattr(args, 'diagnostics_only', False):
            from atdd.coach.commands.diagnostics import (
                print_latest_diagnostics,
            )
            return print_latest_diagnostics(
                phase=args.phase,
                repo_root=repo_path,
            )

        # --smoke-required: record smoke evidence for an issue (#358).
        # Resolves COACH-RATCHET-PRES-001 by writing the gate-unblocking file.
        smoke_required = getattr(args, 'smoke_required', None)
        if smoke_required is not None:
            if args.phase not in ("coder", "all"):
                print(
                    "Error: --smoke-required is only supported with phase "
                    "'coder' (or 'all'). Re-run: atdd validate coder "
                    f"--smoke-required {smoke_required}"
                )
                return 1
            from atdd.coach.utils.repo import find_repo_root
            from atdd.coder.validators.presentation_ratchet import (
                record_smoke_evidence,
            )
            root = repo_path or find_repo_root()
            recorded_by = os.environ.get("USER", "unknown")
            target = record_smoke_evidence(
                root,
                smoke_required,
                recorded_by=recorded_by,
                note="recorded via `atdd validate coder --smoke-required`",
            )
            print(f"Smoke evidence recorded: {target.relative_to(root)}")
            print(
                f"  COACH-RATCHET-PRES-001 unblocked for issue #{smoke_required}."
            )
            return 0

        # --fix: opt-in programmatic fixes for supported coach validators.
        # Currently narrowed to the GitHubClient stub autofixer (#304).
        # Runs before normal validation so the re-run exits clean.
        if getattr(args, 'fix', False):
            if args.phase not in ("coach", "all"):
                print(
                    "Error: --fix is only supported with phase 'coach' (or "
                    "'all'). Re-run with: atdd validate coach --fix"
                )
                return 1
            from atdd.coach.commands.autofix import run_github_client_stub_autofix
            fix_rc = run_github_client_stub_autofix(repo_root=repo_path)
            if fix_rc != 0:
                return fix_rc

        # --verify-baseline: fast path, no test execution. Diagnostics
        # plugin must be a no-op here (issue #449 GT-140) — verify-baseline
        # doesn't run pytest at all, but the env var also flips off the
        # plugin if anything inside the verifier ever does.
        if getattr(args, 'verify_baseline', False):
            os.environ["ATDD_DIAGNOSTICS_DISABLED"] = "1"
            from atdd.coach.commands.validation_baseline import (
                verify_validation_baseline,
            )
            return verify_validation_baseline(
                phase=args.phase,
                repo_root=repo_path,
            )

        # Propagate --no-cache to GraphBuilder via env var
        if getattr(args, 'no_cache', False):
            os.environ["ATDD_NO_CACHE"] = "1"

        # --permissive-coherence: opt the rule-id registry coherence
        # validator out of strict-by-default failure mode and back to WARN.
        # Issue #394 flipped the default; this flag is the opt-out.
        if getattr(args, 'permissive_coherence', False):
            if args.phase not in ("coach", "all"):
                print(
                    "Error: --permissive-coherence is only supported with "
                    "phase 'coach' (or 'all'). Re-run: atdd validate coach "
                    "--permissive-coherence"
                )
                return 1
            os.environ["ATDD_PERMISSIVE_COHERENCE"] = "1"

        # --allow-orphan-rules: opt OUT of reverse-coherence gate (issue #399).
        if getattr(args, "allow_orphan_rules", False):
            if args.phase not in ("coach", "all"):
                print(
                    "Error: --allow-orphan-rules is only supported with "
                    "phase 'coach' (or 'all'). Re-run: atdd validate coach "
                    "--allow-orphan-rules"
                )
                return 1
            os.environ["ATDD_ALLOW_ORPHAN_RULES"] = "1"

        coach = ATDDCoach(repo_root=repo_path)
        skip_api = getattr(args, 'skip_api', False)
        api_only = getattr(args, 'api_only', False)
        no_diagnostics = getattr(args, 'no_diagnostics', False)
        rc = coach.run_validators(
            phase=args.phase,
            verbose=args.verbose,
            coverage=args.coverage,
            html=args.html,
            quick=args.quick,
            split=not args.no_split and not skip_api and not api_only,
            local=args.local,
            skip_api=skip_api,
            api_only=api_only,
            no_diagnostics=no_diagnostics,
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
        return initializer.init(
            force=args.force,
            worktree_layout=args.worktree_layout,
            consumer_repo=getattr(args, "consumer_repo", False),
            toolkit=getattr(args, "toolkit", False),
        )

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
            force=getattr(args, 'force', False),
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

        # atdd issue sync-labels [<N>|--all] [--dry-run]
        if target == "sync-labels":
            manager = IssueManager()
            dry_run = getattr(args, 'dry_run', False)
            apply_all = getattr(args, 'all_issues', False)
            number_str = getattr(args, 'number', None)
            if apply_all:
                results = manager.sync_labels_all(dry_run=dry_run)
                drifted = [
                    (num, delta) for num, delta in results
                    if delta["to_add"] or delta["to_remove"]
                ]
                for num, delta in drifted:
                    _print_sync_labels_delta(num, delta, dry_run=dry_run)
                if not drifted:
                    print(
                        f"sync-labels: every open atdd-issue already matches "
                        f"body metadata ({len(results)} checked)"
                    )
                else:
                    suffix = " (dry-run)" if dry_run else ""
                    print(
                        f"sync-labels: {len(drifted)}/{len(results)} "
                        f"issue(s) drifted{suffix}"
                    )
                return 0
            if not number_str:
                print("Error: atdd issue sync-labels requires an issue number or --all")
                return 1
            try:
                issue_number = int(number_str)
            except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
                print(f"Error: invalid issue number '{number_str}'")
                return 1
            delta = manager.sync_labels(issue_number, dry_run=dry_run)
            _print_sync_labels_delta(issue_number, delta, dry_run=dry_run)
            return 0

        # Detect mode: integer → enter, string → create (future)
        try:
            issue_number = int(target)
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
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

        if getattr(args, 'check', False):
            return lifecycle.check(issue_number)

        if getattr(args, 'sync_wmbts', False):
            manager = IssueManager()
            rc = manager.sync_wmbts(issue_number)
            return 0 if rc >= 0 else 1

        if getattr(args, 'orchestrate', False):
            from atdd.coach.commands.orchestrate_wave_walk import orchestrate_from_issue
            return orchestrate_from_issue(issue_number)

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
  # atdd:suppress(coder.logging.coach-silent-swallow)
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

    # atdd session-template <issue-number>
    elif args.command == "session-template":
        from atdd.coach.commands.session_template import run as run_session_template
        out = Path(args.output) if getattr(args, "output", None) else None
        return run_session_template(
            issue_number=args.issue_number,
            output=out,
            worktree_path=getattr(args, "worktree_path", "") or "",
            from_checkpoint=getattr(args, "from_checkpoint", False),
        )

    # atdd orchestrate <issue-numbers...>
    elif args.command == "orchestrate":
        from atdd.coach.commands.orchestrate import run as run_orchestrate
        return run_orchestrate(
            issue_numbers=args.issue_numbers,
            autonomous=getattr(args, "autonomous", False),
            resume=getattr(args, "resume", False),
            multiplexer=getattr(args, "multiplexer", None),
            multiplexer_mode=getattr(args, "multiplexer_mode", "workspace"),
            dry_run=getattr(args, "dry_run", False),
            state_file=getattr(args, "state_file", ".atdd/orchestrate-state.json"),
        )

    # atdd coach <issue-numbers...> (J1 — #496)
    elif args.command == "coach":
        from atdd.coach.commands.coach import (
            _persona_llm_arg, _review_phases_arg, run as run_coach,
        )
        persona_raw = getattr(args, "persona_llm", None)
        persona = _persona_llm_arg(persona_raw) if persona_raw else {}
        phases_raw = getattr(args, "review_phases", None)
        phases = _review_phases_arg(phases_raw) if phases_raw else set()
        return run_coach(
            issue_numbers=args.issue_numbers,
            max_retries=getattr(args, "max_retries", None),
            escalation_channel=getattr(args, "escalation_channel", None),
            multiplexer=getattr(args, "multiplexer", None),
            multiplexer_mode=getattr(args, "multiplexer_mode", "workspace"),
            auto_merge=getattr(args, "auto_merge", False),
            strict_deps=getattr(args, "strict_deps", False),
            llm=getattr(args, "llm", None),
            persona_llm=persona,
            judge_llm=getattr(args, "judge_llm", None),
            require_issue_review=getattr(args, "require_issue_review", "warn"),
            review_phases=phases,
            skip_review=getattr(args, "skip_review", False),
            risk_threshold_block=getattr(args, "risk_threshold_block", None),
            allow_stale_suppressions=getattr(args, "allow_stale_suppressions", False),
            resume=getattr(args, "resume", None),
            dry_run=getattr(args, "dry_run", False),
        )

    # atdd checkpoint <issue-number>
    elif args.command == "checkpoint":
        from atdd.coach.commands.checkpoint import run as run_checkpoint
        open_files_arg = getattr(args, "open_files", "") or ""
        open_files = [
            f.strip() for f in open_files_arg.split(",") if f.strip()
        ]
        return run_checkpoint(
            issue=args.issue_number,
            phase=args.phase,
            summary=getattr(args, "summary", "") or "",
            open_files=open_files,
            branch=getattr(args, "branch", None),
            last_commit=getattr(args, "last_commit", None),
        )

    # atdd babysit
    elif args.command == "babysit":
        from atdd.coach.commands.babysit import run as run_babysit
        workspaces_arg = getattr(args, "workspaces", None)
        workspaces = (
            [w.strip() for w in workspaces_arg.split(",") if w.strip()]
            if workspaces_arg
            else None
        )
        return run_babysit(
            interval=args.interval,
            workspaces=workspaces,
            stale_warn=args.stale_warn,
            stale_escalate=args.stale_escalate,
            once=getattr(args, "once", False),
            multiplexer=getattr(args, "multiplexer", None),
            dashboard=getattr(args, "dashboard", False),
            approve_all_safe=getattr(args, "approve_all_safe", False),
            token_alert_threshold=getattr(args, "token_alert_threshold", None),
        )

    # atdd merge-cascade <pr-numbers...>
    elif args.command == "merge-cascade":
        from atdd.coach.commands.merge_cascade import run as run_merge_cascade
        return run_merge_cascade(
            pr_numbers=args.pr_numbers,
            auto=getattr(args, "auto", False),
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            dry_run=getattr(args, "dry_run", False),
        )

    # atdd auto-phase <pr-number>
    elif args.command == "auto-phase":
        from atdd.coach.commands.auto_phase import run as run_auto_phase
        return run_auto_phase(
            pr_number=args.pr_number,
            dry_run=getattr(args, "dry_run", False),
        )

    # atdd gate
    elif args.command == "gate":
        gate = ATDDGate()
        return gate.verify(json=args.json)

    elif args.command == "upgrade":
        upgrader = Upgrader()
        return upgrader.run(
            yes=args.yes,
            no_pypi=getattr(args, "no_pypi", False),
        )

    # atdd repo {graph,orphans,broken,validate,resolve,declarations,families,viz,
    #            rules,wmbt-rules,train-rules,security-rules}
    elif args.command == "repo":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None
        cmd = URNCommand(repo_root=repo_path)

        if args.repo_command == "graph":
            return cmd.graph(
                format=args.format,
                root=args.root,
                families=args.families,
                max_depth=args.depth,
                full=args.full,
            )
        elif args.repo_command == "orphans":
            return cmd.orphans(
                families=args.families,
                format=args.format
            )
        elif args.repo_command == "broken":
            return cmd.broken(
                families=args.families,
                format=args.format
            )
        elif args.repo_command == "validate":
            return cmd.validate(
                phase=args.phase,
                families=args.families,
                format=args.format,
                strict=args.strict,
                fix=args.fix,
                dry_run=args.dry_run
            )
        elif args.repo_command == "resolve":
            return cmd.resolve(
                urn=args.urn,
                format=args.format
            )
        elif args.repo_command == "declarations":
            return cmd.declarations(
                families=args.families,
                format=args.format
            )
        elif args.repo_command == "families":
            return cmd.list_families()
        elif args.repo_command == "viz":
            return cmd.viz(
                port=args.port,
                host=args.host,
                root=args.root,
                families=args.families,
                max_depth=args.depth,
            )
        elif args.repo_command in ("rules", "wmbt-rules", "train-rules", "security-rules"):
            from atdd.coach.commands.rules import RepoRulesListing

            listing = RepoRulesListing()
            if args.repo_command == "rules":
                return listing.list_all_repo_rules(format=args.format)
            if args.repo_command == "wmbt-rules":
                return listing.list_rules_for_wmbt(
                    args.wmbt_urn, format=args.format
                )
            if args.repo_command == "security-rules":
                return listing.list_rules_for_feature(
                    args.feature_urn, format=args.format
                )
            return listing.list_rules_for_train(
                args.train_urn, format=args.format
            )
        else:
            repo_parser.print_help()
            return 0

    # legacy `urn` deprecation shim (issue #414, spec §9.1)
    # The legacy `urn` namespace was renamed to `atdd repo`. This shim exits
    # non-zero with the canonical migration error string so legacy callers
    # get a clear pointer. A follow-up issue removes this shim after one
    # minor release.
    elif args.command == "urn":
        print(
            "`atdd urn` was renamed to `atdd repo`. See CHANGELOG for migration.",
            file=sys.stderr,
        )
        return 1

    # atdd rules {show,where,grep,disposition,archetype,suppressions}
    elif args.command == "rules":
        from atdd.coach.commands.rules import RulesCommand

        rules_cmd = RulesCommand()
        if args.rules_command == "show":
            return rules_cmd.show(args.rule_id, format=args.format)
        if args.rules_command == "where":
            return rules_cmd.where(args.rule_id, format=args.format)
        if args.rules_command == "grep":
            return rules_cmd.grep(args.pattern, format=args.format)
        if args.rules_command == "disposition":
            return rules_cmd.disposition(args.value, format=args.format)
        if args.rules_command == "archetype":
            return rules_cmd.archetype(args.value, format=args.format)
        if args.rules_command == "suppressions":
            # Default scan root: the resolved repo root, or CWD as fallback.
            scan_root = Path(args.repo) if args.repo else Path.cwd()
            return rules_cmd.suppressions(
                roots=[scan_root],
                stale_only=args.stale_only,
                rule_id=args.rule,
                format=args.format,
            )
        rules_parser.print_help()
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
