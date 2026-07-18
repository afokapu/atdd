#!/usr/bin/env python3
"""
ATDD Platform - Unified command-line interface.

The coach orchestrates all ATDD lifecycle operations:
- validate: Run validators (planner/tester/coder/coach)
- inventory: Catalog repository artifacts
- status: Show platform status
- registry: Update registries from source files
- init: Initialize ATDD structure in consumer repos
- author: Author artifacts store-first (`atdd author issue` creates issues)
- coach: Issue lifecycle verbs (enter, transition, issues, close-wmbt, ...)
- list/branch/pr: Issue shortcuts
- sync: Sync ATDD rules to agent config files
- gate: Verify agents loaded ATDD rules

The `atdd issue` monolith was REMOVED (umbrella #1303); its verbs live
under `atdd coach <verb>` and creation under `atdd author issue`.

Usage:
    atdd init                                # Initialize ATDD in consumer repo
    atdd author issue --title T --slug S     # Create new issue + WMBT sub-issues
    atdd coach enter 11                      # Enter issue #11 (state-driven)
    atdd coach transition 11 RED             # Transition issue status
    atdd coach close-wmbt 11 D005            # Close WMBT sub-issue
    atdd coach issues open                   # List open issues
    atdd list                                # List all issues
    atdd sync                                # Sync ATDD rules to agent configs
    atdd sync --verify                       # Check if files are in sync
    atdd sync --agent claude                 # Sync specific agent only
    atdd gate                                # Show ATDD gate verification
    atdd validate                            # Run all validators
    atdd validate planner                    # Run planner validators
    atdd validate tester                     # Run tester validators
    atdd validate coder                      # Run coder validators
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
from atdd.coach.utils.escalation_channel import validate_escalation_channel_arg
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


def _deprecation_warning(old: str, new: str, *, stream=None) -> None:
    """Emit a deprecation warning for legacy flags.

    Defaults to stdout to preserve every existing caller's behavior; the
    substrate-grouping aliases (#1239) pass ``stream=sys.stderr`` so the notice
    never pollutes a command's stdout payload (issue #1239, V2).
    """
    print(
        f"\033[33m⚠️  Deprecated: '{old}' will be removed. Use '{new}' instead.\033[0m",
        file=stream or sys.stdout,
    )


# ---------------------------------------------------------------------------
# Commands removed by a breaking change. Data, not a hard-coded branch, so the
# guard and the tests read the same source.
# ---------------------------------------------------------------------------
REMOVED_COMMANDS = {
    "issue": (
        "`atdd issue` has been REMOVED (umbrella #1303).\n"
        "Its verbs live under `atdd coach`, and creation under `atdd author issue`:\n"
        "\n"
        "  atdd issue <slug>                 -> atdd author issue --title <t> --slug <s>\n"
        "  atdd issue <slug> --dry-run       -> atdd author issue --slug <s> --dry-run\n"
        "  atdd issue <N>                    -> atdd coach enter <N>   (show: atdd coach issues <N>)\n"
        "  atdd issue open                   -> atdd coach issues open\n"
        "  atdd issue <N> --status <TO>      -> atdd coach transition <N> <TO>\n"
        "  atdd issue <N> --check            -> atdd coach check <N>\n"
        "  atdd issue <N> --close-wmbt <ID>  -> atdd coach close-wmbt <N> <ID>\n"
        "  atdd issue reconcile              -> atdd coach reconcile\n"
        "  atdd issue sync-labels [...]      -> atdd coach sync-labels [<N>|--all]\n"
        "  atdd issue is-registered <branch> -> atdd coach is-registered <branch>\n"
        "  atdd issue review <N>             -> atdd coach issue-review <N>\n"
    ),
    "new": (
        "`atdd new` has been REMOVED (#1477).\n"
        "It was the last entry point into the orphaned `IssueManager` mint path,\n"
        "which predates the schema substrate. Creation is store-first and\n"
        "schema-driven:\n"
        "\n"
        "  atdd new <slug>                   -> atdd author issue --title <t> --slug <s>\n"
        "\n"
        "The WMBT sub-issue backfill that rode on it (`atdd coach sync-wmbts`) is\n"
        "removed with it: it resolved plan artifacts through a `wagon` field that\n"
        "the store no longer carries (Wagon -> Train + Feature).\n"
    ),
}

# Global flags that consume the following token, so `atdd --repo X issue` still
# resolves `issue` as the command rather than reading `X` as one.
_VALUE_TAKING_GLOBAL_FLAGS = {"--repo"}


def _removed_command_guard(argv, *, stream=None) -> int | None:
    """Fail loud on a removed command, BEFORE argparse sees it.

    Registering `issue` as a subparser just to reject it would keep it in
    --help and in the C2 subcommand registry; letting argparse reject it emits
    a bare `invalid choice: 'issue'` that names no replacement. Intercepting
    pre-parse gives both: absent from the surface, helpful when invoked.
    """
    stream = stream or sys.stderr
    it = iter(argv)
    for tok in it:
        if tok in _VALUE_TAKING_GLOBAL_FLAGS:
            next(it, None)
            continue
        if tok.startswith("-"):
            continue
        message = REMOVED_COMMANDS.get(tok)
        if message is None:
            return None
        print(f"\033[31mError: {message}\033[0m", file=stream)
        return 2
    return None


def _substrate_root(args) -> str:
    """Resolve the operational Control Root for substrate installs/reads (#1346).

    Extension/workspace installs are git-ignored operational ``.atdd/`` data and
    must land in the single Control Root ``.atdd/`` — never a per-worktree copy.
    Route ``--repo``/cwd through the #1177 control-root resolver so any worktree
    resolves to the shared ``.atdd/``; a consumer repo with no resolvable Control
    Root falls back to the given root unchanged.
    """
    from pathlib import Path
    from atdd.state.paths import resolve_operational_root
    start = Path(args.repo or ".").resolve()
    return str(resolve_operational_root(start))


def _substrate_add(args) -> int:
    """Run substrate admission (`atdd substrate add` / deprecated `atdd add`)."""
    from atdd.substrate import commands as substrate_cmd
    if not args.ref and not args.path:
        print("error: `atdd substrate add` needs a ref/alias or --path")
        return 2
    return substrate_cmd.run_add(
        ref=args.ref, path=args.path,
        project_root=_substrate_root(args), dry_run=args.dry_run,
    )


def _substrate_remove(args) -> int:
    """Run substrate withdrawal (`atdd substrate remove` / deprecated `atdd remove`)."""
    from atdd.substrate import commands as substrate_cmd
    return substrate_cmd.run_remove(
        args.ref, project_root=_substrate_root(args),
        force=args.force, prune=args.prune,
    )


def _substrate_bind(args) -> int:
    """Run binding-plan compose (`atdd substrate bind` / deprecated `atdd bind`)."""
    from atdd.substrate.binding import commands as binding_cmd
    return binding_cmd.run_bind_check(
        project_root=_substrate_root(args), write=not args.no_write,
    )


def _substrate_capabilities(args) -> int:
    """Run capability report (`atdd substrate capabilities` / deprecated `atdd capabilities`)."""
    from atdd.substrate.binding import commands as binding_cmd
    return binding_cmd.run_capabilities(project_root=_substrate_root(args))


def _substrate_list(args) -> int:
    """Render the installed substrate (`atdd substrate list` / deprecated `atdd list --substrate`)."""
    from atdd.substrate import commands as substrate_cmd
    return substrate_cmd.run_list(project_root=_substrate_root(args))


def _get_pr_changed_files(repo_root) -> list:
    """Return files changed in this branch vs origin/main (PR-scoped diff).

    Uses `git merge-base HEAD origin/{default}` so the result is correct even
    when the local default-branch ref is stale behind origin.  Falls back to an
    empty list on any git error (safe: scoped check then exits 0 trivially).
    """
    import subprocess
    cwd = str(repo_root)

    for candidate in ("origin/main", "origin/master"):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            capture_output=True,
            cwd=cwd,
        )
        if probe.returncode == 0:
            base_ref = candidate
            break
    else:
        base_ref = "origin/main"

    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", base_ref],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if base.returncode != 0:
            return []
        merge_base = base.stdout.strip()
        diff = subprocess.run(
            ["git", "diff", f"{merge_base}..HEAD", "--name-only"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-31
        warnings.warn(f"[GT-002] could not determine PR changed files: {exc}", stacklevel=2)
        return []


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
        split: bool = True,
        local: bool = False,
        skip_api: bool = False,
        api_only: bool = False,
        no_diagnostics: bool = False,
    ) -> int:
        """Run ATDD validators."""
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
        check: bool = False,
        scope: str = None
    ) -> int:
        """Update registries from source files.

        Args:
            registry_type: Which registry to update (all, wagons, trains, contracts, etc.)
            apply: If True, apply changes without prompting (CI mode)
            check: If True, only check for drift without applying (exit 1 if drift)
            scope: If "changed-files", limit check to wagon sources in git diff main..HEAD

        Returns:
            0 on success, 1 if --check and drift detected
        """
        # PR-scoped registry check (wmbt:govern-lifecycle:E018)
        if check and scope == "changed-files":
            changed_files = _get_pr_changed_files(self.repo_root)
            outcome = self.registry_updater.check_wagon_registry_scoped(changed_files)
            return 1 if outcome.get("has_changes") else 0

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

  # Issue lifecycle (`atdd issue` was removed — see #1303)
  %(prog)s author issue --title T --slug S  Create issue + WMBT sub-issues
  %(prog)s coach enter 11                 Enter issue #11 (state-driven)
  %(prog)s coach transition 11 RED        Transition issue status
  %(prog)s coach close-wmbt 11 D005       Close WMBT sub-issue
  %(prog)s coach issues open              List open issues
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
        choices=["all", "planner", "tester", "coder", "coach", "package"],
        help="Phase to validate, or 'package' to compose-validate an installed package (default: all)"
    )
    validate_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Package directory (for 'atdd validate package <path>')"
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
    registry_update_parser.add_argument(
        "--scope",
        default=None,
        metavar="SCOPE",
        help="Limit drift check scope. Use 'changed-files' to validate only wagon sources "
             "in `git diff main..HEAD` (PR-scoped GT-002 gate; exits 0 trivially when no "
             "wagon sources were touched)"
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

    # NOTE: 'atdd new' was REMOVED by #1477 — it was the only live entry point
    # into the orphaned IssueManager mint path. See REMOVED_COMMANDS["new"];
    # creation is `atdd author issue` (store-first, schema-driven — #1272).

    # NOTE: 'session' subcommand removed in E009; replaced by top-level issue commands.

    # ----- atdd list -----
    list_parser = subparsers.add_parser(
        "list",
        help="List all ATDD issues (or the installed substrate with --substrate)"
    )
    list_parser.add_argument(
        "--substrate",
        action="store_true",
        help="List the installed substrate (.atdd/substrate.lock.yaml) instead of issues",
    )

    # ----- atdd archive <issue_number> -----
    archive_top_parser = subparsers.add_parser(
        "archive",
        help="[DEPRECATED] Use 'atdd coach transition <N> COMPLETE' instead"
    )
    archive_top_parser.add_argument("session_id", type=str, help="Issue number to archive")

    # ----- atdd update <issue_number> -----
    update_top_parser = subparsers.add_parser(
        "update",
        help="[DEPRECATED] Use 'atdd coach transition <N> <S>' instead"
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

    # ----- atdd branch <issue_number> — DEPRECATED alias for `atdd worktree create` -----
    branch_parser = subparsers.add_parser(
        "branch",
        help="[DEPRECATED] Use 'atdd worktree create <N>' instead",
        description="[DEPRECATED alias, #1347] Create a git worktree from issue metadata. Use `atdd worktree create <N>`."
    )
    branch_parser.add_argument("issue_number", type=int, help="Issue number")
    branch_parser.add_argument(
        "--prefix",
        type=str,
        help="Override branch prefix (feat, fix, refactor, chore, docs, devops)"
    )

    # ----- atdd worktree {create,gc,list,remove} (#1347) -----
    # One object-verb command for the agent's working environment (worktree +
    # branch + store binding). `create` is the former `atdd branch`.
    worktree_parser = subparsers.add_parser(
        "worktree",
        help="Manage git worktrees (create/gc/list/remove)",
        description="Create and manage the git worktrees that are agent working environments",
    )
    worktree_subparsers = worktree_parser.add_subparsers(dest="worktree_command")

    worktree_create_parser = worktree_subparsers.add_parser(
        "create",
        help="Create a worktree branch from issue metadata",
        description=(
            "Create a git worktree with the correct prefix/slug naming derived\n"
            "from issue metadata, based on origin/<default>, and register the\n"
            "branch↔issue↔worktree binding in the State Store (never a commit on\n"
            "local main).\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    worktree_create_parser.add_argument("issue_number", type=int, help="Issue number")
    worktree_create_parser.add_argument(
        "--prefix",
        type=str,
        help="Override branch prefix (feat, fix, refactor, chore, docs, devops)",
    )

    worktree_gc_parser = worktree_subparsers.add_parser(
        "gc",
        help="Detect and clean up orphan worktree directories",
        description=(
            "Scan sibling-of-main directories for atdd orphan worktrees\n"
            "(dirs not in `git worktree list` containing only .launch_prompt.txt).\n\n"
            "  atdd worktree gc            List orphans (dry-run)\n"
            "  atdd worktree gc --apply    Remove orphans\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    worktree_gc_parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove orphan directories (default: list only)",
    )

    worktree_subparsers.add_parser(
        "list",
        help="List atdd worktrees and their store bindings",
        description="List every registered git worktree with its branch and bound work item.",
    )

    worktree_remove_parser = worktree_subparsers.add_parser(
        "remove",
        help="Remove a worktree by issue number or path",
        description=(
            "Remove a registered git worktree (issue number → derived path, or an\n"
            "explicit path). Refuses the main checkout; never uses --force.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    worktree_remove_parser.add_argument(
        "target", type=str, help="Issue number or worktree path to remove"
    )

    # ----- atdd cleanup -----
    # #928 Gap 2: remove merged-but-not-removed worktrees + orphan branches.
    # Complements `atdd worktree gc` (which only removes non-git scratch dirs).
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove merged worktrees + orphan branches (post-merge cleanup)",
        description=(
            "Detect worktrees whose branch has merged (ancestor of origin/main "
            "OR a merged PR — catches squash-merges) and orphan merged branches.\n\n"
            "  atdd cleanup        List what would be removed (dry-run)\n"
            "  atdd cleanup --yes  Remove worktrees + prune their branches\n\n"
            "main is never touched; worktrees with uncommitted changes are skipped."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cleanup_parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply the cleanup (default: dry-run list only)",
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
        help="[DEPRECATED] Use 'atdd coach close-wmbt <N> <ID>' instead"
    )
    close_wmbt_top_parser.add_argument("session_id", type=str, help="Parent issue number")
    close_wmbt_top_parser.add_argument("wmbt_id", type=str, help="WMBT ID (e.g., D001, E003)")
    close_wmbt_top_parser.add_argument("--force", "-f", action="store_true", help="Close even if ATDD cycle checkboxes are unchecked")

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

    # ----- atdd hooks -----
    # The resolution seam the installed hook dispatchers call on every git
    # operation (#1492). Keep it fast and side-effect free.
    hooks_parser = subparsers.add_parser(
        "hooks",
        help="Inspect the git hooks shipped by the installed atdd package",
        description=(
            "Resolve the packaged git hooks that .atdd/hooks/* dispatchers exec. "
            "Installed hooks are fixed-content dispatchers, so hook logic ships "
            "with the package and cannot drift from it."
        ),
    )
    hooks_sub = hooks_parser.add_subparsers(dest="hooks_command")
    hooks_path_parser = hooks_sub.add_parser(
        "path",
        help="Print the absolute path of a packaged hook (exit 1 if unresolvable)",
    )
    hooks_path_parser.add_argument("name", type=str, help="Hook name, e.g. commit-msg")
    hooks_sub.add_parser(
        "list",
        help="List every hook name the installed package ships",
    )

    # ----- atdd sync -----
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync ATDD rules to agent config files",
        description="Sync managed ATDD blocks to agent config files (CLAUDE.md, CONDUCTOR.md, etc.)"
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

    # ----- atdd doctor -----
    # Environment self-diagnosis (#928 Gap 4): flags the source-repo /
    # foreign-install mismatch that silently makes `atdd validate` test the
    # released wheel instead of the working tree, and the git-hook python3
    # that cannot import atdd (the misleading "requires a newer atdd" gate).
    subparsers.add_parser(
        "doctor",
        help="Diagnose the atdd install/environment (source-repo & hook interpreter)",
        description=(
            "Detect when atdd is imported from a foreign install while you are "
            "in the source checkout (so validators test stale released code), "
            "or when the git hooks' python3 cannot import atdd."
        ),
    )

    # ----- atdd plan <op> ... -----
    # #1208/#1139: `atdd plan` IS the gated decomposition session. The session
    # owns its own argparse (plan_session_cli); all `atdd plan ...` argv is
    # intercepted before parse_args (see below) and forwarded to it. This stub
    # exists only so `atdd --help` lists `plan`. The legacy PLAN-1 brief renderer
    # (#758) is decommissioned.
    plan_parser = subparsers.add_parser(
        "plan",
        help="Run the atdd plan gated decomposition session (Define→Locate→Prepare→Confirm→author).",
        add_help=False,
    )
    plan_parser.add_argument("plan_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

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

    # ----- atdd coach <issue-numbers...> / atdd coach status ... -----
    # J1 (#496): state-machine skeleton + §5.1 CLI surface.
    # #616 (L001): adds `atdd coach status` live-inspection subcommand.
    # Parsing is forwarded to coach.run_cli() which dispatches between
    # the status path and the existing issue-numbers path.
    coach_parser = subparsers.add_parser(
        "coach",
        help=(
            "Durable per-issue orchestrator (coach v9). "
            "Inspect a running session: `atdd coach status [--run-id ID]`"
        ),
        add_help=False,
    )
    coach_parser.add_argument(
        "coach_argv",
        nargs=argparse.REMAINDER,
        help="Forwarded to atdd.coach.commands.coach",
    )

    # ----- atdd resume <run_id> (Child 9 — #896) -----
    # New public CLI surface (docs/coach-decomposition.md §3.4, §7.4): replay a
    # crashed train run from its durable event log (§6.3). The args are declared
    # here (so `atdd resume --help` renders via the top-level parser); the dispatch
    # forwards them to `atdd.train.resume_cli.run_args` — the train layer owns the
    # logic, the dependency points inward (train MUST NOT import atdd.cli, §3.3).
    resume_parser = subparsers.add_parser(
        "resume",
        help="Replay a crashed train run and continue from where it stopped.",
        description=(
            "Replay a crashed train run from its durable event log and continue "
            "from where it stopped. Deterministic crash-recovery: given the same "
            "frozen conventions snapshot, event log, and external state, resume "
            "reproduces identical decisions with no double-execution "
            "(docs/coach-decomposition.md §6.3)."
        ),
    )
    resume_parser.add_argument(
        "run_id",
        metavar="RUN_ID",
        help="The run id to resume (e.g. run-816-20260530-a81b0d90).",
    )
    resume_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        dest="resume_repo_root",
        help="Repo root holding .atdd/runtime/runs/ (defaults to the cwd).",
    )

    # NOTE (#1486): `atdd agent`, `atdd observer` and `atdd spawn` were the coach's
    # sub-worker orchestration verbs (spawn/observe a persona agent). Orchestration
    # left core, so those verbs and their backing modules are gone.

    # ----- atdd author ... (author-atdd-substrate wagon, #1097) -----
    # Author schema-valid substrate artifacts by construction. The sub-arg
    # surface (convention-node / relationship / scope / gate) lives in
    # `atdd.planner.commands.author.build_parser`; we register `author` here
    # and forward argv. The first forwarded token is the kind (a positional),
    # so REMAINDER captures it cleanly.
    author_parser = subparsers.add_parser(
        "author",
        help="Author schema-valid ATDD substrate artifacts by construction.",
        add_help=False,
    )
    author_parser.add_argument(
        "author_argv",
        nargs=argparse.REMAINDER,
        help="Forwarded to atdd.planner.commands.author",
    )

    # ----- atdd state <subcommand> ... (#1168 State Store, Phase 1 — #1177) -----
    # The State Store command surface (doctor / layout --check). argparse for the
    # sub-subcommands lives in `atdd.state.cli.run`; we register `state` here with
    # REMAINDER and forward argv so the surface stays in one place.
    state_parser = subparsers.add_parser(
        "state",
        help="ATDD State Store — local operational data layout (#1168).",
        add_help=False,
    )
    state_parser.add_argument(
        "state_argv",
        nargs=argparse.REMAINDER,
        help="Forwarded to atdd.state.cli",
    )

    # ----- atdd enforce [--paths ...] [--conformance] [--verify-substrate] -----
    # Lock-driven extension enforcement runner (#1238). Operator/CI hot path, so
    # it sits top-level next to `validate`. argparse for its flags lives in
    # `atdd.enforce.cli.run`; we register `enforce` here with REMAINDER and
    # forward argv so the surface stays in one place (the `author`/`state` idiom).
    enforce_parser = subparsers.add_parser(
        "enforce",
        help="Enforce the binding plan over consumer code (#1238).",
        add_help=False,
    )
    enforce_parser.add_argument(
        "enforce_argv",
        nargs=argparse.REMAINDER,
        help="Forwarded to atdd.enforce.cli",
    )

    # NOTE (#1486): `atdd judge` (the coach's structured-output routing boundary for
    # sub-worker decisions) was decommissioned with the rest of the orchestration
    # verbs. Its generic LLM registry/protocol survives at
    # `atdd.coach.commands.llm_clients.registry`.

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
            "and run `atdd coach transition <N> <NEXT>` to advance one step "
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
        help="Check PyPI, upgrade if needed (pipx/pip-aware), then sync + init --force",
        description=(
            "Query PyPI for a newer atdd release and run the correct upgrade command "
            "(pipx upgrade atdd, pip install --upgrade, or git pull) for the detected "
            "install method; otherwise sync the consumer repo with the installed version."
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
        choices=["json", "dot", "prompt", "launch-prompt"],
        default="json",
        help="Output format (default: json); 'prompt' requires --issue; 'launch-prompt' requires --wagon"
    )
    repo_graph_parser.add_argument(
        "--issue",
        type=int,
        default=None,
        help="GitHub issue number; with --format prompt, outputs the Architecture context section"
    )
    repo_graph_parser.add_argument(
        "--wagon",
        type=str,
        default=None,
        help="Wagon slug; with --format launch-prompt, outputs the wagon-scoped launch-prompt section"
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

    # ----- atdd suppress backfill (issue #482) -----
    suppress_parser = subparsers.add_parser(
        "suppress",
        help="Suppress-marker utilities",
        description="Commands for managing inline atdd:suppress(...) markers",
    )
    suppress_subparsers = suppress_parser.add_subparsers(dest="suppress_command")
    suppress_backfill_parser = suppress_subparsers.add_parser(
        "backfill",
        help="Bulk-insert inline suppress markers on pre-existing violation sites",
        description=(
            "Walk the rule's scanner to enumerate current violation sites and\n"
            "insert a language-appropriate inline suppress comment idempotently.\n\n"
            "  atdd suppress backfill --rule coder.logging.coach-silent-swallow --until 2026-Q4"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    suppress_backfill_parser.add_argument(
        "--rule",
        type=str,
        required=True,
        metavar="RULE_ID",
        help="Rule id to suppress (e.g. coder.logging.coach-silent-swallow)",
    )
    suppress_backfill_parser.add_argument(
        "--until",
        type=str,
        required=True,
        metavar="DATE",
        help="UNTIL= date for the suppress marker (e.g. 2026-Q4 or 2026-12-31)",
    )
    suppress_backfill_parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="List sites that would be marked without editing any files",
    )

    # ----- atdd emergency — single-use hook bypass (E031) -----
    emergency_parser = subparsers.add_parser(
        "emergency",
        help="Create a single-use 5-minute hook bypass for genuine emergencies",
        description=(
            "Create .atdd/EMERGENCY_BYPASS so ATDD hook gates allow ONE git operation.\n"
            "\n"
            "All ATDD_SKIP_* env-var bypasses were retired (E030, 2026-05-26).\n"
            "This is the ONLY sanctioned bypass path.\n"
            "\n"
            "Example:\n"
            "  atdd emergency --reason 'validator outage; fix tracked in #999'\n"
            "  git push   # bypass valid for 5 minutes\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    emergency_parser.add_argument(
        "--reason",
        required=True,
        help="Why the bypass is needed (logged to .atdd/emergency-audit.jsonl)",
    )

    # ----- atdd manifest {backfill} — manifest maintenance (#664) -----
    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Manifest maintenance commands",
        description="Commands for maintaining .atdd/manifest.yaml.",
    )
    manifest_subparsers = manifest_parser.add_subparsers(
        dest="manifest_command",
        help="manifest commands",
    )
    manifest_subparsers.add_parser(
        "backfill",
        help=(
            "Backfill missing open atdd-issues from GitHub into .atdd/manifest.yaml. "
            "Idempotent — re-running on a complete manifest is a no-op. "
            "Equivalent to: atdd coach reconcile"
        ),
    )

    # ----- Substrate admission (wagon: admit-substrate) -----
    search_parser = subparsers.add_parser(
        "search", help="Search configured registries for admittable artifacts"
    )
    search_parser.add_argument("query", help="alias, canonical id, or tag substring")
    search_parser.add_argument(
        "--kind", choices=["extension", "workspace"], default=None,
        help="restrict results to a kind",
    )

    # ----- atdd substrate {add,remove,bind,capabilities,list} (#1239) -----
    # Canonical noun-grouped home for the substrate-management verbs. The flat
    # top-level verbs below are kept as DEPRECATED-but-working aliases (their
    # removal is the breaking MAJOR step owned by #1207/4.0.0).
    substrate_parser = subparsers.add_parser(
        "substrate",
        help="Manage the local substrate (admit/bind/inspect extensions & workspaces)",
        description=(
            "Manage the local substrate — the install ledger covering both "
            "atdd.extension.* and atdd.workspace.* packages. Canonical home for "
            "add / remove / bind / capabilities / list."
        ),
    )
    substrate_subparsers = substrate_parser.add_subparsers(
        dest="substrate_command", metavar="{add,remove,bind,capabilities,list}",
    )

    def _add_substrate_add_args(p):
        p.add_argument("ref", nargs="?", help="registry ref or alias")
        p.add_argument("--path", help="admit a local package directory directly")
        p.add_argument(
            "--dry-run", action="store_true", help="validate + compose only; do not install"
        )

    def _add_substrate_remove_args(p):
        p.add_argument("ref", help="artifact id to remove")
        p.add_argument(
            "--force", action="store_true", help="remove even if other artifacts depend on it"
        )
        p.add_argument(
            "--prune", action="store_true", help="also remove now-unused workspaces"
        )

    def _add_substrate_bind_args(p):
        p.add_argument(
            "--check", action="store_true",
            help="compose + validate the binding plan (never executes an implementation)",
        )
        p.add_argument(
            "--no-write", action="store_true", help="do not write .atdd/binding.lock.yaml"
        )

    _add_substrate_add_args(substrate_subparsers.add_parser(
        "add", help="Admit an extension/workspace artifact into the local substrate"))
    _add_substrate_remove_args(substrate_subparsers.add_parser(
        "remove", help="Withdraw an artifact from the local substrate"))
    _add_substrate_bind_args(substrate_subparsers.add_parser(
        "bind", help="Compose the runtime binding plan from the locked substrate"))
    substrate_subparsers.add_parser(
        "capabilities",
        help="Show conventions gated by bound implementations vs legacy-fallback")
    substrate_subparsers.add_parser(
        "list", help="List the installed substrate (.atdd/substrate.lock.yaml)")

    # ----- Substrate admission (wagon: admit-substrate) — DEPRECATED flat aliases -----
    add_cmd_parser = subparsers.add_parser(
        "add",
        help="[DEPRECATED] Use 'atdd substrate add' instead",
        description="DEPRECATED: Use 'atdd substrate add' instead.\n\n"
                    "Admit an extension/workspace artifact into the local substrate.",
    )
    _add_substrate_add_args(add_cmd_parser)

    remove_cmd_parser = subparsers.add_parser(
        "remove",
        help="[DEPRECATED] Use 'atdd substrate remove' instead",
        description="DEPRECATED: Use 'atdd substrate remove' instead.\n\n"
                    "Withdraw an artifact from the local substrate.",
    )
    _add_substrate_remove_args(remove_cmd_parser)

    # ----- Substrate binding (wagon: bind-substrate-runtime) — DEPRECATED flat aliases -----
    bind_cmd_parser = subparsers.add_parser(
        "bind",
        help="[DEPRECATED] Use 'atdd substrate bind' instead",
        description="DEPRECATED: Use 'atdd substrate bind' instead.\n\n"
                    "Compose the runtime binding plan from the locked substrate.",
    )
    _add_substrate_bind_args(bind_cmd_parser)

    subparsers.add_parser(
        "capabilities",
        help="[DEPRECATED] Use 'atdd substrate capabilities' instead",
        description="DEPRECATED: Use 'atdd substrate capabilities' instead.\n\n"
                    "Show conventions gated by bound implementations vs legacy-fallback.",
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

    # `atdd plan <op> ...` — the gated decomposition session (#1139) IS `atdd plan`
    # (#1208). It owns its own argparse (sub-flags like --id/--root/--step), so
    # intercept ALL plan argv before parse_args and forward to it. The legacy
    # PLAN-1 brief renderer is decommissioned; there is no brief surface to fall to.
    import sys as _sys
    if _sys.argv[1:2] == ["plan"]:
        from atdd.planner.commands.plan_session_cli import run as _run_session
        return _run_session(_sys.argv[2:])

    # `atdd enforce ...` owns its own argparse (--paths/--conformance/
    # --verify-substrate, all leading-dash flags that argparse REMAINDER cannot
    # capture). Intercept its argv before parse_args and forward, the same way
    # `plan` does. The `enforce` subparser above keeps it in --help/usage.
    if _sys.argv[1:2] == ["enforce"]:
        from atdd.enforce.cli import run as _run_enforce
        return _run_enforce(_sys.argv[2:])

    # `atdd author ...` / `atdd coach ...` forward argv to their own sub-CLIs via
    # a REMAINDER positional, which cannot capture a *leading* `-h`/`--help` — it
    # bubbles back to the top parser as `unrecognized arguments: -h` (#1325 item
    # 1). Intercept before parse_args, the same way `plan`/`enforce` do, so bare
    # `atdd author -h` / `atdd coach -h` reach the sub-CLI's own help. The stub
    # subparsers above keep both listed in `atdd --help`. (The `command ==`
    # dispatch branches below still serve the `atdd --repo PATH author ...` form,
    # where the global flag precedes the subcommand and this intercept does not
    # fire.)
    if _sys.argv[1:2] == ["author"]:
        from atdd.planner.commands.author import run as _run_author
        return _run_author(_sys.argv[2:])
    if _sys.argv[1:2] == ["coach"]:
        from atdd.coach.commands.coach import run_cli as _run_coach
        return _run_coach(_sys.argv[2:])

    # #1309: `atdd issue` was removed. Intercept before parse_args so the
    # operator gets the replacement map instead of argparse's `invalid choice`.
    _removed_rc = _removed_command_guard(_sys.argv[1:])
    if _removed_rc is not None:
        return _removed_rc

    args = parser.parse_args()

    # ----- Handle modern subcommands -----

    # atdd version
    if args.command == "version":
        print(f"atdd {atdd_version}")
        return 0

    # atdd validate [phase]
    elif args.command == "validate":
        repo_path = Path(args.repo) if hasattr(args, 'repo') and args.repo else None

        # atdd validate package <path> (#1133): compose-validate an installed
        # extension/workspace package against core (package-relative core load;
        # no runtime execution). Distinct from the pytest validator phases below.
        if getattr(args, "phase", None) == "package":
            from atdd.planner.commands.compose import validate_package_cli
            return validate_package_cli(getattr(args, "path", None))

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
                check=args.check,
                scope=getattr(args, "scope", None),
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

    # atdd list (top-level shorthand)
    elif args.command == "list":
        if getattr(args, "substrate", False):
            # DEPRECATED alias for `atdd substrate list` (#1239) — still works.
            _deprecation_warning("atdd list --substrate", "atdd substrate list", stream=sys.stderr)
            return _substrate_list(args)
        manager = IssueManager()
        return manager.list()

    # ----- atdd substrate {add,remove,bind,capabilities,list} (#1239) -----
    # Canonical noun-grouped surface; routes to the same handlers as the flat
    # verbs below (which remain as deprecated aliases until #1207/4.0.0).
    elif args.command == "substrate":
        sub = getattr(args, "substrate_command", None)
        if sub == "add":
            return _substrate_add(args)
        elif sub == "remove":
            return _substrate_remove(args)
        elif sub == "bind":
            return _substrate_bind(args)
        elif sub == "capabilities":
            return _substrate_capabilities(args)
        elif sub == "list":
            return _substrate_list(args)
        substrate_parser.print_help()
        return 2

    # ----- Substrate admission (wagon: admit-substrate) -----
    elif args.command == "search":
        from atdd.substrate import commands as substrate_cmd
        return substrate_cmd.run_search(
            args.query, kind=args.kind, project_root=_substrate_root(args)
        )

    # DEPRECATED flat aliases — delegate to `atdd substrate <verb>` (#1239)
    elif args.command == "add":
        _deprecation_warning("atdd add", "atdd substrate add", stream=sys.stderr)
        return _substrate_add(args)

    elif args.command == "remove":
        _deprecation_warning("atdd remove", "atdd substrate remove", stream=sys.stderr)
        return _substrate_remove(args)

    elif args.command == "bind":
        _deprecation_warning("atdd bind", "atdd substrate bind", stream=sys.stderr)
        return _substrate_bind(args)

    elif args.command == "capabilities":
        _deprecation_warning("atdd capabilities", "atdd substrate capabilities", stream=sys.stderr)
        return _substrate_capabilities(args)

    # atdd archive <issue_id> — DEPRECATED, delegates to atdd coach transition <N> COMPLETE
    elif args.command == "archive":
        _deprecation_warning("atdd archive <N>", "atdd coach transition <N> COMPLETE")
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()
        issue_number = int(args.session_id)
        return lifecycle.transition(issue_number, "COMPLETE", force=False)

    # atdd update <issue_id> --status <S> — DEPRECATED, delegates to atdd coach transition
    elif args.command == "update":
        status = getattr(args, 'status', None)
        if status:
            # Written FLAG-FIRST on purpose: build_deprecation_registry keys on the
            # first two tokens unless token[2] is a flag, so "atdd update <N>
            # --status <S>" would register a WHOLESALE `atdd update` deprecation and
            # false-flag the still-valid `atdd update <N> --train <T>` (the only
            # surface for train/feature/archetypes). Flag-first keys it as
            # `atdd update --status`, deprecating only the status form.
            _deprecation_warning("atdd update --status <S>", "atdd coach transition <N> <S>")
            from atdd.coach.commands.issue_lifecycle import IssueLifecycle
            lifecycle = IssueLifecycle()
            issue_number = int(args.session_id)
            return lifecycle.transition(
                issue_number, status,
                force=getattr(args, 'force', False),
            )
        # Non-status field updates (train / feature / archetypes / complexity /
        # branch) have NO coach or author equivalent — `IssueManager.update` is
        # the only surface for them. It was previously deprecated toward
        # `atdd issue`, which #1309 removed; rather than repoint that hint at
        # another command that cannot do the job, the bare form is simply not
        # deprecated. Emitting a warning here would send operators nowhere.
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
        # DEPRECATED (#1347) — delegates to `atdd worktree create`.
        _deprecation_warning("atdd branch <N>", "atdd worktree create <N>", stream=sys.stderr)
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

    # atdd close-wmbt <issue_id> <wmbt_id> — DEPRECATED, delegates to atdd coach close-wmbt
    elif args.command == "close-wmbt":
        _deprecation_warning("atdd close-wmbt <N> <ID>", "atdd coach close-wmbt <N> <ID>")
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        lifecycle = IssueLifecycle()
        issue_number = int(args.session_id)
        return lifecycle.close_wmbt(
            issue_number,
            args.wmbt_id,
            force=args.force,
        )

    # atdd worktree <subcommand>
    elif args.command == "worktree":
        worktree_cmd = getattr(args, 'worktree_command', None)
        if worktree_cmd == "create":
            from atdd.coach.commands.branch import BranchManager
            return BranchManager().branch(
                issue_number=args.issue_number,
                prefix=getattr(args, 'prefix', None),
            )
        if worktree_cmd == "gc":
            from atdd.coach.commands.worktree_gc import gc as worktree_gc
            orphans = worktree_gc(apply=getattr(args, 'apply', False))
            if not orphans:
                print("No orphan worktree directories found.")
                return 0
            label = "Removed" if getattr(args, 'apply', False) else "Orphan"
            for p in orphans:
                print(f"  {label}: {p}")
            if not getattr(args, 'apply', False):
                print(f"\n{len(orphans)} orphan(s) found. Run with --apply to remove.")
            return 0
        if worktree_cmd == "list":
            from atdd.coach.commands.branch import BranchManager
            return BranchManager().list_worktrees()
        if worktree_cmd == "remove":
            from atdd.coach.commands.branch import BranchManager
            return BranchManager().remove_worktree(args.target)
        worktree_parser.print_help()
        return 1

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

    # atdd hooks
    elif args.command == "hooks":
        from atdd.coach.commands.hooks import run_hooks_list, run_hooks_path
        if args.hooks_command == "path":
            return run_hooks_path(args.name)
        if args.hooks_command == "list":
            return run_hooks_list()
        print("Usage: atdd hooks {path <name>|list}")
        return 1

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

    # atdd coach <issue-numbers...> / atdd coach status ... (J1 — #496 / L001 — #616)
    elif args.command == "coach":
        from atdd.coach.commands.coach import run_cli as run_coach_cli
        return run_coach_cli(list(getattr(args, "coach_argv", []) or []))

    # atdd resume <run_id> (Child 9 — #896)
    elif args.command == "resume":
        from atdd.train.resume_cli import run_args as run_resume
        return run_resume(
            run_id=args.run_id,
            repo_root=getattr(args, "resume_repo_root", None),
        )

    # atdd author ... (author-atdd-substrate wagon — #1097)
    elif args.command == "author":
        from atdd.planner.commands.author import run as run_author
        return run_author(list(getattr(args, "author_argv", []) or []))

    # atdd state <doctor|layout|init|import-manifest|sync> ...  (#1168)
    elif args.command == "state":
        state_argv = list(getattr(args, "state_argv", []) or [])
        # `state sync` is provider-agnostic (#1364): it drives registered providers
        # via the atdd.state seam and imports NO provider (no GitHub). Provider-
        # specific syncing lives in an extension that plugs into the registry.
        if state_argv and state_argv[0] == "sync":
            from atdd.state.sync_cli import run_sync_cli
            return run_sync_cli(state_argv[1:])
        from atdd.state.cli import run as run_state
        return run_state(state_argv)

    # NOTE: `atdd plan ...` is intercepted before parse_args (see above) and
    # routed to the gated decomposition session — there is no `command == "plan"`
    # branch here. The legacy PLAN-1 brief renderer was decommissioned in #1208.

    # NOTE: `atdd enforce ...` is intercepted before parse_args (see above) and
    # routed to atdd.enforce.cli — there is no `command == "enforce"` branch here
    # (its leading-dash flags cannot ride argparse REMAINDER).

    # NOTE (#1486): `atdd judge` was the coach's structured-output routing boundary
    # for sub-worker decisions — orchestration, so it left core with the rest. Its
    # generic LLM plumbing (registry/protocol) was rehomed to
    # `atdd.coach.commands.llm_clients.registry`, which `atdd coach issue-review`
    # still uses (it imports llm_clients for the side-effect registration itself).

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

    elif args.command == "doctor":
        from atdd.doctor import run_doctor
        return run_doctor()

    elif args.command == "cleanup":
        from atdd.coach.commands.cleanup import run_cleanup
        return run_cleanup(apply=getattr(args, "yes", False))

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
            if args.format == "launch-prompt":
                from atdd.coach.commands.issue_graph import build_wagon_launch_prompt

                wagon_slug = getattr(args, "wagon", None)
                if not wagon_slug:
                    print(
                        "error: --format launch-prompt requires --wagon <slug>",
                        file=sys.stderr,
                    )
                    return 2
                section = build_wagon_launch_prompt(wagon_slug, repo_root=repo_path)
                if section is None:
                    print(
                        f"error: wagon '{wagon_slug}' not found in plan/ directory",
                        file=sys.stderr,
                    )
                    return 1
                print(section, end="")
                return 0
            if args.format == "prompt":
                from atdd.coach.commands.issue_graph import build_issue_architecture_context

                issue_num = getattr(args, "issue", None)
                if issue_num is None:
                    print(
                        "error: --format prompt requires --issue <N>",
                        file=sys.stderr,
                    )
                    return 2
                section = build_issue_architecture_context(issue_num, repo_root=repo_path)
                if section is None:
                    print(
                        f"error: issue {issue_num} has no wagon assigned in .atdd/manifest.yaml",
                        file=sys.stderr,
                    )
                    return 1
                print(section, end="")
                return 0
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

    elif args.command == "emergency":
        from atdd.coach.commands.emergency import run_cli as emergency_run_cli

        return emergency_run_cli(sys.argv[2:])

    elif args.command == "suppress":
        from atdd.coach.commands.suppress import run_suppress_backfill
        from atdd.coach.utils.repo import find_repo_root

        repo_path = Path(args.repo) if args.repo else find_repo_root()
        if getattr(args, "suppress_command", None) == "backfill":
            return run_suppress_backfill(
                rule_id=args.rule,
                until=args.until,
                repo_root=repo_path,
                dry_run=getattr(args, "dry_run", False),
            )
        suppress_parser.print_help()
        return 0

    elif args.command == "manifest":
        manifest_command = getattr(args, "manifest_command", None)
        if manifest_command == "backfill":
            repo_root = Path(args.repo) if args.repo else find_repo_root()
            manager = IssueManager(repo_root)
            return manager.reconcile()
        manifest_parser.print_help()
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
        )

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
    # #917: self-heal a worktree falsely marked core.bare=true BEFORE doing any
    # work. A stray unscoped `git config core.bare true` (SMOKE test in the
    # wrong cwd, crashed run, xdist worker) bleeds into the shared .git/config
    # and the next `git add -A` mass-deletes the working tree. Reset it here so
    # no atdd command operates on a poisoned config. Never fatal.
    try:
        from atdd.coach.utils.repo import ensure_repo_not_falsely_bare
        ensure_repo_not_falsely_bare()
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
        pass

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
