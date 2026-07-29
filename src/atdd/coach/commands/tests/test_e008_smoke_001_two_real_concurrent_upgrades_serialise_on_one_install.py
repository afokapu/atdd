# URN: test:integration-hardening:run-upgrade-unattended:E008-SMOKE-001-two-real-concurrent-upgrades-serialise-on-one-install
# Acceptance: acc:integration-hardening:E008-SMOKE-001-two-real-concurrent-upgrades-serialise-on-one-install
# WMBT: wmbt:integration-hardening:E008
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-SMOKE-001 — two real concurrent upgrades serialise on one install.

Two `atdd upgrade --no-pypi` subprocesses launched simultaneously from two
distinct checkouts that share a single installed atdd. The real lock, unpatched.

`--no-pypi` keeps this off the network and away from mutating the shared venv,
so what is being proven is the serialisation of the local sync section — the
part that rewrites each checkout's stamp and re-runs sync + init --force.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform]


def _make_repo(root):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text("toolkit:\n  last_version: 0.0.1\n")
    return root


@pytest.mark.platform
def test_e008_smoke_001_two_real_concurrent_upgrades_serialise_on_one_install(tmp_path):
    repo_a = _make_repo(tmp_path / "worktree-a")
    repo_b = _make_repo(tmp_path / "worktree-b")

    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "atdd", "upgrade", "--no-pypi"],
            cwd=str(repo),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for repo in (repo_a, repo_b)
    ]

    outputs = []
    for proc in procs:
        out, err = proc.communicate(timeout=600)
        outputs.append((proc.returncode, out + err))

    for rc, combined in outputs:
        assert "EOFError" not in combined, (
            f"a concurrent no-TTY upgrade died on closed stdin:\n{combined}"
        )
        assert rc == 0, f"both concurrent upgrades must succeed; rc={rc}\n{combined}"

    # Neither run may report having proceeded without the lock, and neither may
    # report a half-applied sync.
    for rc, combined in outputs:
        assert "unlocked" not in combined.lower(), (
            f"a run proceeded without the lock:\n{combined}"
        )

    # Both checkouts end up stamped current — no partial install left behind.
    for repo in (repo_a, repo_b):
        stamp = (repo / ".atdd" / "config.yaml").read_text()
        assert "0.0.1" not in stamp, (
            f"{repo.name} was left on its stale stamp — the sync did not complete:\n{stamp}"
        )
