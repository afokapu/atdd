"""Shared fixtures for substrate admission tests."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
import yaml

# Repo src so subprocesses import THIS branch's atdd (the installed toolkit may
# predate the substrate commands).
_SRC = pathlib.Path(__file__).resolve().parents[3]

DOOMED = "acme.extension.doomed"
KEEPER = "acme.extension.keeper"
WORKSPACE = "atdd.workspace.python-pytest"
DOOMED_RULE = "doomed.gate.one"
KEEPER_RULE = "keeper.gate.one"


def installed_ids(project_root) -> set:
    """The package ids `substrate.lock.yaml` says are installed."""
    from atdd.substrate import installer

    return {a["id"] for a in installer.list_substrate(project_root) if a.get("id")}


def bound_conventions(project_root) -> list:
    """The `bound` entries of `binding.lock.yaml`, read straight off disk.

    Deliberately reads the artifact rather than calling the production coherence
    helper: an invariant oracle that shares no code with the implementation cannot
    be fooled by a bug in the implementation.
    """
    path = pathlib.Path(project_root) / ".atdd" / "binding.lock.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [c for c in (data.get("conventions") or []) if c.get("disposition") == "bound"]


@pytest.fixture
def bound_substrate(tmp_path):
    """A real, installed, bound substrate mirroring the #1488 repro shape.

    One workspace provider plus TWO extensions, each owning one convention, with a
    binding plan composed from the lock. Two extensions matter: removing one must
    unbind only its own rules and must leave the workspace — still needed by the
    other — installed. That is the exact case a workspace-only coherence check
    would miss.
    """
    from atdd.substrate.binding import plan as plan_mod
    from atdd.substrate.binding.tests.conftest import install_extension, install_provider

    install_provider(tmp_path, WORKSPACE)
    install_extension(tmp_path, DOOMED, convention=DOOMED_RULE)
    install_extension(tmp_path, KEEPER, convention=KEEPER_RULE)
    plan_mod.write_binding_plan(tmp_path, plan_mod.build_binding_plan(tmp_path))
    return tmp_path


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
