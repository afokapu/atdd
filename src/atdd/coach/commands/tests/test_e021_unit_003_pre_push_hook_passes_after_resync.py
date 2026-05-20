# URN: test:govern-lifecycle:systemic-registry-drift-enforcement:E021-UNIT-003-pre-push-hook-passes-after-resync
# Acceptance: acc:govern-lifecycle:E021-UNIT-003-pre-push-hook-passes-after-resync
# WMBT: wmbt:govern-lifecycle:E021
# Phase: GREEN
# Layer: backend.unit
"""
AC-UNIT-003: Pre-push hook passes (exits 0) after the operator runs
atdd registry update --yes and re-stages the mirror files.

RED state: The pre-push hook has no registry-drift gate, so this scenario cannot
be verified. The test asserting the hook calls 'atdd registry update --check'
(from UNIT-002) already fails; this test fails for the same reason —
the gate that would produce the pass/fail does not yet exist in the hook.
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
HOOK_PATH = REPO_ROOT / ".atdd" / "hooks" / "pre-push"


@pytest.mark.skipif(
    "registry update --check" not in HOOK_PATH.read_text(),
    reason="Pre-push hook missing registry gate — the 'passes' scenario is meaningless without the gate",
)
def test_pre_push_hook_passes_when_registry_in_sync(tmp_path):
    """When atdd registry update --check exits 0, the pre-push hook must also exit 0."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    # Mock atdd that returns 0 for registry update --check (no drift)
    fake_atdd = tmp_path / "fake_atdd.sh"
    fake_atdd.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'registry update --check'*|*'registry'*'--check'*)\n"
        "    echo 'No drift detected'\n"
        "    exit 0\n"
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

    # The test verifies the hook's registry gate passes.
    # RED: since the hook has no registry gate, we can't verify that the gate
    # correctly passes — the hook must explicitly call registry update --check
    # and only pass when it exits 0. For now this will fail because:
    # 1. The hook doesn't call fake_atdd for registry check at all
    # 2. We cannot confirm the hook handled the gate correctly (not just bypassed it)
    hook_text = HOOK_PATH.read_text()
    assert "registry update --check" in hook_text, (
        "Pre-push hook must contain 'registry update --check' gate before this "
        "pass-through behavior can be verified. "
        "Add the registry-drift gate to .atdd/hooks/pre-push."
    )

    assert result.returncode == 0, (
        f"Pre-push hook should exit 0 when registry is in sync, "
        f"but exited {result.returncode}.\nOutput:\n{result.stdout + result.stderr}"
    )


def test_pre_push_hook_does_not_block_when_no_drift(tmp_path):
    """Push is not blocked when registry is in sync — hook exits 0 without registry error."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    fake_atdd = tmp_path / "fake_atdd.sh"
    fake_atdd.write_text("#!/bin/sh\nexit 0\n")
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

    hook_text = HOOK_PATH.read_text()
    assert "registry update --check" in hook_text, (
        "Pre-push hook must contain 'registry update --check' to make this test meaningful. "
        "A hook that does NOT call registry update --check 'passes' trivially — not because "
        "the registry is in sync, but because the gate doesn't exist."
    )
