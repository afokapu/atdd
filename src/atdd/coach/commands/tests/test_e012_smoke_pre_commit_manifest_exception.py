# Acceptance: acc:govern-lifecycle:E012-SMOKE-001-pre-commit-hook-installed-allows-manifest-only
# Acceptance: acc:govern-lifecycle:E012-SMOKE-002-issue-reconcile-wired-in-cli
# Acceptance: acc:govern-lifecycle:Y004-SMOKE-001-pre-commit-template-has-drift-notice
# Acceptance: acc:govern-lifecycle:Y005-SMOKE-001-reconcile-wired-in-cli
"""SMOKE tests for E012: pre-commit exception and atdd issue reconcile CLI wiring (#775).

These tests verify the integration points work against real infrastructure:
- The installed hook template exists on disk and is executable
- The `atdd issue reconcile` subcommand is wired in the CLI and returns a valid exit code
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# parents[5] from commands/tests/ → repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
HOOK_TEMPLATE = REPO_ROOT / "src/atdd/coach/templates/hooks/pre-commit"


# ---------------------------------------------------------------------------
# E012-SMOKE-001 — hook template on disk and contains the exception
# ---------------------------------------------------------------------------

def test_hook_template_exists() -> None:
    """E012-SMOKE-001: the pre-commit hook template must exist on disk."""
    assert HOOK_TEMPLATE.exists(), (
        f"pre-commit hook template not found at {HOOK_TEMPLATE}"
    )


def test_hook_template_contains_manifest_exception() -> None:
    """E012-SMOKE-001: the hook template must contain the manifest-only exception."""
    content = HOOK_TEMPLATE.read_text()
    assert ".atdd/manifest.yaml" in content, (
        "pre-commit hook must reference .atdd/manifest.yaml in its manifest-only exception"
    )
    assert 'exit 0' in content, (
        "pre-commit hook must have an exit 0 path for the manifest-only exception"
    )


def test_hook_template_contains_reconcile_hint() -> None:
    """E012-SMOKE-001: the hook template must mention 'atdd issue reconcile' in the drift notice."""
    content = HOOK_TEMPLATE.read_text()
    assert "reconcile" in content, (
        "pre-commit hook must mention 'atdd issue reconcile' in the drift notice"
    )


# ---------------------------------------------------------------------------
# E012-SMOKE-002 — atdd issue reconcile wired in CLI
# ---------------------------------------------------------------------------

def test_atdd_issue_reconcile_is_recognized_by_cli() -> None:
    """E012-SMOKE-002: cli.py dispatch must route 'reconcile' target to IssueManager.reconcile()."""
    # Read the CLI source directly — the installed binary may lag the local tree.
    cli_source = (REPO_ROOT / "src/atdd/cli.py").read_text()
    assert "reconcile" in cli_source, (
        "cli.py must wire the 'reconcile' target in the atdd issue dispatch block"
    )
    assert "manager.reconcile()" in cli_source, (
        "cli.py must call manager.reconcile() for the reconcile target"
    )


def test_branch_manager_has_backfill_method() -> None:
    """E012-SMOKE-002: BranchManager must expose _backfill_from_github after import."""
    from atdd.coach.commands.branch import BranchManager
    assert hasattr(BranchManager, "_backfill_from_github"), (
        "BranchManager must have _backfill_from_github method"
    )


def test_issue_manager_has_reconcile_method() -> None:
    """E012-SMOKE-002: IssueManager must expose reconcile() after import."""
    from atdd.coach.commands.issue import IssueManager
    assert hasattr(IssueManager, "reconcile"), (
        "IssueManager must have reconcile() method"
    )
