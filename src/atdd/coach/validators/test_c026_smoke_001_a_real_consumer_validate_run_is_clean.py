# URN: test:govern-lifecycle:govern-lifecycle:C026-SMOKE-001
# Acceptance: acc:govern-lifecycle:C026-SMOKE-001-a-real-consumer-validate-run-is-clean
# WMBT: wmbt:govern-lifecycle:C026
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
# Smoke: true

"""C026-SMOKE-001 — a real consumer repo's coach phase runs without toolkit paths.

C026-UNIT-001 pins the guard on the one validator that leaked. This pins the
OUTCOME, which is the thing a consumer cares about: run the real coach validators
as a real subprocess against a real repository that is not the toolkit, the way
that repo's `validate-coach` job runs them, and demand that nothing fails because
a toolkit-only path was missing.

It is deliberately not a whitelist of known-good validators. The leak class is
"a shipped validator reaches for `src/atdd/`", and any member of it produces the
same signature — a missing-path error naming the toolkit tree. Asserting on that
signature catches the next member too, which a per-validator assertion would not.

The subprocess is the point: this is what the consumer's CI job actually does, and
the defect was invisible to every in-process test in this repo because in THIS repo
the path exists.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

TARGET = "test_r005_smoke_001_real_validate_coach_enforces_projection_only.py"


def _consumer_repo(tmp_path: Path) -> Path:
    """A real repo that is emphatically not the toolkit checkout."""
    root = tmp_path / "consumer"
    (root / ".atdd").mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "T"]):
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    (root / "README.md").write_text("consumer\n", encoding="utf-8")

    # `src/` and `.github/` — because the guard being replaced keys on exactly
    # those two names to decide "this is a toolkit checkout". A consumer with a
    # `src/` directory and a CI workflow, which is most of them, sails past it.
    # This is the shape of the real repo the defect was found in: a Bun app with
    # `src/server.ts` and `.github/workflows/atdd-validate.yml`.
    (root / "src").mkdir()
    (root / "src" / "server.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "atdd-validate.yml").write_text(
        "name: ATDD Validate\non: [push]\njobs: {}\n", encoding="utf-8"
    )
    (root / "pyproject.toml").write_text("[project]\nname = 'consumer'\n", encoding="utf-8")

    assert not (root / "src" / "atdd").exists(), "the fixture must not be the toolkit"
    return root


def test_c026_smoke_001_a_real_consumer_validate_run_is_clean(tmp_path):
    """The leaking validator must DECLINE in a consumer repo, not fail there."""
    import os

    root = _consumer_repo(tmp_path)

    # The sibling in THIS tree, not `atdd.coach.validators.__path__` — that
    # resolves to whatever copy is importable, which under a pipx install is the
    # released package rather than the source under change. Targeting the sibling
    # is what makes this test able to fail: with the guards removed it must go red.
    target = Path(__file__).with_name(TARGET)
    assert target.is_file(), f"{TARGET} is missing beside this test"
    tree_src = target.parents[3]  # .../src

    # The consumer's own shape: a repo that is not the toolkit, the packaged
    # validator, no marker filter — a bare pytest, which is the harsher of the two
    # runners because it applies no `-m 'not platform'` exclusion.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(target),
         "-q", "-rs", "-p", "no:cacheprovider", "--no-header"],
        cwd=str(root), capture_output=True, text=True,
        env={**os.environ, "ATDD_REPO_ROOT": str(root), "PYTHONPATH": str(tree_src)},
    )
    combined = proc.stdout + proc.stderr

    assert proc.returncode == 0, (
        "the toolkit-self validator ran in a repo that is not the toolkit and "
        "failed there — this is what keeps validate-coach, and via the fan-in "
        f"validate-gate, permanently red in every consumer:\n{combined[-1500:]}"
    )
    assert "skipped" in combined, (
        f"{TARGET} neither skipped nor failed; it must DECLINE rather than pass "
        f"silently, or the guard is indistinguishable from the test not existing:\n{combined[-800:]}"
    )
    assert "toolkit-self" in combined, (
        "the skip reason does not say why, so a reader cannot tell a deliberate "
        f"toolkit-self decline from an accidental skip:\n{combined[-800:]}"
    )
