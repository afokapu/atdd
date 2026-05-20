# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-UNIT-002-pre-push-hook-rejects-drift
# Acceptance: acc:govern-lifecycle:E021-UNIT-002-pre-push-hook-rejects-drift
# WMBT: wmbt:govern-lifecycle:E021
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-002: Pre-push hook running atdd registry update --check rejects a push
when the mirror is out of sync with source.

RED state: The pre-push hook at .atdd/hooks/pre-push has no registry-drift gate.
The hook does not invoke 'atdd registry update --check' at any point.
This test fails by asserting the hook script contains the gate call — which it does not yet.
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
HOOK_PATH = REPO_ROOT / ".atdd" / "hooks" / "pre-push"

# Stub import: RegistryDriftChecker does not exist yet; tests verify its behavior via
# the hook script gate rather than calling it directly.
try:
    from atdd.coach.commands.registry import RegistryDriftChecker  # type: ignore[attr-defined]
    _HAS_DRIFT_CHECKER = True
except ImportError:
    RegistryDriftChecker = None  # type: ignore[misc,assignment]
    _HAS_DRIFT_CHECKER = False


def test_pre_push_hook_contains_registry_check_gate():
    """The pre-push hook script must invoke 'atdd registry update --check' as a gate."""
    hook_text = HOOK_PATH.read_text()
    assert "registry update --check" in hook_text, (
        f"Pre-push hook at {HOOK_PATH} does not contain 'registry update --check'.\n"
        "Add the registry-drift gate step to the hook script."
    )


@pytest.mark.skipif(
    "registry update --check" not in HOOK_PATH.read_text(),
    reason="Pre-push hook missing registry gate — implement gate first (test_pre_push_hook_contains_registry_check_gate)",
)
def test_pre_push_hook_exits_nonzero_when_registry_drift_detected(tmp_path):
    """When atdd registry update --check exits non-zero, the pre-push hook also exits non-zero."""
    # Initialize a minimal git repo so the hook's git calls don't fail
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    # Patch PATH so the mocked atdd returns non-zero for registry update --check
    fake_atdd = tmp_path / "atdd"
    fake_atdd.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'registry update --check'*|*'registry'*'update'*'--check'*)\n"
        "    echo 'Drift detected: plan/_wagons.yaml' >&2\n"
        "    exit 1\n"
        "    ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    fake_atdd.chmod(0o755)

    env = {
        **os.environ,
        "CI": "false",
        "ATDD_SKIP_BARE_CHECK": "1",
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "GIT_DIR": str(tmp_path / ".git"),
    }

    push_stdin = (
        "refs/heads/feat/x 0000000000000000000000000000000000000001 "
        "refs/heads/feat/x 0000000000000000000000000000000000000000\n"
    )

    result = subprocess.run(
        ["sh", str(HOOK_PATH), "origin", "https://example.invalid/repo.git"],
        input=push_stdin,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0, (
        "Pre-push hook should exit non-zero when registry drift is detected, "
        f"but exited {result.returncode}.\nOutput:\n{output}"
    )


@pytest.mark.skipif(
    "registry update --check" not in HOOK_PATH.read_text(),
    reason="Pre-push hook missing registry gate — implement gate first",
)
def test_pre_push_hook_output_contains_fix_hint_on_drift(tmp_path):
    """When drift is detected, the pre-push hook output must contain 'atdd registry update --yes'."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    fake_atdd = tmp_path / "atdd"
    fake_atdd.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'registry update --check'*|*'registry'*'--check'*)\n"
        "    echo 'Drift detected: plan/_wagons.yaml' >&2\n"
        "    exit 1\n"
        "    ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    fake_atdd.chmod(0o755)

    env = {
        **os.environ,
        "CI": "false",
        "ATDD_SKIP_BARE_CHECK": "1",
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "GIT_DIR": str(tmp_path / ".git"),
    }

    push_stdin = (
        "refs/heads/feat/x 0000000000000000000000000000000000000001 "
        "refs/heads/feat/x 0000000000000000000000000000000000000000\n"
    )

    result = subprocess.run(
        ["sh", str(HOOK_PATH), "origin", "https://example.invalid/repo.git"],
        input=push_stdin,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    output = result.stdout + result.stderr
    assert "atdd registry update --yes" in output, (
        "Pre-push hook output must contain the fix-hint 'atdd registry update --yes' "
        f"when drift is detected.\nActual output:\n{output}"
    )
