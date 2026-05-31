# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-UNIT-001-shim-classifier-precise
# Acceptance: acc:govern-lifecycle:E036-UNIT-001-shim-classifier-precise
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.unit
"""AC-UNIT-001: the .atdd/bin/git shim's argv classifier is precise.

Blocks unscoped WRITES to the danger keys (exit 1, real git never reached):
  - git config core.bare true
  - git config --local core.worktree /tmp

Forwards everything else unchanged to the next git on PATH (exit 0, recorded):
  - git config --worktree core.bare true   (scoped → safe)
  - git config --get core.bare             (read)
  - git config core.bare                   (read, no value)
  - git config --unset core.bare           (repair)
  - git -c core.bare=false status          (ephemeral override)
  - git status                             (non-config)

RED state: src/atdd/coach/templates/bin/git.shim does not exist yet, so the
fixture's install step fails the GIT_SHIM_TEMPLATE.exists() guard.
"""
from __future__ import annotations

import pytest

from .conftest import GIT_SHIM_TEMPLATE, REPO_ROOT, run_git_via_shim

pytestmark = [pytest.mark.coach]


def _require_shim() -> None:
    assert GIT_SHIM_TEMPLATE.exists(), (
        f"RED: {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"
    )


@pytest.mark.parametrize(
    "args",
    [
        ["config", "core.bare", "true"],
        ["config", "--local", "core.worktree", "/tmp"],
    ],
)
def test_shim_blocks_unscoped_danger_write(git_shim_worktree, args) -> None:
    _require_shim()
    worktree, real_bin, record = git_shim_worktree
    result = run_git_via_shim(worktree, real_bin, args)
    assert result.returncode == 1, f"expected block (exit 1) for {args}, got {result.returncode}: {result.stderr}"
    assert "--worktree" in result.stderr, f"alternative missing from stderr: {result.stderr!r}"
    assert not record.exists(), f"real git was invoked for a blocked {args}"


@pytest.mark.parametrize(
    "args",
    [
        ["config", "--worktree", "core.bare", "true"],   # scoped write — safe
        ["config", "--get", "core.bare"],                # read
        ["config", "core.bare"],                         # read, no value
        ["config", "--unset", "core.bare"],              # repair
        ["-c", "core.bare=false", "status"],             # ephemeral override
        ["status"],                                      # non-config
    ],
)
def test_shim_forwards_allowed_invocations(git_shim_worktree, args) -> None:
    _require_shim()
    worktree, real_bin, record = git_shim_worktree
    result = run_git_via_shim(worktree, real_bin, args)
    assert result.returncode == 0, f"allowed {args} was wrongly blocked: {result.stderr}"
    assert record.exists(), f"allowed {args} was not forwarded to the real git"
    assert " ".join(args) in record.read_text(), f"forwarded argv {args!r} not recorded: {record.read_text()!r}"
