# URN: test:integration-hardening:run-upgrade-unattended:Y007-SMOKE-001-real-upgrade-with-stdin-closed-does-not-raise
# Acceptance: acc:integration-hardening:Y007-SMOKE-001-real-upgrade-with-stdin-closed-does-not-raise
# WMBT: wmbt:integration-hardening:Y007
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y007-SMOKE-001 — the field failure, reproduced against the real CLI and closed.

A real `atdd upgrade --no-pypi` subprocess with stdin=DEVNULL, so stdin
genuinely is not a terminal. Nothing inside the child is mocked: this is the
exact shape of the invocation that produced the traceback in #1628.

`--no-pypi` keeps the smoke off the network and away from the shared install —
it exercises the local sync branch, which carries the second of the two
unguarded input() calls.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform]


def _make_repo(root):
    """A minimal ATDD repo whose stamped version is stale."""
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text("toolkit:\n  last_version: 0.0.1\n")
    return root


@pytest.mark.platform
def test_y007_smoke_001_real_upgrade_with_stdin_closed_does_not_raise(tmp_path):
    repo = _make_repo(tmp_path / "consumer")

    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "upgrade", "--no-pypi"],
        cwd=str(repo),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
    )

    combined = proc.stdout + proc.stderr

    assert "EOFError" not in combined, (
        "the real CLI still dies on a closed stdin — this is the #1628 defect:\n"
        f"{combined}"
    )
    assert "EOF when reading a line" not in combined, (
        f"the field traceback is still reachable:\n{combined}"
    )
    assert proc.returncode == 0, (
        f"a no-TTY upgrade must complete; rc={proc.returncode}\n{combined}"
    )
    assert any(
        t in combined.lower() for t in ("no terminal", "not a terminal", "non-interactive")
    ), f"the run must state that it resolved the confirmation itself:\n{combined}"
