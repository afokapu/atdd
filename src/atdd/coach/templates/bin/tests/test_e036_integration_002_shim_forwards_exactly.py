# URN: test:govern-lifecycle:agnostic-git-config-bare-guard-via-path-shim:E036-INTEGRATION-002-shim-forwards-exactly
# Acceptance: acc:govern-lifecycle:E036-INTEGRATION-002-shim-forwards-exactly
# WMBT: wmbt:govern-lifecycle:E036
# Phase: RED
# Layer: backend.integration
"""AC-INTEGRATION-002: forwarding correctness — the main risk.

A non-blocked git invocation must reach the next git on PATH with argv, exit
code, stdout, and stderr preserved byte-for-byte. We stage a forwarding stub
that echoes a known marker to BOTH stdout and stderr, records argv, and exits
with a known non-zero code, then assert the shim relays all three unchanged.

RED state: src/atdd/coach/templates/bin/git.shim does not exist yet.
"""
from __future__ import annotations

import pytest

from .conftest import (
    GIT_SHIM_TEMPLATE,
    REPO_ROOT,
    install_git_shim,
    make_forwarding_git,
    run_git_via_shim,
)

pytestmark = [pytest.mark.coach]


@pytest.mark.parametrize(
    "args",
    [
        ["status"],
        ["config", "--worktree", "core.bare", "true"],  # scoped write must forward
        ["rev-parse", "HEAD"],
    ],
)
def test_shim_forwards_argv_stdout_stderr_exit(tmp_path, args) -> None:
    assert GIT_SHIM_TEMPLATE.exists(), f"RED: {GIT_SHIM_TEMPLATE.relative_to(REPO_ROOT)} not implemented yet"

    worktree = tmp_path / "gitwt"
    worktree.mkdir()
    install_git_shim(worktree)
    real_bin = tmp_path / "gitrealbin"
    record = make_forwarding_git(real_bin, exit_code=42)

    result = run_git_via_shim(worktree, real_bin, args)

    joined = " ".join(args)
    assert record.exists() and joined in record.read_text(), f"argv {args!r} not forwarded: {record.read_text() if record.exists() else '<no record>'!r}"
    assert result.returncode == 42, f"exit code not preserved: got {result.returncode}"
    assert result.stdout == f"OUT:{joined}", f"stdout not preserved: {result.stdout!r}"
    assert result.stderr == f"ERR:{joined}", f"stderr not preserved: {result.stderr!r}"
