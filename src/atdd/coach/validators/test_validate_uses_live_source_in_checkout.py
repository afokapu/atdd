# URN: component:govern-lifecycle:enforcement-substrate:test_validate_uses_live_source_in_checkout:backend:domain
# Runtime: python
# Purpose: Inside the atdd source checkout, `atdd validate` must run the WORKING-TREE
#          validators (src/atdd), not the installed wheel (#928 Gap 4 Item 3).
"""
Tests for the live-source resolution in ``TestRunner`` (#928 Gap 4 Item 3).

When ``atdd validate`` runs inside the atdd toolkit checkout, it must discover
validators from ``<repo>/src/atdd`` and import atdd from there — otherwise it
tests the last RELEASED wheel while you edit source, and hooks-on requires a
manual ``PYTHONPATH=src`` bridge. In a consumer repo it must still use the
installed package (unchanged).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import atdd
from atdd.coach.commands.test_runner import TestRunner

pytestmark = [pytest.mark.coach]


def _make_atdd_checkout(root: Path) -> None:
    (root / "src" / "atdd" / "coach" / "validators").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "atdd"\nversion = "9.9.9"\n')


def _make_consumer_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text('[project]\nname = "my-app"\nversion = "1.0.0"\n')


def test_checkout_resolves_validators_to_working_tree(tmp_path):
    repo = tmp_path / "atdd"
    repo.mkdir()
    _make_atdd_checkout(repo)

    runner = TestRunner(repo_root=repo)
    assert runner._repo_is_atdd_checkout() is True
    assert runner.atdd_pkg_dir == (repo / "src" / "atdd").resolve(), \
        "in the atdd checkout, validators must come from the working tree"


def test_consumer_repo_uses_installed_package(tmp_path):
    repo = tmp_path / "consumer"
    repo.mkdir()
    _make_consumer_repo(repo)

    runner = TestRunner(repo_root=repo)
    assert runner._repo_is_atdd_checkout() is False
    assert runner.atdd_pkg_dir == Path(atdd.__file__).resolve().parent, \
        "consumer repos must validate against the installed atdd package"


def test_run_pytest_env_injects_src_pythonpath_in_checkout(tmp_path, monkeypatch):
    """In the checkout, the pytest subprocess env must carry src/ on PYTHONPATH."""
    repo = tmp_path / "atdd"
    repo.mkdir()
    _make_atdd_checkout(repo)
    runner = TestRunner(repo_root=repo)

    captured = {}

    def fake_run(cmd, env=None, cwd=None):
        captured["env"] = env
        class _R:  # noqa: D401
            returncode = 0
        return _R()

    monkeypatch.setattr("atdd.coach.commands.test_runner.subprocess.run", fake_run)
    runner._run_pytest(["pytest", "-q"])

    pythonpath = captured["env"].get("PYTHONPATH", "")
    assert str(repo / "src") in pythonpath.split(":")[0], \
        "src/ must be prepended to PYTHONPATH so the subprocess imports atdd from source"
