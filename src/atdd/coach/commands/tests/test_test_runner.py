"""Unit tests for `atdd.coach.commands.test_runner`.

Regression coverage for issue #341: `atdd validate` must invoke pytest as
a module under the active interpreter (`sys.executable -m pytest`) rather
than relying on PATH resolution of a bare `pytest` argv0. The latter fails
when atdd is installed in an isolated venv (e.g. via pipx) whose
`bin/pytest` is not on the consumer's PATH.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from atdd.coach.commands.test_runner import TestRunner

pytestmark = [pytest.mark.platform]


@pytest.fixture
def runner(tmp_path: Path) -> TestRunner:
    return TestRunner(repo_root=tmp_path)


def test_build_pytest_cmd_uses_module_invocation(runner: TestRunner) -> None:
    """argv0 must be sys.executable, followed by '-m', 'pytest'."""
    cmd = runner._build_pytest_cmd(validator_dirs=["/tmp/fake"], parallel=False)

    assert cmd[:3] == [sys.executable, "-m", "pytest"], (
        f"Expected argv to begin with [sys.executable, '-m', 'pytest']; got {cmd[:3]!r}. "
        "Bare 'pytest' argv0 fails when atdd is installed in an isolated venv (pipx)."
    )


def test_build_pytest_cmd_does_not_use_bare_pytest(runner: TestRunner) -> None:
    """The literal string 'pytest' must never appear at argv[0]."""
    cmd = runner._build_pytest_cmd(validator_dirs=["/tmp/fake"], parallel=False)
    assert cmd[0] != "pytest", (
        "argv[0] must not be the bare string 'pytest'; it must be sys.executable."
    )


def test_build_pytest_cmd_preserves_validator_dirs(runner: TestRunner) -> None:
    """Validator dirs must follow the pytest invocation prefix unchanged."""
    cmd = runner._build_pytest_cmd(
        validator_dirs=["/tmp/dir-a", "/tmp/dir-b"], parallel=False
    )
    assert "/tmp/dir-a" in cmd and "/tmp/dir-b" in cmd
    # The dirs must come after the [python, -m, pytest] prefix
    assert cmd.index("/tmp/dir-a") >= 3
