# URN: test:govern-lifecycle:deprecate-issue-create-alias:E061-SMOKE-001-real-cli-create-by-slug-warns
# Acceptance: acc:govern-lifecycle:E061-SMOKE-001-real-cli-create-by-slug-warns
# WMBT: wmbt:govern-lifecycle:E061
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E061-SMOKE-001 — the real `atdd issue <slug>` CLI create-by-slug surface warns.

Real infra: a genuine `python -m atdd issue <slug>` subprocess, exercised via
``--dry-run`` (ATDD_DRY_RUN=1) so it runs hermetically without filing a GitHub
issue — mirroring the sibling E019 issue-author smoke. The deprecated
create-by-slug alias must emit a stderr deprecation warning naming
`atdd author issue` and exit 0, with the warning on stderr (not the rendered
body payload on stdout). Part of the `atdd issue` decommission (#1349);
prerequisite #1272.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]


def _repo_root() -> Path:
    here = Path(__file__)
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


@pytest.mark.smoke
def test_e061_smoke_001_real_cli_create_by_slug_warns():
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["ATDD_DRY_RUN"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "issue", "smoke-e061-deprecation-alias", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=env,
    )

    # C5b (#1309): the alias is REMOVED. It must refuse, never silently create.
    assert result.returncode != 0, (
        f"the removed `atdd issue <slug>` alias must exit non-zero; got "
        f"{result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The real CLI still points operators at the canonical create, on stderr.
    assert "author issue" in result.stderr, (
        "the real `atdd issue <slug>` CLI must point operators to `atdd author "
        f"issue` on stderr; stderr was:\n{result.stderr!r}"
    )
    assert "REMOVED" in result.stderr
    # The notice must not pollute stdout.
    assert "author issue" not in result.stdout, (
        "the notice must go to stderr, not the stdout payload"
    )
