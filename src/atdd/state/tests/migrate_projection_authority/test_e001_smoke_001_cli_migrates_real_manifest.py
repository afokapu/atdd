# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-SMOKE-001-cli-migrates-real-manifest
# Acceptance: acc:migrate-projection-authority:E001-SMOKE-001-cli-migrates-real-manifest
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state migrate-manifest --mint-uids` CLI turns a real repo's populated .atdd/manifest.yaml into a committed .atdd/state/projection/ tree of one <uid>.yaml per work item, each naming its GitHub issue from the quarantined external_refs table (#2025) and none carrying issue_number in its data bag; re-running it is a no-op (git reports no diff) and `atdd state canonicality` passes over the produced tree. Refs #1434, #2025.
"""SMOKE — the shipped CLI migrates a real manifest into a canonical projection (E001-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:E001

The three claims an operator following the runbook is betting on, driven through the real command
against a real checkout:

1. the manifest becomes a projection tree, one ``<uid>.yaml`` per work item;
2. running it again changes nothing — and **git** is the oracle for that, not the tool's own report;
3. the tree it produced passes the gate that will later block merges (``atdd state canonicality``).

Claim 3 is the load-bearing one. A migration that produces a tree the canonicality gate then
rejects has not migrated anything; it has manufactured a merge blocker. Refs #1434 / #1400.
"""
from __future__ import annotations

import yaml

from ._live import atdd_state, commit_all, make_checkout, porcelain

_PROJECTION = ".atdd/state/projection"


def test_e001_smoke_001_cli_migrates_real_manifest(tmp_path) -> None:
    """A real manifest → a canonical, idempotent, uid-keyed committed projection."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    # A real, populated legacy manifest — no uids, exactly as a live repo's looks. One entry is
    # COMPLETE, which every real manifest has and which the projection may never carry.
    (repo / ".atdd" / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "2.0", "sessions": [
            {"id": "11", "slug": "add-widget", "issue_number": 11, "status": "PLANNED",
             "type": "implementation", "train": "train:commons:spine"},
            {"id": "12", "slug": "fix-gadget", "issue_number": 12, "status": "GREEN",
             "type": "implementation"},
            {"id": "13", "slug": "shipped-thing", "issue_number": 13, "status": "COMPLETE",
             "type": "implementation"},
        ]}, sort_keys=False),
        encoding="utf-8",
    )
    commit_all(repo, "the legacy manifest")

    migrated = atdd_state(repo, "migrate-manifest", "--mint-uids")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr

    # One <uid>.yaml per LIVE work item. The COMPLETE one is archived, not projected: COMPLETE is
    # derived from merge-to-main (§18 decision 1), so it has no legal projection document, and
    # fabricating a phase for it would be the lossy write C001 refuses.
    files = sorted(p.name for p in (repo / _PROJECTION).glob("*.yaml"))
    assert len(files) == 2, files
    assert all(name.startswith("wi_") for name in files), files
    assert "archived" in migrated.stdout and "shipped-thing" not in "".join(files)

    # The GitHub issue number IS in the projection, and the quarantine that put it there still
    # holds. These used to be the same assertion inverted: this test asserted `external_refs`
    # was absent, on the #1622 ruling that a core commit writing a bot-owned field is the wrong
    # writer (§7.1). #2025 SUPERSEDED the premise that ruling rested on — the committed
    # projection is now the transport to GitHub, and a document that cannot say which issue it
    # is gives the reconciliation workflow nothing to reconcile. See the supersession addendum
    # in docs/1400-findings/1622-projection-authority-ruling.md.
    #
    # The ruling's NARROW rule survives untouched, and the second half of this check is what
    # pins it: core still does not AUTHOR provider identity into the data bag. The migration
    # quarantines the issue number in the external_refs TABLE, exactly as before, and the
    # projector reads it back out of that table. Carried, never authored.
    for name in files:
        document = yaml.safe_load((repo / _PROJECTION / name).read_text(encoding="utf-8"))
        refs = document.get("external_refs")
        assert refs is not None, f"{name} names no GitHub issue, so it cannot be the transport"
        issue = refs.get("github", {}).get("issue")
        assert isinstance(issue, str) and issue.isdigit(), (
            f"{name} must carry its issue as a digit string, got {issue!r}"
        )
        assert "issue_number" not in document, (
            f"{name} carries issue_number in the data bag — the quarantine is broken; the "
            "identity must live in the external_refs table and be projected from there"
        )
    assert "quarantined in the store" in migrated.stdout

    commit_all(repo, "migrate the manifest into the committed projection")

    # Re-running is a NO-OP, and git says so — not the tool.
    again = atdd_state(repo, "migrate-manifest")
    assert again.returncode == 0, again.stdout + again.stderr
    assert porcelain(repo, [_PROJECTION]) == "", "re-running the migration changed the tree"

    # And the tree it produced passes the gate that will later block merges.
    canonical = atdd_state(repo, "canonicality")
    assert canonical.returncode == 0, canonical.stdout + canonical.stderr
    assert "is canonical" in canonical.stdout
