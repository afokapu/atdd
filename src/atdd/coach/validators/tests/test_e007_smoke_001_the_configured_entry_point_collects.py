# URN: test:govern-lifecycle:govern-lifecycle:E007-SMOKE-001-the-configured-entry-point-collects
# Acceptance: acc:govern-lifecycle:E007-SMOKE-001-the-configured-entry-point-collects
# WMBT: wmbt:govern-lifecycle:E007
# Phase: SMOKE
# Layer: application
"""E007-SMOKE-001 — the command pyproject documents must collect the real suite.

Collects EXACTLY what ``testpaths`` configures, in one process, over this
repository. A fixture cannot stand in: the defect is a name collision between two
real trees, so a fixture would have to recreate the collision in order to detect
it, and would then be asserting the thing it was built from.

Collect-only, deliberately. The property under test is whether collection
completes; running 6000 tests to learn that would cost ~38 minutes and assert
nothing this does not already establish.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

# Measured on c0ecce6a, the revision this defect was found at: 6213 collected with
# 25 errors and collection interrupted. Anything at or below that count means the
# ambiguous tree is still winning the name.
_COUNT_BEFORE_FIX = 6213


def _collect(repo_root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly"],
        cwd=str(repo_root), env=env, capture_output=True, text=True, timeout=900,
    )


@pytest.mark.coder
@pytest.mark.platform
def test_the_configured_testpaths_collect_without_interruption():
    if not is_atdd_source_repo():
        pytest.skip("collects this repository's own configured suite")

    repo_root = Path(find_repo_root())
    result = _collect(repo_root)
    out = result.stdout + result.stderr

    assert "Interrupted" not in out, (
        "collection aborted, so the suite cannot be run by the command the "
        f"configuration documents:\n{out[-2000:]}"
    )
    assert "No module named 'tests." not in out, (
        "a module is still being named under the ambiguous top-level `tests` "
        f"package, which is the defect:\n{out[-2000:]}"
    )

    match = re.search(r"(\d+) tests collected", out)
    assert match, f"could not read a collection count from:\n{out[-1200:]}"
    collected = int(match.group(1))

    assert collected > _COUNT_BEFORE_FIX, (
        f"{collected} collected, but {_COUNT_BEFORE_FIX} were already reachable "
        "before this fix — the point is to RECOVER execution, not to silence the "
        "message while the same tests stay unrunnable"
    )
