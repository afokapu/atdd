#!/usr/bin/env python3
"""
Validator runner for ATDD.

Executes validators from the installed atdd package against the current
consumer repository. Validators are discovered from the package's
planner/tester/coder/coach validator directories.

Usage:
    atdd validate                # Run all validators
    atdd validate planner        # Run planner validators only
    atdd validate --local        # Run all validators offline (skip github_api tests)
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import atdd
from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo


def _xdist_available() -> bool:
    """Check if pytest-xdist is installed."""
    try:
        import xdist  # noqa: F401
        return True
    except ImportError:
        return False


# Git injects these into the environment of its hooks (pre-push, pre-commit,
# pre-merge-commit). They redirect git's notion of the repo/index/worktree to
# the in-progress operation. If they leak into the validator subprocess, every
# validator that shells out to `git` (commit-trailer checks, "leaves tree
# clean" readonly-command checks, core.bare baseline, manifest-write
# discipline, …) sees the WRONG git context and fails — deterministically, on
# state unrelated to the diff. This was a dominant reason `atdd validate` run
# from a pre-push hook blocked every push while a standalone run was green
# (#932). Scrub them so validators rediscover git context from cwd (repo_root).
_GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_INDEX_VERSION",
    "GIT_REFLOG_ACTION",
    "GIT_QUARANTINE_PATH",
    "GIT_PUSH_CERT",
)


def _scrub_git_hook_env(env: dict) -> dict:
    """Return *env* with git-hook-injected redirection vars removed.

    No-op outside a git hook (these vars are unset in a normal shell), so it is
    safe for every `atdd validate` invocation; inside a hook it restores the
    repo-at-cwd git context for validator subprocesses.
    """
    for var in _GIT_HOOK_ENV_VARS:
        env.pop(var, None)
    return env


class TestRunner:
    """Run ATDD validators with various configurations."""

    def __init__(self, repo_root: Path = None):
        self.repo_root = repo_root or find_repo_root()
        # #928 Gap 4 Item 3: inside the atdd source checkout, validate the LIVE
        # working tree (src/atdd), not the installed wheel. Otherwise `atdd
        # validate` (and every git hook that runs it) tests the last RELEASED
        # toolkit while you edit source — new validators look like orphans and
        # hooks-on requires a manual `PYTHONPATH=src` bridge. In a consumer
        # repo this falls back to the installed package, unchanged.
        self.atdd_pkg_dir = self._resolve_atdd_pkg_dir()

    def _repo_is_atdd_checkout(self) -> bool:
        """True when self.repo_root is the atdd toolkit source checkout.

        Keyed off ``pyproject.toml`` declaring ``name = "atdd"`` — independent
        of where the running ``atdd`` was imported from (a pipx wheel still
        reports the checkout correctly).
        """
        pyproject = self.repo_root / "pyproject.toml"
        try:
            return pyproject.is_file() and 'name = "atdd"' in pyproject.read_text(encoding="utf-8")
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-11-16
            return False

    def _resolve_atdd_pkg_dir(self) -> Path:
        src_pkg = self.repo_root / "src" / "atdd"
        if self._repo_is_atdd_checkout() and src_pkg.is_dir():
            return src_pkg.resolve()
        return Path(atdd.__file__).resolve().parent

    def _get_validator_dirs(self, phase: Optional[str] = None) -> Optional[list]:
        """Resolve validator directories for the given phase."""
        if phase and phase != "all":
            test_path = self.atdd_pkg_dir / phase / "validators"
            if not test_path.exists():
                print(f"Error: Test phase '{phase}' not found at {test_path}")
                return None
            return [str(test_path)]

        dirs = []
        for subdir in ["planner", "tester", "coder", "coach"]:
            validators_path = self.atdd_pkg_dir / subdir / "validators"
            if validators_path.exists():
                dirs.append(str(validators_path))
        if not dirs:
            print("Error: No validator directories found in atdd package")
            return None
        return dirs

    def _build_pytest_cmd(
        self,
        validator_dirs: list,
        verbose: bool = False,
        coverage: bool = False,
        html_report: bool = False,
        markers: Optional[List[str]] = None,
        parallel: bool = True,
        no_diagnostics: bool = False,
    ) -> list:
        """Build a pytest command list."""
        # Module-form invocation so atdd's own interpreter resolves pytest.
        # Bare 'pytest' argv0 fails when atdd is installed in an isolated
        # venv (e.g. pipx) whose bin/ is not on the consumer's PATH (#341).
        cmd = [sys.executable, "-m", "pytest"] + validator_dirs

        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")

        # pytest's -m is store, not append: passing it twice keeps only the LAST
        # expression and silently discards the earlier ones. Emitting one -m per
        # marker therefore dropped a filter whose identity depended on argument
        # order — `-m 'not platform' -m 'not github_api'` ran every platform test,
        # and `-m 'not github_api' -m 'not platform'` ran every API-bound test.
        # Conjoin into a single expression instead; each operand is parenthesised
        # so an operand that already contains `not`/`or` cannot rebind across the
        # `and` (#1475).
        if markers:
            cmd.extend(["-m", " and ".join(f"({m})" for m in markers)])

        if coverage:
            htmlcov_path = self.repo_root / ".atdd" / "htmlcov"
            cmd.extend([
                "--cov=atdd",
                "--cov-report=term-missing",
                f"--cov-report=html:{htmlcov_path}"
            ])

        if html_report:
            report_path = self.repo_root / ".atdd" / "test_report.html"
            cmd.extend([
                f"--html={report_path}",
                "--self-contained-html"
            ])

        if parallel and _xdist_available():
            cmd.extend(["-n", "auto"])
        elif parallel and not _xdist_available():
            print("  pytest-xdist not installed, running sequentially")

        cmd.append("--tb=short")

        # Validation diagnostics plugin (issue #449). Argv injection only —
        # never via conftest.py / pytest_plugins, which would auto-load it
        # in consumer suites outside ``atdd validate``. Suppressible via
        # ``--no-diagnostics`` for the rare runner that needs the legacy
        # stdout-only output (CI smoke jobs, --verify-baseline, etc.).
        if not no_diagnostics:
            cmd.extend(["-p", "atdd.coach.plugins.diagnostics"])

        return cmd

    def _run_pytest(self, cmd: list) -> int:
        """Run a pytest command and return exit code."""
        import os
        env = _scrub_git_hook_env(os.environ.copy())
        env["ATDD_REPO_ROOT"] = str(self.repo_root)

        # #928 Gap 4 Item 3: inside the atdd checkout, prepend src/ so the
        # pytest subprocess imports atdd from the WORKING TREE (matching
        # atdd_pkg_dir above), not the installed wheel — no manual bridge.
        if self._repo_is_atdd_checkout():
            src = str(self.repo_root / "src")
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")

        print(f"  Running: {' '.join(cmd)}")
        print(f"  Repo root: {self.repo_root}")
        print("=" * 60)

        result = subprocess.run(cmd, env=env, cwd=str(self.repo_root))
        return result.returncode

    def run_tests(
        self,
        phase: Optional[str] = None,
        verbose: bool = False,
        coverage: bool = False,
        html_report: bool = False,
        markers: Optional[List[str]] = None,
        parallel: bool = True,
        split: bool = True,
        local: bool = False,
        no_diagnostics: bool = False,
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
            split: Two-stage run (default True): fast tests parallel, then
                   API-bound platform tests sequential with shared fixtures.
                   Use --no-split to run everything in one pass.
            local: Explicitly allow running locally (default: GH Actions only)

        Returns:
            Exit code from pytest (non-zero if any stage fails)
        """
        import os
        if not os.environ.get("GITHUB_ACTIONS") and not local:
            print(
                "\033[33m⚠️  atdd validate is designed for GitHub Actions CI.\033[0m\n"
                "  Skipping locally. Use --local to run anyway:\n"
                "    atdd validate --local\n"
                "    atdd validate planner --local"
            )
            return 0

        validator_dirs = self._get_validator_dirs(phase)
        if validator_dirs is None:
            return 1

        # E025: consumer-mode platform-exclusion must apply before the split/no-split
        # branch so that --skip-api (which sets split=False) does not bypass it.
        # _run_split() historically held this guard; moving it here makes it the
        # single chokepoint regardless of invocation flags.
        if not is_atdd_source_repo():
            markers = list(markers or []) + ["not platform"]

        if split:
            return self._run_split(
                validator_dirs, verbose=verbose, coverage=coverage,
                html_report=html_report, markers=markers, parallel=parallel,
                no_diagnostics=no_diagnostics,
            )

        cmd = self._build_pytest_cmd(
            validator_dirs, verbose=verbose, coverage=coverage,
            html_report=html_report, markers=markers, parallel=parallel,
            no_diagnostics=no_diagnostics,
        )
        return self._run_pytest(cmd)

    def _run_split(
        self,
        validator_dirs: list,
        verbose: bool = False,
        coverage: bool = False,
        html_report: bool = False,
        markers: Optional[List[str]] = None,
        parallel: bool = True,
        no_diagnostics: bool = False,
    ) -> int:
        """Run validators in two stages: fast then slow.

        Stage 1: All tests except github_api — parallel
        Stage 2: github_api tests (live GitHub API) — sequential (shared session fixtures)

        In consumer mode (atdd installed via pip/pipx, not running from the
        toolkit source checkout), tests marked `platform` are skipped in
        Stage 1. They are toolkit-self dogfood tests that walk paths like
        ``src/atdd/...`` which only exist in the toolkit checkout — running
        them against a consumer repo would fail with assertion errors that
        have no consumer-side fix.
        """
        # Stage 1: all tests except github_api, parallel.
        # Consumer-mode 'not platform' exclusion is injected in run_tests() before
        # this method is called (E025), so markers already contain it when needed.
        stage1_expr = "not github_api"
        fast_markers = list(markers or []) + [stage1_expr]
        fast_cmd = self._build_pytest_cmd(
            validator_dirs, verbose=verbose, coverage=coverage,
            html_report=False, markers=fast_markers, parallel=parallel,
            no_diagnostics=no_diagnostics,
        )

        print("\n[1/2] Fast validators (file parsing + local platform, no API):")
        fast_rc = self._run_pytest(fast_cmd)

        # Stage 2: github_api tests, sequential to share session fixtures.
        # Diagnostics plugin disabled for the slow stage so the artifact
        # written by the fast stage isn't overwritten with a tiny tail of
        # github_api results (often 0 collected → empty findings list).
        slow_markers = list(markers or []) + ["github_api"]
        slow_cmd = self._build_pytest_cmd(
            validator_dirs, verbose=verbose, coverage=False,
            html_report=html_report, markers=slow_markers, parallel=False,
            no_diagnostics=True,
        )

        print("\n[2/2] GitHub API validators (live API):")
        slow_rc = self._run_pytest(slow_cmd)

        # Exit code 5 = "no tests collected" — expected when a phase has no
        # github_api-marked tests (planner, tester, coder currently have none).
        if slow_rc == 5:
            print("  No github_api tests collected for this phase — OK")
            slow_rc = 0

        # Fail if either stage failed
        if fast_rc != 0:
            return fast_rc
        return slow_rc

    def run_phase(self, phase: str, **kwargs) -> int:
        """Run validators for a specific phase."""
        return self.run_tests(phase=phase, **kwargs)

    def run_all(self, **kwargs) -> int:
        """Run all ATDD validators."""
        return self.run_tests(phase="all", **kwargs)

    def full_suite(self) -> int:
        """Full validation suite with coverage and HTML report."""
        print("🎯 Running full validation suite...")
        return self.run_tests(
            phase="all",
            verbose=True,
            coverage=True,
            html_report=True,
            parallel=True,
            local=True,
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
