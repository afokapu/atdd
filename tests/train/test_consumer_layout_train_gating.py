"""Regression — the train validators must not fire on a non-train consumer (#689).

sboupda's ``portfolio-management`` is laid out as ``python/<package>/...`` with
no ``app.py``, no ``wagon.py`` and no ``trains/`` tree. Before this gate,
``test_wagons_implement_run_train`` was gated on the *code root* and then
hard-asserted ``len(find_wagons()) > 0``, so every such consumer failed
``atdd validate coder`` with "No wagons found in python/ directory" — a check it
had no way to satisfy. Three sibling station-master tests had the same defect
against ``python/app.py`` and were regated onto the resolved entrypoint by
#1476 / PR #1485; this is the fourth and last.

The gate is the *train runtime*, not the code root: a repo with no ``trains/``
tree has no orchestration for a wagon to participate in. These tests pin both
directions — the consumer skips, and a repo that really does declare train
infrastructure still gets enforced, so the fix cannot rot into a blanket skip.

Driven as a child pytest process because the validator resolves ``REPO_ROOT``
(and therefore every skip flag) at module-import time from the working
directory, so the layout must exist before the module is imported.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
VALIDATOR = (
    SRC_DIR / "atdd" / "coder" / "validators" / "test_train_infrastructure.py"
)
TEST_ID = f"{VALIDATOR}::test_wagons_implement_run_train"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=True)


def _make_repo(root: Path) -> Path:
    """A git repo with an .atdd/ config and default (undeclared) code roots."""
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text("project:\n  name: fixture\n")
    _git("init", cwd=root)
    return root


def _consumer_repo(root: Path) -> Path:
    """sboupda's shape: a python tier, but no wagons, no trains, no app.py."""
    _make_repo(root)
    pkg = root / "python" / "manage_portfolio" / "portfolio_mvp"
    pkg.mkdir(parents=True)
    (root / "python" / "pyproject.toml").write_text(
        '[project]\nname = "portfolio-management"\nversion = "0.1.0"\n'
    )
    (root / "python" / "manage_portfolio" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "core.py").write_text("def compute_allocation(holdings):\n    return {}\n")
    return root


def _run_validator(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", TEST_ID, "-p", "no:cacheprovider", "-q"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(SRC_DIR), "HOME": str(repo)},
    )


def test_consumer_without_train_runtime_is_skipped_not_failed(tmp_path):
    """The #689 repro: a python tier with no trains/ must skip, not fail."""
    result = _run_validator(_consumer_repo(tmp_path / "consumer"))

    assert result.returncode == 0, (
        "a consumer with no train runtime must not fail the wagon validator "
        f"(this is #689)\n{result.stdout}\n{result.stderr}"
    )
    assert "1 skipped" in result.stdout, (
        f"expected the wagon test to be skipped, got:\n{result.stdout}"
    )
    assert "No wagons found" not in result.stdout


def test_repo_declaring_train_runtime_is_still_enforced(tmp_path):
    """The fix must not become a blanket skip: trains/ present ⇒ still gates."""
    repo = _make_repo(tmp_path / "trainrepo")
    (repo / "python" / "trains").mkdir(parents=True)

    result = _run_validator(repo)

    assert result.returncode != 0, (
        "a repo declaring train infrastructure but shipping no wagons must "
        f"still fail\n{result.stdout}\n{result.stderr}"
    )
    assert "No wagons found" in result.stdout


def test_wagon_implementing_run_train_passes(tmp_path):
    """Control for the above: a well-formed train repo passes."""
    repo = _make_repo(tmp_path / "goodtrain")
    (repo / "python" / "trains").mkdir(parents=True)
    wagon = repo / "python" / "pace_dilemmas"
    wagon.mkdir(parents=True)
    (wagon / "wagon.py").write_text(
        "def run_train(inputs, timing=None):\n    return {}\n"
    )

    result = _run_validator(repo)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "1 passed" in result.stdout
