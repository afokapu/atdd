# URN: test:bind-substrate-runtime:bind-substrate-runtime:L002-UNIT-002
# Acceptance: acc:bind-substrate-runtime:L002-UNIT-002-a-run-names-the-substrate-it-enforced
# WMBT: wmbt:bind-substrate-runtime:L002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""L002-UNIT-002 — a run must name the substrate whose rules it enforced.

Writing L002-UNIT-001 exposed the fallback's real shape, which is worse than
"enforces nothing". When a repo's own lock is unreachable, `resolve_substrate_home`
falls through to the TOOLKIT install — and if that install is itself a bound repo,
enforcement reads ITS rule set and runs it over the caller's code:

    enforce verdict: PASS — 64 rule(s) enforced, 0 failed

Sixty-four rules belonging to a different repository, applied to a directory that
never admitted them, reported as this repo's clean result. `no bound conventions`
was only the pipx-install presentation of the same fallback.

So the obligation is not "say something when the set is empty" — it is: whenever
the rules came from somewhere other than this repo, say where from. That is one
line, and it is the difference between a false pass and a legible one.

Phase RED: the report names no substrate home in either case.
Phase GREEN: it names the home, and flags a home that is not this repo's.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]


def _git(*args: str, cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {' '.join(args)} failed: {r.stderr}"


def _repo_without_a_lock(tmp_path: Path) -> Path:
    root = tmp_path / "solo"
    root.mkdir()
    _git("init", "-q", "-b", "main", cwd=root)
    (root / ".atdd").mkdir()
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    return root


def test_l002_unit_002_a_run_names_the_substrate_it_enforced(tmp_path):
    from atdd.enforce.runner import enforce, resolve_substrate_home

    root = _repo_without_a_lock(tmp_path)
    home = resolve_substrate_home(root)

    # Precondition: this fixture is exactly the case the defect produced — the
    # substrate home is NOT the repo under inspection.
    assert home != root

    report = enforce(root).report
    assert str(home) in report, (
        "the report does not name the substrate home its rules came from, so a "
        "result computed against another repository's lock is indistinguishable "
        "from this repo's own clean result"
    )


def test_l002_unit_002_a_foreign_substrate_is_flagged_not_merely_named(tmp_path):
    """Naming is necessary; flagging is what makes it read as wrong at a glance."""
    from atdd.enforce.runner import enforce, resolve_substrate_home

    root = _repo_without_a_lock(tmp_path)
    assert resolve_substrate_home(root) != root

    report = enforce(root).report.lower()
    assert "not this repo" in report or "toolkit" in report, (
        "a substrate belonging to a different repository was used without the "
        "report saying so — the operator reads a PASS and has no way to know "
        "whose rules produced it"
    )


def test_l002_unit_002_a_local_substrate_is_not_flagged(tmp_path):
    """The flag must mean something: a repo enforcing its OWN lock says nothing."""
    from atdd.enforce.runner import enforce, resolve_substrate_home

    root = _repo_without_a_lock(tmp_path)
    (root / ".atdd" / "binding.lock.yaml").write_text(
        "schema_version: 1.0.0\nconventions: []\n", encoding="utf-8"
    )
    assert resolve_substrate_home(root) == root

    report = enforce(root).report.lower()
    assert "not this repo" not in report, (
        "a repo enforcing its own substrate was flagged as foreign, which would "
        "train operators to ignore the warning"
    )
