# URN: test:project-shared-state:project-store:E001-SMOKE-001-cli-projects-real-store
# Acceptance: acc:project-shared-state:E001-SMOKE-001-cli-projects-real-store
# WMBT: wmbt:project-shared-state:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state project` CLI, run twice against a real .atdd/state/state.sqlite in a real checkout, writes byte-identical projection files named by uid. Refs #1433.
"""SMOKE — the real CLI projects a real store, deterministically (E001-SMOKE-001).

wagon: project-shared-state | feature: project-store | phase: SMOKE
WMBT: wmbt:project-shared-state:E001

Drives the installed-form CLI (``python -m atdd state ...``) by subprocess against
a real on-disk checkout and a real SQLite store — no fixtures, no patching. This is
the run that proves determinism outside the unit harness. Refs #1433 / #1400.
"""
from __future__ import annotations

from ._live import atdd_state, make_checkout


def test_e001_smoke_001_cli_projects_real_store(tmp_path) -> None:
    """Two real CLI projections of one real store produce byte-identical files."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--title", "Feature X")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    first = atdd_state(repo, "project", "--out", str(tmp_path / "one"))
    second = atdd_state(repo, "project", "--out", str(tmp_path / "two"))
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    # Projection files appear named by uid — the uid alone, never the slug.
    one = sorted((tmp_path / "one").glob("*.yaml"))
    two = sorted((tmp_path / "two").glob("*.yaml"))
    assert [p.name for p in one] == [f"{uid}.yaml"]
    assert [p.name for p in two] == [f"{uid}.yaml"]
    assert not list((tmp_path / "one").glob("*feature-x*"))

    # The two runs produce byte-identical files, proving determinism outside the
    # test fixtures.
    assert one[0].read_bytes() == two[0].read_bytes()
