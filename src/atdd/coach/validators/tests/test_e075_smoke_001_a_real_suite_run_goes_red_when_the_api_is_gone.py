# URN: test:govern-lifecycle:validator-fixtures-refuse-when-unestablished:E075-SMOKE-001-a-real-suite-run-goes-red-when-the-api-is-gone
# Acceptance: acc:govern-lifecycle:E075-SMOKE-001-a-real-suite-run-goes-red-when-the-api-is-gone
# WMBT: wmbt:govern-lifecycle:E075
# Phase: SMOKE
# Layer: integration
"""E075-SMOKE-001 — a real suite run goes red when the API is gone (#1896).

The UNIT test drives the fixtures directly. This one runs pytest as a subprocess,
because the defect was never about a return value — it was about the SUMMARY
LINE. "11 passed, 4 skipped" and "15 passed" are both read as success, and that
reading is what let 16 validators report nothing for as long as they did.

So this asserts on what a reader sees: the process exit code and the summary.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

pytestmark = [pytest.mark.platform]

_SUITE = '''
import pytest
from atdd.coach.validators.conftest import all_open_issues_unfiltered

@pytest.fixture(scope="session")
def _github_prefetch():
    return {"all_open_issues": RuntimeError("API rate limit already exceeded")}

@pytest.fixture(scope="session")
def issues(_github_prefetch):
    return getattr(all_open_issues_unfiltered, "__wrapped__")(_github_prefetch)

def test_a_validator_behind_the_fixture(issues):
    assert issues is not None
'''


REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> subprocess.CompletedProcess:
    d = tmp_path_factory.mktemp("e075")
    (d / "test_probe.py").write_text(textwrap.dedent(_SUITE), encoding="utf-8")
    # PYTHONPATH matters here: without it the probe exits non-zero on
    # ModuleNotFoundError, and the exit-code and summary assertions both pass for
    # a reason that has nothing to do with the fixture under test. Caught by the
    # COULD_NOT_CHECK assertion, which is the one that actually names the subject.
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(d / "test_probe.py"), "-q", "-p", "no:randomly"],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )


def test_the_run_exits_non_zero(run) -> None:
    """A suite that could not evaluate its subject does not report success."""
    assert run.returncode != 0, (
        "the run reported success while the API query had failed:\n" + run.stdout[-800:]
    )


def test_the_summary_line_does_not_say_passed(run) -> None:
    """THE POINT. `11 passed, 4 skipped` is read as green by every reader and
    every CI badge."""
    summary = [ln for ln in run.stdout.splitlines() if " passed" in ln or " failed" in ln or " error" in ln]
    assert summary, f"no summary line at all:\n{run.stdout[-800:]}"
    assert not any(ln.strip().startswith(("1 passed", "2 passed")) and "failed" not in ln and "error" not in ln
                   for ln in summary), f"summary reports success: {summary}"


def test_the_output_names_could_not_check(run) -> None:
    blob = run.stdout + run.stderr
    assert "COULD_NOT_CHECK" in blob, (
        "a reader cannot tell an unevaluated run from a clean one:\n" + blob[-800:]
    )
