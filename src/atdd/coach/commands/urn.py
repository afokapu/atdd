"""
URN Traceability CLI Command
============================
Provides CLI interface for URN traceability analysis.

Commands:
- graph: Generate URN traceability graph (JSON/DOT)
- orphans: Find orphaned URNs
- broken: Find broken URN references
- validate: Run full validation suite

Usage:
    atdd repo graph --format json
    atdd repo graph --format dot --root wagon:my-wagon
    atdd repo orphans
    atdd repo broken
    atdd repo validate --phase warn
    atdd repo validate --phase fail
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.graph.resolver import ResolverRegistry
from atdd.coach.utils.graph.graph_builder import (
    EdgeType,
    GraphBuilder,
    TraceabilityGraph,
)
from atdd.coach.utils.graph.edge_validator import (
    EdgeValidator,
    ValidationResult,
    IssueSeverity,
    IssueType,
)


def _default_edge_type_exclude(root_urn: Optional[str]) -> Optional[set]:
    """
    Return the default ``edge_type_exclude`` for a subgraph rooted at ``root_urn``.

    Train roots opt into journey semantics (TRAIN_STEP visible). Every other
    root family is treated as structural and hides TRAIN_STEP so wagon/feature
    subgraphs don't leak cross-train wagons via shared handoffs (#287).
    """
    if root_urn and root_urn.startswith("train:"):
        return None
    return {EdgeType.TRAIN_STEP}


class URNCommand:
    """
    CLI command handler for URN traceability operations.

    Provides subcommands for graph generation, orphan detection,
    broken reference detection, and full validation.
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or find_repo_root()
        self.registry = ResolverRegistry(self.repo_root)
        self.graph_builder = GraphBuilder(self.repo_root)
        self._built_graph = self.graph_builder.build()
        self.validator = EdgeValidator(self._built_graph)

    def graph(
        self,
        format: str = "json",
        root: Optional[str] = None,
        families: Optional[List[str]] = None,
        max_depth: int = -1,
        full: bool = False,
    ) -> int:
        """
        Generate URN traceability graph.

        Args:
            format: Output format - "json" or "dot"
            root: Optional root URN for subgraph
            families: Optional list of families to include
            max_depth: Maximum depth for subgraph (-1 for unlimited)
            full: If True, output full raw nodes+edges; default is agent-optimized summary

        Returns:
            Exit code (0 for success)
        """
        try:
            if root:
                graph = self.graph_builder.build_from_root(
                    root,
                    max_depth,
                    families,
                    edge_type_exclude=_default_edge_type_exclude(root),
                )
            else:
                graph = self.graph_builder.build(families)

            if format == "dot":
                output = graph.to_dot()
            elif full:
                output = graph.to_json()
            else:
                output = json.dumps(graph.to_agent_summary(), indent=2)

            print(output)
            return 0

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error generating graph: {e}", file=sys.stderr)
            return 1

    def viz(
        self,
        port: int = 8502,
        host: str = "127.0.0.1",
        root: Optional[str] = None,
        families: Optional[List[str]] = None,
        max_depth: int = -1,
    ) -> int:
        """
        Launch Streamlit URN graph visualizer.

        Args:
            port: Server port (default: 8502)
            host: Server address (default: 127.0.0.1)
            root: Optional root URN for subgraph
            families: Optional list of families to include
            max_depth: Maximum depth for subgraph (-1 for unlimited)

        Returns:
            Exit code (0 for success)
        """
        try:
            import streamlit  # noqa: F401
        except ImportError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(
                "Error: Streamlit is not installed.\n"
                "Install the viz extra: pip install atdd[viz]",
                file=sys.stderr,
            )
            return 1

        try:
            import st_link_analysis  # noqa: F401
        except ImportError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(
                "Error: st-link-analysis is not installed.\n"
                "Install the viz extra: pip install atdd[viz]",
                file=sys.stderr,
            )
            return 1

        app_path = Path(__file__).parent / "viz_app.py"

        env = os.environ.copy()
        env["ATDD_VIZ_REPO"] = str(self.repo_root)
        if root:
            env["ATDD_VIZ_ROOT"] = root
        env["ATDD_VIZ_DEPTH"] = str(max_depth)
        if families:
            env["ATDD_VIZ_FAMILIES"] = ",".join(families)

        cmd = [
            sys.executable, "-m", "streamlit", "run",
            str(app_path),
            "--server.port", str(port),
            "--server.address", host,
            "--server.headless", "true",
        ]

        print(f"Launching URN graph visualizer on http://{host}:{port}")
        try:
            return subprocess.call(cmd, env=env)
        except KeyboardInterrupt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            return 0

    def orphans(
        self,
        families: Optional[List[str]] = None,
        format: str = "text",
    ) -> int:
        """
        Find orphaned URNs (declared but not referenced).

        Args:
            families: Optional list of families to check
            format: Output format - "text" or "json"

        Returns:
            Exit code (0 if no orphans, 1 if orphans found)
        """
        try:
            issues = self.validator.find_orphans(families)

            if format == "json":
                output = {
                    "orphan_count": len(issues),
                    "orphans": [i.to_dict() for i in issues],
                }
                print(json.dumps(output, indent=2))
            else:
                if not issues:
                    print("No orphaned URNs found.")
                else:
                    print(f"Found {len(issues)} orphaned URN(s):\n")
                    for issue in issues:
                        self._print_issue(issue)

            return 1 if issues else 0

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error finding orphans: {e}", file=sys.stderr)
            return 1

    def broken(
        self,
        families: Optional[List[str]] = None,
        format: str = "text",
    ) -> int:
        """
        Find broken URN references.

        Args:
            families: Optional list of families to check
            format: Output format - "text" or "json"

        Returns:
            Exit code (0 if no broken refs, 1 if broken refs found)
        """
        try:
            issues = self.validator.find_broken(families)

            if format == "json":
                output = {
                    "broken_count": len(issues),
                    "broken": [i.to_dict() for i in issues],
                }
                print(json.dumps(output, indent=2))
            else:
                if not issues:
                    print("No broken URN references found.")
                else:
                    print(f"Found {len(issues)} broken URN reference(s):\n")
                    for issue in issues:
                        self._print_issue(issue)

            return 1 if issues else 0

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error finding broken refs: {e}", file=sys.stderr)
            return 1

    def validate(
        self,
        phase: str = "warn",
        families: Optional[List[str]] = None,
        format: str = "text",
        strict: bool = False,
        fix: bool = False,
        dry_run: bool = False,
    ) -> int:
        """
        Run full URN traceability validation.

        Args:
            phase: Validation phase - "warn" or "fail"
            families: Optional list of families to check
            format: Output format - "text" or "json"
            strict: If True, warnings also cause failure
            fix: If True, auto-fix urn:jel:* contract IDs
            dry_run: If True, show what --fix would change without modifying

        Returns:
            Exit code (0 for pass, 1 for failure)
        """
        try:
            # Handle --fix or --dry-run for JEL contracts
            if fix or dry_run:
                return self._fix_jel_contracts(dry_run=dry_run, format=format)

            result = self.validator.validate_all(families, phase)

            if format == "json":
                print(json.dumps(result.to_dict(), indent=2))
            else:
                self._print_validation_result(result)

            # Substrate Track-B conformance suite (#410, spec §11 step 2):
            # `atdd repo validate` (renamed from the legacy `urn validate`
            # per #414) MUST also surface Class-1 substrate-conformance findings so
            # day-1 backlog appears on the same CLI surface as URN-graph
            # findings. The conformance tests live under
            # ``src/atdd/tester/validators/test_acceptance_*.py`` +
            # ``test_metric_implementation.py`` +
            # ``test_repo_validator_binding.py``; pytest is the gate so the
            # rule_id-keyed Violation records and disposition gate apply.
            substrate_rc = self._run_substrate_conformance(format=format)

            # Determine exit code: combine URN-graph + substrate.
            urn_rc: int
            if strict:
                urn_rc = 1 if result.issues else 0
            else:
                urn_rc = 1 if result.has_errors else 0

            return 1 if (urn_rc or substrate_rc) else 0

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error running validation: {e}", file=sys.stderr)
            return 1

    def _run_substrate_conformance(self, format: str = "text") -> int:
        """Invoke the substrate Track-B conformance pytest suite.

        Returns 0 on pass, 1 on any failing conformance rule. The
        ``ATDD_ALLOW_SUBSTRATE_BACKLOG`` env var (set by the toolkit's
        own CI during the migration window) demotes findings to warnings
        — see ``_acceptance_walker.assert_substrate_strict``.
        """
        import atdd as _atdd_pkg

        pkg_dir = Path(_atdd_pkg.__file__).resolve().parent
        validators_dir = pkg_dir / "tester" / "validators"
        targets = [
            str(validators_dir / "test_acceptance_measurable.py"),
            str(validators_dir / "test_acceptance_phase.py"),
            str(validators_dir / "test_acceptance_disposition.py"),
            str(validators_dir / "test_repo_validator_binding.py"),
            str(validators_dir / "test_metric_implementation.py"),
        ]
        existing = [t for t in targets if Path(t).is_file()]
        if not existing:
            return 0

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *existing,
            "-q",
            "--tb=short",
            "--no-header",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except (OSError, FileNotFoundError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            # The handler is observable: it prints the exception to stderr
            # before returning the failure exit code, satisfying the
            # "log, re-raise, or otherwise observably react" rule. The
            # suppress marker is here because the validator's AST scan
            # only sees the bare ``return``.
            if format != "json":
                print(
                    f"\n[substrate] could not invoke conformance suite: {exc}",
                    file=sys.stderr,
                )
            return 1

        if format == "json":
            payload = {
                "substrate_conformance": {
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
            }
            print(json.dumps(payload, indent=2))
        else:
            sep = "\n--- Substrate Track-B conformance (spec §7.3) ---"
            print(sep)
            if proc.returncode == 0:
                print("[substrate] conformance: PASS")
            else:
                if proc.stdout:
                    print(proc.stdout)
                if proc.stderr:
                    print(proc.stderr, file=sys.stderr)
                print("[substrate] conformance: FAIL")

        return proc.returncode

    def _fix_jel_contracts(self, dry_run: bool = False, format: str = "text") -> int:
        """
        Fix urn:jel:* contract IDs.

        Args:
            dry_run: If True, only show what would be fixed
            format: Output format - "text" or "json"

        Returns:
            Exit code (0 if fixes applied, 1 if errors)
        """
        fixes = self.validator.fix_jel_contracts(dry_run=dry_run)

        if format == "json":
            print(json.dumps({"fixes": fixes, "dry_run": dry_run}, indent=2))
        else:
            if not fixes:
                print("No urn:jel:* contract IDs found.")
                return 0

            mode = "Would fix" if dry_run else "Fixed"
            print(f"{mode} {len(fixes)} contract(s):\n")

            for fix in fixes:
                status_icon = {
                    "fixed": "✅",
                    "dry_run": "🔍",
                    "error": "❌",
                    "pending": "⏳",
                }.get(fix["status"], "  ")

                print(f"{status_icon} {fix['file_path']}")
                print(f"   Old: {fix['old_id']}")
                print(f"   New: {fix['new_id']}")
                if fix.get("backup"):
                    print(f"   Backup: {fix['backup']}")
                if fix.get("error"):
                    print(f"   Error: {fix['error']}")
                print()

        # Return 0 if all successful, 1 if any errors
        has_errors = any(f["status"] == "error" for f in fixes)
        return 1 if has_errors else 0

    def resolve(self, urn: str, format: str = "text") -> int:
        """
        Resolve a single URN to its artifact(s).

        Args:
            urn: The URN to resolve
            format: Output format - "text" or "json"

        Returns:
            Exit code (0 if resolved, 1 if not)
        """
        try:
            resolution = self.registry.resolve(urn)

            if format == "json":
                output = {
                    "urn": resolution.urn,
                    "family": resolution.family,
                    "resolved": resolution.is_resolved,
                    "deterministic": resolution.is_deterministic,
                    "paths": [str(p) for p in resolution.resolved_paths],
                    "error": resolution.error,
                }
                print(json.dumps(output, indent=2))
            else:
                if resolution.is_resolved:
                    print(f"URN: {resolution.urn}")
                    print(f"Family: {resolution.family}")
                    print(f"Deterministic: {resolution.is_deterministic}")
                    print(f"Resolved to:")
                    for path in resolution.resolved_paths:
                        print(f"  - {path}")
                else:
                    print(f"URN: {resolution.urn}")
                    print(f"Family: {resolution.family}")
                    print(f"Error: {resolution.error}")

            return 0 if resolution.is_resolved else 1

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error resolving URN: {e}", file=sys.stderr)
            return 1

    def list_families(self) -> int:
        """
        List all registered URN families.

        Returns:
            Exit code (always 0)
        """
        print("Registered URN families:")
        for family in sorted(self.registry.families):
            print(f"  - {family}")
        return 0

    def declarations(
        self,
        families: Optional[List[str]] = None,
        format: str = "text",
    ) -> int:
        """
        List all URN declarations in the codebase.

        Args:
            families: Optional list of families to include
            format: Output format - "text" or "json"

        Returns:
            Exit code (always 0)
        """
        try:
            declarations = self.registry.find_all_declarations(families)

            if format == "json":
                output = {}
                for family, decls in declarations.items():
                    output[family] = [
                        {
                            "urn": d.urn,
                            "source_path": str(d.source_path),
                            "line_number": d.line_number,
                            "context": d.context,
                        }
                        for d in decls
                    ]
                print(json.dumps(output, indent=2))
            else:
                total = 0
                for family, decls in sorted(declarations.items()):
                    if decls:
                        print(f"\n{family.upper()} ({len(decls)}):")
                        for d in decls:
                            line_info = f":{d.line_number}" if d.line_number else ""
                            print(f"  {d.urn}")
                            print(f"    └─ {d.source_path}{line_info}")
                        total += len(decls)

                print(f"\nTotal: {total} declarations")

            return 0

        except Exception as e:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error listing declarations: {e}", file=sys.stderr)
            return 1

    def _print_issue(self, issue) -> None:
        """Print a single validation issue."""
        severity_icons = {
            IssueSeverity.ERROR: "❌",
            IssueSeverity.WARNING: "⚠️ ",
            IssueSeverity.INFO: "ℹ️ ",
        }

        icon = severity_icons.get(issue.severity, "  ")
        print(f"{icon} {issue.urn}")
        print(f"   {issue.message}")
        if issue.location:
            print(f"   Location: {issue.location}")
        if issue.context:
            print(f"   Context: {issue.context}")
        if issue.suggestion:
            print(f"   Suggestion: {issue.suggestion}")
        print()

    def _print_validation_result(self, result: ValidationResult) -> None:
        """Print validation result summary."""
        print("=" * 60)
        print("URN Traceability Validation Report")
        print("=" * 60)
        print()

        print(f"Checked URNs: {result.checked_urns}")
        print(f"Families: {', '.join(result.families_checked)}")
        print()

        if result.is_valid and not result.has_warnings:
            print("✅ All checks passed!")
            return

        # Group issues by type
        by_type = {}
        for issue in result.issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)

        # Print summary
        print("Summary:")
        print(f"  Errors: {result.error_count}")
        print(f"  Warnings: {result.warning_count}")
        print()

        # Print issues by type
        type_labels = {
            IssueType.ORPHAN: "Orphaned URNs",
            IssueType.BROKEN: "Broken References",
            IssueType.NON_DETERMINISTIC: "Non-Deterministic URNs",
            IssueType.MISSING_EDGE: "Missing Edges",
            IssueType.CYCLE: "Cycles Detected",
            IssueType.INVALID_FORMAT: "Invalid URN Format",
            IssueType.JEL_CONTRACT: "JEL Contract IDs (use --fix to remediate)",
        }

        for issue_type, issues in by_type.items():
            label = type_labels.get(issue_type, issue_type.value)
            print(f"\n{label} ({len(issues)}):")
            print("-" * 40)
            for issue in issues:
                self._print_issue(issue)

        # Final status
        print()
        if result.has_errors:
            print("❌ Validation FAILED")
        else:
            print("⚠️  Validation passed with warnings")
