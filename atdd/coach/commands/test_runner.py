#!/usr/bin/env python3
"""
Test runner for ATDD meta-tests.

Replaces run_all_tests.sh with a more flexible Python-based test runner.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class TestRunner:
    """Run ATDD meta-tests with various configurations."""

    def __init__(self, repo_root: Path = None):
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        self.atdd_dir = self.repo_root / "atdd"

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
        Run ATDD tests with specified options.

        Args:
            phase: Test phase to run (planner, tester, coder, all, None=all)
            verbose: Enable verbose output
            coverage: Generate coverage report
            html_report: Generate HTML report
            markers: Additional pytest markers to filter
            parallel: Run tests in parallel (uses pytest-xdist)

        Returns:
            Exit code from pytest
        """
        # Build pytest command
        cmd = ["pytest"]

        # Determine test path
        if phase and phase != "all":
            test_path = self.atdd_dir / phase
            if not test_path.exists():
                print(f"❌ Error: Test phase '{phase}' not found at {test_path}")
                return 1
            cmd.append(str(test_path))
        else:
            # Run all atdd tests
            cmd.append(str(self.atdd_dir))

        # Add verbosity
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")

        # Add markers
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        # Add coverage
        if coverage:
            cmd.extend([
                "--cov=atdd",
                "--cov-report=term-missing",
                "--cov-report=html:atdd/htmlcov"
            ])

        # Add HTML report
        if html_report:
            cmd.extend([
                "--html=atdd/test_report.html",
                "--self-contained-html"
            ])

        # Add parallel execution
        if parallel:
            cmd.extend(["-n", "auto"])

        # Show collected tests summary
        cmd.append("--tb=short")

        # Run pytest
        print(f"🧪 Running: {' '.join(cmd)}")
        print("=" * 60)

        result = subprocess.run(cmd, cwd=self.repo_root)
        return result.returncode

    def run_phase(self, phase: str, **kwargs) -> int:
        """Run tests for a specific phase."""
        return self.run_tests(phase=phase, **kwargs)

    def run_all(self, **kwargs) -> int:
        """Run all ATDD meta-tests."""
        return self.run_tests(phase="all", **kwargs)

    def quick_check(self) -> int:
        """Quick smoke test - run without parallelization."""
        print("🚀 Running quick check (no parallel)...")
        return self.run_tests(
            phase="all",
            verbose=False,
            parallel=False,
            html_report=False
        )

    def full_suite(self) -> int:
        """Full test suite with coverage and HTML report."""
        print("🎯 Running full test suite...")
        return self.run_tests(
            phase="all",
            verbose=True,
            coverage=True,
            html_report=True,
            parallel=True
        )


def main():
    """CLI entry point for test runner."""
    runner = TestRunner()

    # Simple usage for now - can be enhanced with argparse
    if len(sys.argv) > 1:
        phase = sys.argv[1]
        return runner.run_phase(phase, verbose=True, html_report=True)
    else:
        return runner.run_all(verbose=True, html_report=True)


if __name__ == "__main__":
    sys.exit(main())
