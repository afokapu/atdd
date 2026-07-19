# URN: test:govern-lifecycle:R005-SMOKE-001-real-validate-coach-enforces-projection-only
# Acceptance: acc:govern-lifecycle:R005-SMOKE-001-real-validate-coach-enforces-projection-only
# WMBT: wmbt:govern-lifecycle:R005
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""R005-SMOKE-001 — against REAL infrastructure (a real ``pytest`` subprocess
running the real validator against a real workflow file), the projection-only
rule is actually collected, actually executed, and actually goes red when the
deleted label-swap step is planted back.

Why a subprocess and not an in-process call: everything about this bug was a
thing that *looked* enforced. The phase machine was enforced — against humans.
auto-phase was correct — and outrun. #1434 deleted the writer — in three new
files, not the one it lived in. A validator that is never observed failing under
the real runner is the same category of comfort.

So the guarantee is bought twice over:

  * the CLEAN run must PASS **and** report the validator as collected — a
    silently-skipped guard passes too, and passes forever;
  * the PLANTED run must FAIL, naming the rule and the planted ``file:line``,
    under the real strict disposition gate.

Issue #1452.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach, pytest.mark.slow]

REPO_ROOT = find_repo_root()
VALIDATOR = "src/atdd/coach/validators/test_phase_label_projection_only.py"
TEST_NAME = "test_no_raw_atdd_phase_label_writes_outside_issue_manager"

# The step deleted from post-merge-lifecycle.yml in #1452, verbatim.
_PLANTED_STEP = """
      - name: Swap labels to atdd:COMPLETE
        run: |
          for PHASE in INIT PLANNED RED GREEN SMOKE REFACTOR BLOCKED; do
            gh issue edit "$ISSUE" --repo "$REPO" --remove-label "atdd:${PHASE}"
          done
          gh issue edit "$ISSUE" --repo "$REPO" --add-label "atdd:COMPLETE"
"""


def _run_validator(cwd: Path) -> subprocess.CompletedProcess:
    """Run the real validator as a real pytest subprocess rooted at *cwd*."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", VALIDATOR, "-v", "-p", "no:randomly"],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(cwd / "src"), "PATH": __import__("os").environ["PATH"]},
    )


@pytest.fixture(scope="module")
def scratch_repo(tmp_path_factory) -> Path:
    """A real checkout copy: src/, .github/workflows/, and the conventions."""
    dest = tmp_path_factory.mktemp("r005_smoke") / "repo"
    dest.mkdir(parents=True)
    for rel in ("src", ".github"):
        src = REPO_ROOT / rel
        if not src.exists():
            pytest.skip(f"{rel}/ absent — not a toolkit checkout")
        shutil.copytree(src, dest / rel)
    # find_repo_root anchors on these; without them the copy is not a repo.
    for marker in ("pyproject.toml", ".atdd"):
        src = REPO_ROOT / marker
        if src.is_dir():
            shutil.copytree(src, dest / marker, dirs_exist_ok=True)
        elif src.exists():
            shutil.copy2(src, dest / marker)
    (dest / ".git").mkdir(exist_ok=True)
    return dest


def test_clean_tree_passes_and_the_validator_actually_ran(scratch_repo):
    """The guard is collected and executed — not skipped into a green lie."""
    proc = _run_validator(scratch_repo)
    assert proc.returncode == 0, (
        "The projection-only validator must PASS on a clean tree.\n"
        f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-2000:]}"
    )
    assert f"{TEST_NAME} PASSED" in proc.stdout, (
        "The repo-wide sweep did not report as PASSED under the real runner — "
        "it was skipped, deselected or never collected, which is how a guard "
        f"stays green forever without ever running.\nstdout:\n{proc.stdout[-4000:]}"
    )


def test_planted_raw_label_writer_turns_the_real_run_red(scratch_repo):
    """Fault injection through the real runner: replant the step, expect red."""
    victim = scratch_repo / ".github" / "workflows" / "post-merge-lifecycle.yml"
    if not victim.exists():
        pytest.skip("post-merge-lifecycle.yml absent in this checkout")

    original = victim.read_text()
    victim.write_text(original + _PLANTED_STEP)
    try:
        # The fault must actually be present — a regex that silently no-ops
        # would otherwise let this test "pass" by proving nothing (see the
        # fail-open trap these injections are prone to).
        assert "--add-label \"atdd:COMPLETE\"" in victim.read_text(), (
            "The planted step did not land in the workflow file."
        )
        proc = _run_validator(scratch_repo)
    finally:
        victim.write_text(original)

    assert proc.returncode != 0, (
        "Replanting the raw `gh issue edit --add-label atdd:COMPLETE` step left "
        "the real validator run GREEN. The guard cannot fail, so it is a stub — "
        "and the writer it is meant to stop already regrew once, through "
        f"#1434.\nstdout:\n{proc.stdout[-4000:]}"
    )
    combined = proc.stdout + proc.stderr
    assert "coach.phase-label.projection-only" in combined, (
        "The failure must name the rule so the operator knows which convention "
        f"fired.\nstdout:\n{proc.stdout[-4000:]}"
    )
    assert "post-merge-lifecycle.yml:" in combined, (
        "The failure must name the offending file:line.\n"
        f"stdout:\n{proc.stdout[-4000:]}"
    )
