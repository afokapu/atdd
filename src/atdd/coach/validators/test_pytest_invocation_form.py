"""Smoke test for the pytest subprocess invocation form (issue #341).

End-to-end regression: invokes the pytest runner shape used by `atdd
validate` against a fixture repo containing a single trivial test, and
asserts the runner does not raise ``FileNotFoundError``. This catches the
failure mode where bare ``pytest`` argv0 is unresolvable on the caller's
PATH (e.g. atdd installed via pipx into an isolated venv).

The test deliberately exercises the runner as it is wired in production
(via ``TestRunner._build_pytest_cmd`` + ``_run_pytest``) so that any
regression outside ``_build_pytest_cmd`` that re-introduces a PATH-bound
invocation is also caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atdd.coach.commands.test_runner import TestRunner

pytestmark = [pytest.mark.platform]


FIXTURE_REPO = Path(__file__).parent / "fixtures" / "minimal_repo"


def test_validate_runs_without_filenotfound(tmp_path: Path) -> None:
    """`_run_pytest` must launch pytest without raising FileNotFoundError.

    Reproduces the user-facing failure from issue #341: a bare ``pytest``
    argv0 is unresolvable when atdd ships in an isolated venv. The fix
    routes through ``[sys.executable, '-m', 'pytest', ...]`` which resolves
    against atdd's own interpreter where pytest is a hard dependency.
    """
    runner = TestRunner(repo_root=tmp_path)
    cmd = runner._build_pytest_cmd(
        validator_dirs=[str(FIXTURE_REPO)],
        parallel=False,
    )

    # Sanity: the cmd must use module-form invocation.
    assert cmd[:3] == [sys.executable, "-m", "pytest"]

    try:
        rc = runner._run_pytest(cmd)
    except FileNotFoundError as exc:
        pytest.fail(
            f"_run_pytest raised FileNotFoundError, regressing issue #341: {exc!r}. "
            "The runner must invoke pytest via [sys.executable, '-m', 'pytest']."
        )

    # rc 0 = all passed; rc 1 = test failures (still a successful launch);
    # rc 5 = no tests collected. Any of these prove the subprocess started.
    assert rc in (0, 1, 5), (
        f"Unexpected pytest exit code {rc}; expected 0/1/5 (process launched)."
    )
