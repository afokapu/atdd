# URN: test:migrate-projection-authority:describe-migration-runbook:D001-SMOKE-001-migration-runbook
# Acceptance: acc:migrate-projection-authority:D001-SMOKE-001-migration-runbook
# WMBT: wmbt:migrate-projection-authority:D001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state runbook-check` command, run in a real checkout against the real authored docs/atdd-migration-runbook.md, exits 0; and against a runbook citing an invariant the spec does not declare, it exits non-zero and names it. Refs #1434.
"""SMOKE — the shipped command checks the real runbook (D001-SMOKE-001).

wagon: migrate-projection-authority | feature: describe-migration-runbook | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:D001

The unit tests check the runbook through the library. This checks it through the **command an
operator or a CI job would actually run**, in a real checkout, against the real authored document
and the real architecture spec — no fixtures, no patching. If `atdd state runbook-check` is wired
wrong, or the doc ships broken, this is what says so. Refs #1434 / #1400.
"""
from __future__ import annotations

import shutil

from ._live import REPO_ROOT, atdd_state


def test_d001_smoke_001_migration_runbook(tmp_path) -> None:
    """The real command passes against the real runbook, and bites when the runbook lies."""
    # A real checkout of the two documents the check reads.
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / ".atdd").mkdir()
    (repo / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    for name in ("atdd-migration-runbook.md", "atdd-state-projection-plan.md"):
        shutil.copy(REPO_ROOT / "docs" / name, repo / "docs" / name)

    passing = atdd_state(repo, "runbook-check")
    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert "covers all" in passing.stdout
    assert "migration step" in passing.stdout

    # Now make the runbook cite an invariant the spec does not declare, and drive the same command.
    runbook = repo / "docs" / "atdd-migration-runbook.md"
    runbook.write_text(
        runbook.read_text(encoding="utf-8").replace("**Invariant**: **I7**", "**Invariant**: **I42**"),
        encoding="utf-8",
    )
    failing = atdd_state(repo, "runbook-check")
    assert failing.returncode != 0, failing.stdout
    report = failing.stdout + failing.stderr
    assert "I42" in report, report
    assert "does not declare" in report
