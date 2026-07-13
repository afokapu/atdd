# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-SMOKE-001-lossy-migration-write
# Acceptance: acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state migrate-manifest` CLI, run against a real checkout with a real defective .atdd/manifest.yaml, exits NON-ZERO, names every offending entry on stderr, and leaves the working tree with no projection file at all (git reports nothing). Refs #1434.
"""SMOKE — the shipped command refuses a lossy migration and writes nothing (C001-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C001

The unit guard proves the function refuses. This proves the *shipped command* refuses — against a
real checkout, a real ``.atdd/manifest.yaml``, a real ``state.sqlite``, and the real
``.atdd/state/projection/`` an operator would then commit. The oracle for "wrote nothing" is git
itself: after the refusal, `git status --porcelain` over the projection path is empty, which is a
claim about the tree the operator is about to commit rather than about a Python object.
Refs #1434 / #1400.
"""
from __future__ import annotations

import yaml

from ._live import atdd_state, commit_all, make_checkout, porcelain

_PROJECTION = ".atdd/state/projection"


def _write_manifest(repo, sessions) -> None:
    (repo / ".atdd" / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "2.0", "sessions": sessions}, sort_keys=False),
        encoding="utf-8",
    )


def test_c001_smoke_001_lossy_migration_write(tmp_path) -> None:
    """The real CLI exits non-zero, names every defect, and leaves the tree without a projection."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    # A real manifest carrying all three defects at once.
    _write_manifest(repo, [
        {"id": "1", "slug": "clean", "uid": "wi_01HF7YAT00M78607F000000001", "status": "PLANNED"},
        {"id": "2", "slug": "no-uid", "status": "GREEN"},
        {"id": "3", "slug": "dupe", "uid": "wi_01HF7YAT00M78607F000000001", "status": "RED"},
        {"id": "4", "slug": "bad-phase", "uid": "wi_01HF7YAT00M78607F000000002",
         "status": "MARINATING"},
    ])
    commit_all(repo, "the legacy manifest, before migration")

    refused = atdd_state(repo, "migrate-manifest")

    assert refused.returncode != 0, refused.stdout + refused.stderr
    report = refused.stdout + refused.stderr
    assert "no projection file was written" in report
    # Every offending entry, in one refusal.
    for slug in ("no-uid", "dupe", "bad-phase"):
        assert slug in report, report
    assert "MARINATING" in report

    # The tree is untouched. Not "the projection is invalid" — there IS no projection, and git,
    # not the tool, is the one saying so.
    assert not (repo / _PROJECTION).exists()
    assert porcelain(repo) == "", "the refused migration left changes in the working tree"

    # And the refusal is not a one-off sulk: fixing the manifest lets the very same command through,
    # which is what makes the refusal a gate rather than a bug.
    _write_manifest(repo, [
        {"id": "1", "slug": "clean", "uid": "wi_01HF7YAT00M78607F000000001", "status": "PLANNED"},
    ])
    accepted = atdd_state(repo, "migrate-manifest")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert (repo / _PROJECTION / "wi_01HF7YAT00M78607F000000001.yaml").is_file()
