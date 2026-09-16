# URN: test:migrate-projection-authority:compare-shadow-projection:M001-SMOKE-002-dead-run-exits-zero-and-says-so
# Acceptance: acc:migrate-projection-authority:M001-SMOKE-002-dead-run-exits-zero-and-says-so
# WMBT: wmbt:migrate-projection-authority:M001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state shadow`, against a real store that cannot be projected, exits 0 and writes a report that names the failure; and the CI step that publishes it cannot render that failure as an empty, clean-looking drift block. Refs #2023.
"""SMOKE — a run that could not happen exits zero and says so (M001-SMOKE-002).

wagon: migrate-projection-authority | feature: compare-shadow-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:M001

Shadow mode's whole value is that it is believed. `SHADOW_EXIT_CODE` is declared a constant "so the
CLI, the workflow and the tests all read the same number and none of them can drift from it" — and
before #2023 the store side escaped as a traceback and exited 1 anyway, because `project(store)` is
computed above the per-source loop and outside any handler.

CI then laundered it. No `pipefail`, so the step's status was `tee`'s; the traceback went to stderr,
which `tee` never captured; and the summary's `|| echo '(no report produced)'` fallback never fired,
because `cat` on an empty-but-present file succeeds. The published summary was an empty code block
under a heading saying the job reports rather than gates — indistinguishable from zero drift.

This acceptance drives the real command against a real store that cannot be projected, then replays
the workflow step verbatim, because the defect lived as much in the shell as in the Python. Refs
#2023 / #1434.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from ._live import atdd_state, make_checkout

#: The shape of the real fault: 195 of 1265 objects in the toolkit's own store carry one of these.
_ABSOLUTE_HOST_PATH = "/Users/someone/Github/atdd/worktrees/feat-alpha"


def _repo_with_an_unprojectable_store(tmp_path):
    """A real checkout whose store holds one object the projection guard must refuse."""
    repo = make_checkout(tmp_path / "repo")
    seed = (
        "from pathlib import Path\n"
        "from atdd.state.db import connect, init_state_store\n"
        "from atdd.state.store import StateStore\n"
        "from atdd.state.manifest_import import WORK_ITEM_KIND\n"
        f"conn = connect(init_state_store(start=Path({str(repo)!r})))\n"
        "StateStore(conn).objects.upsert(\n"
        "    'wi_01HF7YAT00M78607F000000001', WORK_ITEM_KIND, state='PLANNED',\n"
        "    data={'slug': 'alpha', 'owner_actor': 'dev-a', 'state': 'ACTIVE', 'wmbts': [],\n"
        f"          'worktree_path': {_ABSOLUTE_HOST_PATH!r}}},\n"
        ")\n"
        "conn.commit()\n"
    )
    (repo / "_seed.py").write_text(seed)
    from ._live import _SRC

    done = subprocess.run(
        [sys.executable, str(repo / "_seed.py")],
        env={"PYTHONPATH": str(_SRC), "HOME": str(repo), "CI": "true"},
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return repo


@pytest.mark.smoke
def test_m001_smoke_002_the_real_command_exits_zero_and_reports(tmp_path) -> None:
    """Exit 0, and a report that names the failure instead of a traceback."""
    repo = _repo_with_an_unprojectable_store(tmp_path)
    result = atdd_state(repo, "shadow")

    assert result.returncode == 0, (
        "shadow exited non-zero on a store it could not project — SHADOW_EXIT_CODE is the "
        f"invariant on every path (M001):\n{result.stdout}{result.stderr}"
    )
    assert result.stdout.strip(), (
        "shadow wrote nothing to stdout; the report IS the deliverable, and an empty one is "
        f"indistinguishable from a clean one:\n{result.stderr}"
    )
    assert "COULD NOT RUN" in result.stdout
    assert "worktree_path" in result.stdout, (
        f"the report does not name the offending field:\n{result.stdout}"
    )
    assert "no drift" not in result.stdout, (
        f"a run that compared nothing reported 'no drift':\n{result.stdout}"
    )
    assert "Traceback" not in result.stderr


@pytest.mark.smoke
def test_m001_smoke_002_the_ci_step_cannot_launder_it(tmp_path) -> None:
    """Replay the workflow step verbatim: the published summary must not look clean."""
    repo = _repo_with_an_unprojectable_store(tmp_path)
    from ._live import _SRC

    step = (
        "set -o pipefail\n"
        f"{sys.executable} -m atdd state shadow --root . 2>&1 | tee shadow-report.txt\n"
        "echo \"STEP_EXIT=$?\"\n"
        "if [ -s shadow-report.txt ]; then cat shadow-report.txt; "
        "else echo '(no report produced — the shadow command wrote nothing; treat as FAILED TO RUN)'; fi\n"
    )
    done = subprocess.run(
        ["bash", "-c", step], cwd=str(repo),
        env={"PYTHONPATH": str(_SRC), "PATH": "/usr/bin:/bin", "HOME": str(repo), "CI": "true"},
        capture_output=True, text=True, timeout=180,
    )
    published = (repo / "shadow-report.txt").read_text()

    assert "STEP_EXIT=0" in done.stdout, f"the CI step failed the build:\n{done.stdout}{done.stderr}"
    assert published.strip(), "the published report is empty — exactly the laundering #2023 closed"
    assert "COULD NOT RUN" in published, f"the summary would not show the failure:\n{published}"
    assert "no drift" not in published
