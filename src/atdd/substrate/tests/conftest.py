"""Shared fixtures for substrate admission tests."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

# Repo src so subprocesses import THIS branch's atdd (the installed toolkit may
# predate the substrate commands).
_SRC = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def run_atdd():
    def _run(args: list[str], cwd, extra_env: dict | None = None):
        env = {
            **os.environ,
            "PYTHONPATH": str(_SRC) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "CI": "true",
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "atdd", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
        )

    return _run
