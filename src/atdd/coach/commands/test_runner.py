#!/usr/bin/env python3
"""
Validator runner for ATDD.

Executes validators from the installed atdd package against the current
consumer repository. Validators are discovered from the package's
planner/tester/coder/coach validator directories.

Usage:
    atdd validate                # Run all validators
    atdd validate planner        # Run planner validators only
    atdd validate --quick        # Quick smoke test
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import atdd
from atdd.coach.utils.repo import find_repo_root


def _xdist_available() -> bool:
    """Check if pytest-xdist is installed."""
    try:
        import xdist  # noqa: F401
        return True
    except ImportError:
        return False


class TestRunner:
    """Run ATDD validators with various configurations."""

    def __init__(self, repo_root: Path = None):
        self.repo_root = repo_root or find_repo_root()
        # Point to the installed atdd package validators, not a local atdd/ dir
        self.atdd_pkg_dir = Path(atdd.__file__).resolve().parent

    def run_tests(
        self,
        phase: Optional[str] = None,
        verbose: bool = False,
        coverage: bool = False,
        html_report: bool = False,
        markers: Optional[List[str]] = None,
        parallel: bool = True,
    ) -> int:
        """
        Run ATDD validators with specified options.

        Args:
            phase: Validator phase to run (planner, tester, coder, coach, all, None=all)
            verbose: Enable verbose output
            coverage: Generate coverage report
            html_report: Generate HTML report
            markers: Additional pytest markers to filter
            parallel: Run validators in parallel (uses pytest-xdist if available)

        Returns:
            Exit code from pytest
        """
        # Build pytest command
        cmd = ["pytest"]

        # Determine test path from installed package
        if phase and phase != "all":
            test_path = self.atdd_pkg_dir / phase / "validators"
            if not test_path.exists():
                print(f"❌ Error: Test phase '{phase}' not found at {test_path}")
                return 1
            cmd.append(str(test_path))
        else:
            # Run all validator tests from the package
            # Include validators from all phases
            validator_dirs = []
            for subdir in ["planner", "tester", "coder", "coach"]:
                validators_path = self.atdd_pkg_dir / subdir / "validators"
                if validators_path.exists():
                    validator_dirs.append(str(validators_path))
            if not validator_dirs:
                print("❌ Error: No validator directories found in atdd package")
                return 1
            cmd.extend(validator_dirs)

        # Add verbosity
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")

        # Add markers
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        # Add coverage (coverage reports go to consumer repo's .atdd/ dir)
        if coverage:
            htmlcov_path = self.repo_root / ".atdd" / "htmlcov"
            cmd.extend([
                "--cov=atdd",
                "--cov-report=term-missing",
                f"--cov-report=html:{htmlcov_path}"
            ])

        # Add HTML report (reports go to consumer repo's .atdd/ dir)
        if html_report:
            report_path = self.repo_root / ".atdd" / "test_report.html"
            cmd.extend([
                f"--html={report_path}",
                "--self-contained-html"
            ])

        # Add parallel execution (only if pytest-xdist is available)
        if parallel and _xdist_available():
            cmd.extend(["-n", "auto"])
        elif parallel and not _xdist_available():
            print("⚠️  pytest-xdist not installed, running validators sequentially")

        # Show collected tests summary
        cmd.append("--tb=short")

        # Set up environment with repo root for validators
        import os
        env = os.environ.copy()
        env["ATDD_REPO_ROOT"] = str(self.repo_root)

        # Run pytest with consumer repo as cwd
        print(f"🧪 Running: {' '.join(cmd)}")
        print(f"📁 Repo root: {self.repo_root}")
        print("=" * 60)

        result = subprocess.run(cmd, env=env, cwd=str(self.repo_root))
        return result.returncode

    def run_phase(self, phase: str, **kwargs) -> int:
        """Run validators for a specific phase."""
        return self.run_tests(phase=phase, **kwargs)

    def run_all(self, **kwargs) -> int:
        """Run all ATDD validators."""
        return self.run_tests(phase="all", **kwargs)

    def quick_check(self) -> int:
        """Quick smoke validation - run without parallelization."""
        print("🚀 Running quick validation (no parallel)...")
        return self.run_tests(
            phase="all",
            verbose=False,
            parallel=False,
            html_report=False
        )

    def full_suite(self) -> int:
        """Full validation suite with coverage and HTML report."""
        print("🎯 Running full validation suite...")
        return self.run_tests(
            phase="all",
            verbose=True,
            coverage=True,
            html_report=True,
            parallel=True
        )


def main():
    """CLI entry point for validator runner."""
    runner = TestRunner()

    # Simple usage for now - can be enhanced with argparse
    if len(sys.argv) > 1:
        phase = sys.argv[1]
        return runner.run_phase(phase, verbose=True, html_report=True)
    else:
        return runner.run_all(verbose=True, html_report=True)


if __name__ == "__main__":
    sys.exit(main())
