"""
Baseline CLI Command
====================
Provides ``atdd baseline update`` and ``atdd baseline show`` for managing
ratchet baselines used by coder and tester validators.

Baseline files:
- ``.atdd/baselines/coder.yaml`` — coder validators
- ``.atdd/baselines/tester.yaml`` — tester validators

Usage::

    atdd baseline update              # Record current violation counts
    atdd baseline update --dry-run    # Show what would be written
    atdd baseline show                # Compare baseline vs current
    atdd baseline show --verbose      # Include per-validator detail
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from atdd.coach.utils.repo import find_repo_root
from atdd.coder.baselines.ratchet import RatchetBaseline, default_baseline_path
from atdd.tester.validators.conftest import tester_baseline_path


# ---------------------------------------------------------------------------
# Validator registry
# ---------------------------------------------------------------------------
# Each entry maps a validator_id to a callable that accepts (repo_root) and
# returns (violation_count, violations_list).  Validators register here when
# they are retrofitted to the ratchet pattern (Phase 3).
#
# Import paths are deferred (inside the callable) to avoid import-time
# failures when the target repo has no Python/TS tree to scan.
# ---------------------------------------------------------------------------

ValidatorFn = Callable[[Path], Tuple[int, Sequence]]


def _composition_python(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_python_repo,
    )
    violations = analyze_python_repo(repo_root)
    return len(violations), violations


def _composition_typescript(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_typescript_repo,
    )
    violations = analyze_typescript_repo(repo_root)
    return len(violations), violations


def _composition_supabase(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_composition_completeness import (
        analyze_typescript_repo,
    )
    violations = analyze_typescript_repo(repo_root, stack="supabase")
    return len(violations), violations


def _dead_code_python(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_dead_code_python import (
        find_python_files,
        build_file_import_graph,
        find_reachable_files,
        find_cli_entry_points,
        resolve_module_to_file,
        is_root_file,
        build_reverse_graph,
    )
    python_files = find_python_files()
    if not python_files:
        return 0, []
    graph = build_file_import_graph(python_files)
    roots = {f for f in python_files if is_root_file(f)}
    cli_modules = find_cli_entry_points()
    all_files_set = set(python_files)
    for module in cli_modules:
        roots.update(resolve_module_to_file(module, all_files_set))
    # Composition roots mark wagon src/ as reachable
    for f in list(roots):
        if f.name == "composition.py":
            src_dir = f.parent / "src"
            if src_dir.is_dir():
                roots.update(pf for pf in python_files if str(pf).startswith(str(src_dir)))
    reachable = find_reachable_files(roots, graph)
    reverse_reachable = find_reachable_files(roots, build_reverse_graph(graph))
    all_reachable = reachable | reverse_reachable
    unreachable = [
        str(f.relative_to(repo_root))
        for f in python_files
        if f not in all_reachable and f.name != "__init__.py"
    ]
    return len(unreachable), unreachable


def _maintainability_index(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        calculate_maintainability_index,
        MIN_MAINTAINABILITY_INDEX,
        REPO_ROOT,
    )
    violations = []
    for py_file in find_python_files():
        try:
            with open(py_file, 'r') as f:
                if len(f.readlines()) < 10:
                    continue
        except Exception:
            continue
        index = calculate_maintainability_index(py_file)
        if index < MIN_MAINTAINABILITY_INDEX:
            violations.append(f"{py_file.relative_to(REPO_ROOT)} MI={index:.1f}")
    return len(violations), violations


def _code_comments(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_quality_metrics import (
        find_python_files,
        calculate_comment_ratio,
        MIN_COMMENT_RATIO,
        REPO_ROOT,
    )
    violations = []
    for py_file in find_python_files():
        try:
            with open(py_file, 'r') as f:
                if len(f.readlines()) < 20:
                    continue
        except Exception:
            continue
        ratio = calculate_comment_ratio(py_file)
        if ratio < MIN_COMMENT_RATIO:
            violations.append(f"{py_file.relative_to(REPO_ROOT)} {ratio*100:.1f}%")
    return len(violations), violations


def _contract_driven_http(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.coder.validators.test_contract_driven_http import (
        analyze_contract_driven_http,
    )
    return analyze_contract_driven_http(repo_root)


VALIDATORS: Dict[str, ValidatorFn] = {
    "composition_completeness_python": _composition_python,
    "composition_completeness_typescript": _composition_typescript,
    "composition_completeness_supabase": _composition_supabase,
    "contract_driven_http": _contract_driven_http,
    "dead_code_python": _dead_code_python,
    "maintainability_index": _maintainability_index,
    "code_comments": _code_comments,
}


# ---------------------------------------------------------------------------
# Tester validator registry
# ---------------------------------------------------------------------------


def _smoke_coverage_gaps(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_smoke_coverage import (
        CoverageAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    analyzer = CoverageAnalyzer(e2e_dir)
    trains, gaps, _, _ = analyzer.analyze()
    violations = [
        f"{g.train_id}: {len(g.contract_tests)} contract test(s), 0 smoke tests"
        for g in gaps
    ]
    return len(violations), violations


def _train_e2e_existence(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_train_e2e_existence import (
        E2EExistenceAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    trains_file = repo_root / "plan" / "_trains.yaml"
    analyzer = E2EExistenceAnalyzer(e2e_dir, trains_file)
    statuses = analyzer.analyze()
    violations = [
        f"{s.train_id}: no E2E tests in e2e/{s.train_id}/"
        for s in statuses
        if not s.has_tests
    ]
    return len(violations), violations


def _train_completeness(repo_root: Path) -> Tuple[int, Sequence]:
    from atdd.tester.validators.test_train_completeness import (
        CompletenessAnalyzer,
    )
    e2e_dir = repo_root / "e2e"
    trains_file = repo_root / "plan" / "_trains.yaml"
    analyzer = CompletenessAnalyzer(e2e_dir, trains_file)
    statuses = analyzer.analyze()
    incomplete = [s for s in statuses if not s.complete]
    violations = [
        f"{s.train_id}: {s.status_label} "
        f"(e2e={s.e2e_count}, contract={s.contract_count}, smoke={s.smoke_count})"
        for s in incomplete
    ]
    return len(violations), violations


TESTER_VALIDATORS: Dict[str, ValidatorFn] = {
    "smoke_coverage_gaps": _smoke_coverage_gaps,
    "train_e2e_existence": _train_e2e_existence,
    "train_completeness": _train_completeness,
}


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class BaselineCommand:
    """CLI command handler for ``atdd baseline {update,show}``."""

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.baseline = RatchetBaseline(
            default_baseline_path(self.repo_root),
        )
        self.tester_baseline = RatchetBaseline(
            tester_baseline_path(self.repo_root),
        )

    # ---------------------------------------------------------------
    # atdd baseline update
    # ---------------------------------------------------------------

    def _run_validators(
        self,
        validators: Dict[str, ValidatorFn],
        label: str,
        verbose: bool = False,
    ) -> Tuple[Dict[str, int], List[str]]:
        """Run a set of validators and return results + errors."""
        results: Dict[str, int] = {}
        errors: List[str] = []

        print(f"  [{label}]")
        for vid, fn in sorted(validators.items()):
            try:
                count, violations = fn(self.repo_root)
                results[vid] = count
                symbol = "✓" if count == 0 else f"▸ {count}"
                print(f"    {vid}: {symbol}")
                if verbose and violations:
                    for v in violations[:5]:
                        print(f"        {v}")
                    if len(violations) > 5:
                        print(f"        ... and {len(violations) - 5} more")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"    {vid}: ERROR — {exc}")
                print(f"    {vid}: ERROR — {exc}")

        return results, errors

    def update(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> int:
        """Run all registered validators and write current counts."""
        print(f"Scanning {self.repo_root} ...\n")

        coder_results, coder_errors = self._run_validators(
            VALIDATORS, "coder", verbose,
        )
        tester_results, tester_errors = self._run_validators(
            TESTER_VALIDATORS, "tester", verbose,
        )

        errors = coder_errors + tester_errors
        print()

        if errors:
            print("Errors encountered (baselines NOT updated):")
            for e in errors:
                print(e)
            return 1

        if dry_run:
            print("Dry-run — would write:\n")
            for vid, count in sorted(coder_results.items()):
                print(f"  {vid}: {count}")
            print(f"  To: {self.baseline.path}\n")
            for vid, count in sorted(tester_results.items()):
                print(f"  {vid}: {count}")
            print(f"  To: {self.tester_baseline.path}")
            return 0

        self.baseline.update(coder_results)
        print(f"Coder baseline written to {self.baseline.path}")
        self.tester_baseline.update(tester_results)
        print(f"Tester baseline written to {self.tester_baseline.path}")
        return 0

    # ---------------------------------------------------------------
    # atdd baseline show
    # ---------------------------------------------------------------

    def _show_scope(
        self,
        baseline: RatchetBaseline,
        validators: Dict[str, ValidatorFn],
        label: str,
    ) -> List[str]:
        """Show baseline vs current for one scope. Returns errors."""
        errors: List[str] = []
        results: Dict[str, int] = {}

        for vid, fn in sorted(validators.items()):
            try:
                count, _ = fn(self.repo_root)
                results[vid] = count
            except Exception as exc:  # noqa: BLE001
                errors.append(f"  {vid}: ERROR — {exc}")

        if not baseline.exists and not results:
            return errors

        rows = baseline.show(results)

        fmt = "{:<45} {:>10} {:>10} {:>8}  {}"
        print(f"\n[{label}] {baseline.path}")
        print(fmt.format("Validator", "Baseline", "Current", "Delta", "Status"))
        print("-" * 90)

        for row in rows:
            delta_str = f"{row['delta']:+d}" if row["delta"] != 0 else "0"
            print(
                fmt.format(
                    row["validator"],
                    row["baseline"],
                    row["current"],
                    delta_str,
                    row["status"],
                )
            )

        return errors

    def show(self, verbose: bool = False) -> int:
        """Display baseline vs current violation counts."""
        if not self.baseline.exists and not self.tester_baseline.exists:
            print(
                f"No baseline files found.\n\n"
                f"Run `atdd baseline update` to create them."
            )
            return 0

        print(f"Scanning {self.repo_root} ...")

        errors = self._show_scope(self.baseline, VALIDATORS, "coder")
        errors += self._show_scope(
            self.tester_baseline, TESTER_VALIDATORS, "tester",
        )

        if errors:
            print(f"\nErrors ({len(errors)}):")
            for e in errors:
                print(e)

        return 0
