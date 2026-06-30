"""Shared fixtures for the run-binding-plan SMOKE tests (issue #1238).

Every test drives the real ``atdd enforce`` CLI entry point as a subprocess —
the same command an operator (and the commit hook / CI job) invokes. No
synthetic subprocess stubs, no mocks, no collaborator substitution: the runner
either exists and behaves, or it does not exist yet (RED).
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

# Repo ``src`` so the subprocess imports THIS branch's atdd (the installed
# toolkit predates the enforce verb).
_SRC = pathlib.Path(__file__).resolve().parents[4]

# When the ``enforce`` verb is not wired, argparse rejects it with this text and
# exits 2. Every test guards on its absence: that guard is the load-bearing RED
# assertion — it fails today (verb absent) and flips green when the runner ships.
VERB_ABSENT = "invalid choice: 'enforce'"


def repo_src() -> pathlib.Path:
    return _SRC


@pytest.fixture
def run_enforce():
    """Run ``atdd enforce <args>`` as a real subprocess; return CompletedProcess."""

    def _run(args, cwd, extra_env: dict | None = None):
        env = {
            **os.environ,
            "PYTHONPATH": str(_SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "CI": "true",
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "atdd", "enforce", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
        )

    return _run
