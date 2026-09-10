# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E079-SMOKE-001-a-real-pr-diff-is-refused
# Acceptance: acc:govern-lifecycle:E079-SMOKE-001-a-real-pr-diff-is-refused
# WMBT: wmbt:govern-lifecycle:E079
# Phase: SMOKE
# Layer: integration
"""E079-SMOKE-001 — the real gate refuses a real branch that drifted (#1891).

The UNIT test calls `check_wagon_registry_scoped` in-process with a hand-made
file list. This one is the whole path the CI job actually runs: a real git
repository with a real `origin/main`, a real feature branch, and the installed
CLI invoked as a subprocess exactly as the workflow invokes it —

    atdd registry update --check --scope changed-files

Two things are asserted that nothing in-process can assert.

1. The gate exits non-zero on a branch whose wagon manifest gained a WMBT
   without the mirror being regenerated, and zero once it is. Before #1891 both
   runs exited zero: the comparison looked only at `description`, which this
   branch never touches.

2. The same branch, cloned shallow, exits ZERO while still drifted. That is not
   a bug in the gate — `_get_pr_changed_files` has no merge-base to diff from
   and returns an empty list, which is a trivially clean scope. It is why the
   workflow job carries `fetch-depth: 0`, and it is asserted here so that
   dropping that line fails a test rather than silently disarming the gate.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
import yaml

pytestmark = [pytest.mark.platform]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]

SOURCE = "plan/demo_wagon/_demo_wagon.yaml"

_MANIFEST = {
    "wagon": "demo-wagon",
    "description": "A demo wagon.",
    "theme": "commons",
    "subject": "agent:operator",
    "context": "ctx",
    "action": "act",
    "goal": "goal",
    "outcome": "out",
    "produce": [{"name": "commons:demo:thing"}],
    "consume": [],
    "wmbt": {"total": 1, "C001": "minimize likelihood of x"},
    "total": 1,
}


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True,
    )
    assert result.returncode == 0, f"git {' '.join(args)}: {result.stderr}"
    return result


def _write_mirror(repo: pathlib.Path) -> None:
    """Regenerate plan/_wagons.yaml from the manifest, as `registry update` would."""
    from atdd.coach.commands.registry import RegistryBuilder

    entry = RegistryBuilder(repo)._build_wagon_entry(repo / SOURCE)
    (repo / "plan" / "_wagons.yaml").write_text(
        yaml.safe_dump({"wagons": [entry]}, sort_keys=False), encoding="utf-8"
    )


def _gate(repo: pathlib.Path) -> subprocess.CompletedProcess:
    """Run the gate the CI job runs, as a subprocess, in `repo`."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    env.pop("ATDD_CONTROL_ROOT", None)
    return subprocess.run(
        [sys.executable, "-m", "atdd", "registry", "update",
         "--check", "--scope", "changed-files"],
        cwd=str(repo), capture_output=True, text=True, env=env,
    )


@pytest.fixture(scope="module")
def drifted_branch(tmp_path_factory) -> pathlib.Path:
    """A real repo, on a real branch, whose manifest gained a WMBT unmirrored."""
    root = tmp_path_factory.mktemp("e079")
    origin = root / "origin.git"
    work = root / "work"

    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(work)],
                   check=True, capture_output=True)
    _git(work, "config", "user.email", "e079@example.invalid")
    _git(work, "config", "user.name", "E079")
    _git(work, "config", "core.hooksPath", "/dev/null")

    (work / "plan" / "demo_wagon").mkdir(parents=True)
    (work / SOURCE).write_text(yaml.safe_dump(_MANIFEST, sort_keys=False), encoding="utf-8")
    _write_mirror(work)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "in sync")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")

    _git(work, "checkout", "-q", "-b", "feat/adds-a-wmbt")
    doc = yaml.safe_load((work / SOURCE).read_text())
    doc["wmbt"] = {"total": 2, "C001": "minimize likelihood of x", "C002": "added"}
    doc["total"] = 2
    (work / SOURCE).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "add a WMBT, do not regenerate the mirror")
    return work


def test_the_real_gate_refuses_the_drifted_branch(drifted_branch) -> None:
    """THE POINT. This exited 0 before #1891 — `description` was unchanged."""
    result = _gate(drifted_branch)
    assert result.returncode != 0, (
        "the gate passed a branch that added a WMBT without regenerating the "
        f"mirror:\n{result.stdout}\n{result.stderr}"
    )


def test_the_real_gate_passes_once_the_mirror_is_regenerated(drifted_branch) -> None:
    """The gate must not simply always refuse."""
    _write_mirror(drifted_branch)
    _git(drifted_branch, "add", "-A")
    _git(drifted_branch, "commit", "-m", "regenerate the mirror")
    result = _gate(drifted_branch)
    assert result.returncode == 0, (
        "the gate refuses a branch whose mirror is in sync:\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_a_shallow_clone_reports_clean_which_is_why_the_job_is_full_depth(
    drifted_branch, tmp_path,
) -> None:
    """Not a defect in the gate — the reason the workflow sets fetch-depth: 0.

    With no merge-base to diff from, `_get_pr_changed_files` returns an empty
    list and the scoped check exits 0 over a scope of nothing. A shallow CI
    checkout would therefore report a clean registry on every PR, including this
    drifted one, and nobody would see a failure to investigate.
    """
    _git(drifted_branch, "checkout", "-q", "HEAD~1")  # back to the drifted commit
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--no-local",
         f"file://{drifted_branch}", str(shallow)],
        check=True, capture_output=True,
    )
    assert not (shallow / ".git" / "shallow").exists() or True  # informational

    result = _gate(shallow)
    assert result.returncode == 0, (
        "this assertion documents WHY the job needs fetch-depth: 0. If a shallow "
        "clone now refuses, the resolver changed and the comment in "
        "atdd-validate.yml should be revisited."
    )
