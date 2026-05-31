# URN: component:govern-lifecycle:enforcement-substrate:test_doctor_environment_diagnosis:backend:domain
# Runtime: python
# Purpose: Enforces `atdd doctor` correctly diagnoses the source-repo / foreign-install
#          mismatch that silently makes pre-push validators test stale code (#928 Gap 4).
"""
Tests for ``atdd.doctor`` — the environment self-diagnosis behind
``atdd doctor`` (issue #928 Gap 4).

The dogfooding mismatch: you are standing in the atdd source checkout but
the ``atdd`` being imported comes from a foreign install (e.g. a pipx
wheel). In that state ``atdd validate`` runs the released wheel's
validators against your working tree, so the pre-push gate tests stale
code and reports false orphans — the silent failure that cost a whole
session of reverse-engineering. ``atdd doctor`` must name this exactly.

These tests drive the pure evaluator (no import-path manipulation) plus
the report formatter.
"""
from __future__ import annotations

import pytest

from atdd.doctor import EnvDiagnosis, evaluate_diagnosis, format_report

pytestmark = [pytest.mark.coach]


def test_consumer_repo_is_healthy():
    """A consumer repo importing the installed wheel is fine — no mismatch."""
    d = evaluate_diagnosis(
        interpreter="/usr/bin/python3",
        can_import_atdd=True,
        atdd_import_path="/opt/venv/lib/python3.14/site-packages/atdd",
        repo_root="/home/me/my-app",
        repo_is_atdd_checkout=False,
        hook_python_can_import_atdd=True,
    )
    assert d.imported_from_tree is False
    assert d.source_repo_mismatch is False
    assert d.healthy is True


def test_editable_atdd_checkout_is_healthy():
    """Developing atdd with an editable/source install validates live code."""
    d = evaluate_diagnosis(
        interpreter="/repo/.venv/bin/python3",
        can_import_atdd=True,
        atdd_import_path="/repo/src/atdd",
        repo_root="/repo",
        repo_is_atdd_checkout=True,
        hook_python_can_import_atdd=True,
    )
    assert d.imported_from_tree is True
    assert d.source_repo_mismatch is False
    assert d.healthy is True


def test_dogfood_foreign_install_is_flagged():
    """THE bug: in the atdd checkout but importing a foreign (pipx) wheel."""
    d = evaluate_diagnosis(
        interpreter="/Users/me/.local/pipx/venvs/atdd/bin/python3",
        can_import_atdd=True,
        atdd_import_path="/Users/me/.local/pipx/venvs/atdd/lib/python3.14/site-packages/atdd",
        repo_root="/Users/me/Github/atdd/worktree",
        repo_is_atdd_checkout=True,
        hook_python_can_import_atdd=True,
    )
    assert d.imported_from_tree is False
    assert d.source_repo_mismatch is True
    assert d.healthy is False
    report = format_report(d)
    # The report must name the mismatch and point at the remedy.
    assert "stale" in report.lower()
    assert "atdd" in report.lower()
    assert any(tok in report for tok in ("PYTHONPATH=src", "editable", "pip install -e"))


def test_hook_python_cannot_import_atdd_is_flagged():
    """The version-gate misfire: the hooks' python3 can't import atdd at all."""
    d = evaluate_diagnosis(
        interpreter="/Users/me/.local/pipx/venvs/atdd/bin/python3",
        can_import_atdd=True,
        atdd_import_path="/Users/me/.local/pipx/venvs/atdd/lib/python3.14/site-packages/atdd",
        repo_root="/Users/me/Github/atdd/worktree",
        repo_is_atdd_checkout=True,
        hook_python_can_import_atdd=False,
    )
    assert d.hook_python_can_import_atdd is False
    assert d.healthy is False
    report = format_report(d)
    assert "hook" in report.lower()
    assert "atdd doctor" not in report or "import" in report.lower()


def test_cannot_import_atdd_is_unhealthy():
    """If atdd cannot be imported by the diagnosing interpreter, not healthy."""
    d = evaluate_diagnosis(
        interpreter="/opt/homebrew/bin/python3",
        can_import_atdd=False,
        atdd_import_path=None,
        repo_root="/Users/me/Github/atdd/worktree",
        repo_is_atdd_checkout=True,
        hook_python_can_import_atdd=False,
    )
    assert d.can_import_atdd is False
    assert d.healthy is False


def test_diagnosis_is_dataclass_with_expected_fields():
    """Contract: EnvDiagnosis carries the fields the report + callers rely on."""
    d = evaluate_diagnosis(
        interpreter="/x/python3",
        can_import_atdd=True,
        atdd_import_path="/x/site-packages/atdd",
        repo_root="/r",
        repo_is_atdd_checkout=False,
        hook_python_can_import_atdd=True,
    )
    assert isinstance(d, EnvDiagnosis)
    for field in (
        "interpreter", "can_import_atdd", "atdd_import_path", "repo_root",
        "repo_is_atdd_checkout", "imported_from_tree", "source_repo_mismatch",
        "hook_python_can_import_atdd", "healthy",
    ):
        assert hasattr(d, field), field
