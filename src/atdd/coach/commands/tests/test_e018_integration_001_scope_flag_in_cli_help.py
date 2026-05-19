# URN: test:govern-lifecycle:pr-scoped-registry-drift-gate:E018-INTEGRATION-001-scope-flag-in-cli-help
# Acceptance: acc:govern-lifecycle:E018-INTEGRATION-001-scope-flag-in-cli-help
# WMBT: wmbt:govern-lifecycle:E018
# Phase: GREEN
# Layer: backend.integration
"""
AC-INTEGRATION-001: atdd registry update --help contains --scope with 'changed-files'
documented as an accepted value.
"""
import subprocess
import sys
import os
from pathlib import Path


def _repo_src() -> str:
    """Return the src/ directory for the local source tree."""
    here = Path(__file__)
    for parent in here.parents:
        candidate = parent / "src"
        if candidate.is_dir():
            return str(candidate)
    return ""


def _run_atdd_help():
    env = os.environ.copy()
    src = _repo_src()
    if src:
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "atdd", "registry", "update", "--help"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_scope_flag_appears_in_registry_update_help():
    """--scope flag is documented in atdd registry update --help."""
    result = _run_atdd_help()
    help_text = result.stdout + result.stderr
    assert "--scope" in help_text, f"--scope not found in help:\n{help_text}"


def test_scope_help_mentions_changed_files():
    """The --scope help text mentions 'changed-files' as the PR-scoped value."""
    result = _run_atdd_help()
    help_text = result.stdout + result.stderr
    assert "changed-files" in help_text, (
        f"'changed-files' not mentioned in --scope help:\n{help_text}"
    )
