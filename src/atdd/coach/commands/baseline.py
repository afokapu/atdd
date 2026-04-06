"""
Baseline CLI Command
====================
Provides ``atdd baseline update`` and ``atdd baseline show`` for managing
ratchet baselines used by coder validators.

Baseline file: ``.atdd/baselines/coder.yaml`` in the TARGET repo.

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


VALIDATORS: Dict[str, ValidatorFn] = {
    "composition_completeness_python": _composition_python,
    "composition_completeness_typescript": _composition_typescript,
    "composition_completeness_supabase": _composition_supabase,
    "dead_code_python": _dead_code_python,
    "maintainability_index": _maintainability_index,
    "code_comments": _code_comments,
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

    # ---------------------------------------------------------------
    # atdd baseline update
    # ---------------------------------------------------------------

    def update(
        self,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> int:
        """Run all registered validators and write current counts."""
        results: Dict[str, int] = {}
        errors: List[str] = []

        print(f"Scanning {self.repo_root} ...\n")

        for vid, fn in sorted(VALIDATORS.items()):
            try:
                count, violations = fn(self.repo_root)
                results[vid] = count
                symbol = "✓" if count == 0 else f"▸ {count}"
                print(f"  {vid}: {symbol}")
                if verbose and violations:
                    for v in violations[:5]:
                        print(f"      {v}")
                    if len(violations) > 5:
                        print(f"      ... and {len(violations) - 5} more")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"  {vid}: ERROR — {exc}")
                print(f"  {vid}: ERROR — {exc}")

        print()

        if errors:
            print("Errors encountered (baselines NOT updated):")
            for e in errors:
                print(e)
            return 1

        if dry_run:
            print("Dry-run — would write:\n")
            for vid, count in sorted(results.items()):
                print(f"  {vid}: {count}")
            print(f"\nTo: {self.baseline.path}")
            return 0

        self.baseline.update(results)
        print(f"Baseline written to {self.baseline.path}")
        return 0

    # ---------------------------------------------------------------
    # atdd baseline show
    # ---------------------------------------------------------------

    def show(self, verbose: bool = False) -> int:
        """Display baseline vs current violation counts."""
        if not self.baseline.exists:
            print(
                f"No baseline file found at {self.baseline.path}\n\n"
                f"Run `atdd baseline update` to create one."
            )
            return 0

        results: Dict[str, int] = {}
        errors: List[str] = []

        print(f"Scanning {self.repo_root} ...\n")

        for vid, fn in sorted(VALIDATORS.items()):
            try:
                count, _ = fn(self.repo_root)
                results[vid] = count
            except Exception as exc:  # noqa: BLE001
                errors.append(f"  {vid}: ERROR — {exc}")

        rows = self.baseline.show(results)

        # Header
        fmt = "{:<45} {:>10} {:>10} {:>8}  {}"
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

        if errors:
            print(f"\nErrors ({len(errors)}):")
            for e in errors:
                print(e)

        return 0
