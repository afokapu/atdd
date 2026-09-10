# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-SMOKE-001-routine-push-requires-zero-gate-bypasses
# Acceptance: acc:govern-lifecycle:E023-SMOKE-001-routine-push-requires-zero-gate-bypasses
# WMBT: wmbt:govern-lifecycle:E023
# Phase: SMOKE
# Layer: backend.integration
"""AC-SMOKE-001: a routine branch push on an up-to-date worktree completes with
no env-var bypass, and quickly (#1893).

The acceptance was always right — "No gate-bypass env-var was needed". The test
was a RED-phase stub that asserted `ATDD_SKIP_ALL_GATES` was present in the hook,
which E026 then required to be absent, so it has been red ever since. It was left
carrying `# Phase: RED` and the note "this test drives the implementation" long
after E023 completed.

E023's measured complaint was a 2-4 flag cocktail per push, ~30 documented bypass
invocations across ten issues, none of them emergencies. That is what this
asserts: the clean path needs nothing, and it is fast enough that reaching for a
bypass is not tempting.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOK_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-push"

_STDIN_NON_MAIN = (
    "refs/heads/feat/routine 1111111111111111111111111111111111111111 "
    "refs/heads/feat/routine 0000000000000000000000000000000000000000\n"
)
_TIME_BUDGET_SECONDS = 5.0


@pytest.fixture()
def clean_repo(tmp_path: Path) -> tuple[Path, dict]:
    """A worktree in the state the acceptance describes: up to date, no overrides."""
    import os

    subprocess.run(["git", "init", "-q", "-b", "feat/routine", str(tmp_path)], check=True)
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir(parents=True, exist_ok=True)
    # A declared floor is what "up-to-date worktree" means for the version gate;
    # without one it falls back to PyPI and the verdict tracks the network.
    (atdd_dir / "config.yaml").write_text(
        "release:\n  minimum_version: '0.0.1'\n", encoding="utf-8"
    )

    hook = tmp_path / "pre-push"
    hook.write_bytes(HOOK_PATH.read_bytes())
    hook.chmod(0o755)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "CI": "true",
    }
    return hook, env


def test_a_routine_push_needs_no_bypass_env_var(clean_repo) -> None:
    hook, env = clean_repo
    assert not [k for k in env if k.startswith("ATDD_SKIP")], (
        "the environment sets a bypass, so this would prove the opposite of the "
        "acceptance"
    )

    result = subprocess.run(
        [str(hook), "origin", "https://example.com/repo.git"],
        input=_STDIN_NON_MAIN, capture_output=True, text=True,
        cwd=str(hook.parent), env=env,
    )

    assert result.returncode == 0, (
        f"the hook exited {result.returncode} on a clean push with no overrides.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_the_clean_path_is_fast_enough_not_to_invite_a_bypass(clean_repo) -> None:
    """E023's complaint was cost, not correctness: gates that are slow get
    bypassed, and a gate that is always bypassed enforces nothing."""
    hook, env = clean_repo
    started = time.monotonic()
    subprocess.run(
        [str(hook), "origin", "https://example.com/repo.git"],
        input=_STDIN_NON_MAIN, capture_output=True, text=True,
        cwd=str(hook.parent), env=env,
    )
    elapsed = time.monotonic() - started
    assert elapsed < _TIME_BUDGET_SECONDS, (
        f"the clean path took {elapsed:.1f}s, over the {_TIME_BUDGET_SECONDS}s budget"
    )
