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


VALIDATORS: Dict[str, ValidatorFn] = {
    "composition_completeness_python": _composition_python,
    "composition_completeness_typescript": _composition_typescript,
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
