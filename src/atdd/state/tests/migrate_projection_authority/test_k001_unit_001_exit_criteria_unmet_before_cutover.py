# URN: test:migrate-projection-authority:plan-migration-rollout:K001-UNIT-001-exit-criteria-unmet-before-cutover
# Acceptance: acc:migrate-projection-authority:K001-UNIT-001-exit-criteria-unmet-before-cutover
# WMBT: wmbt:migrate-projection-authority:K001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A repo mid-migration — projection present, but a manifest read-fallback still resolves — fails the M8 cutover check, which names the unmet criterion; and each of the three criteria is shown to fail on its own, so the check cannot pass by ignoring one. Refs #1434.
"""The cutover check fails while any one exit criterion is unmet (K001-UNIT-001).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: RED
WMBT: wmbt:migrate-projection-authority:K001

A milestone whose exit criteria live only in a document is a milestone that gets declared done by
whoever is tired first. §14's three sentences — the projection is the shared state, GitHub is an
optional mirror, the manifest is no longer a fallback — are a check, and it fails while **any one**
of them is untrue.

The scenario the acceptance names is the dangerous one, and it is dangerous precisely because it
looks finished: the projection is there, it is canonical, everything works... and a reader still
falls back to the manifest, so two developers can still hold two different answers. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import cutover
from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import project

from ._helpers import UID_A, control_root, memory_store

_BASE = {"slug": "alpha", "owner_actor": "dev-a", "state": "ACTIVE", "wmbts": []}

#: A synthetic core package carrying exactly one flaw, so each criterion can be failed alone.
_CLEAN_MODULE = "PHASES = ()\n"
_MANIFEST_READER = (
    "from pathlib import Path\n"
    "import yaml\n"
    "def phase(root):\n"
    "    manifest = Path(root) / '.atdd' / 'manifest.yaml'\n"
    "    return yaml.safe_load(manifest.read_text())\n"
)
_GITHUB_READER = "from atdd.integrations.github import issue_state\n"


def _package(root: Path, **modules: str) -> Path:
    package = root / "atdd"
    (package / "state").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "state" / "__init__.py").write_text("")
    (package / "state" / "projection.py").write_text(_CLEAN_MODULE)
    for name, source in modules.items():
        (package / "state" / f"{name}.py").write_text(source)
    return package


def _repo_with_projection(root: Path) -> Path:
    """A Control Root carrying a canonical committed projection."""
    control_root(root)
    with memory_store() as (_conn, store):
        store.objects.upsert(UID_A, WORK_ITEM_KIND, state="PLANNED", data=dict(_BASE))
        project(store, root / ".atdd" / "state" / "projection")
    return root


def test_k001_unit_001_exit_criteria_unmet_before_cutover(tmp_path) -> None:
    """Mid-migration — projection present, manifest fallback alive — the cutover check fails."""
    # The scenario the acceptance names: everything LOOKS done. The projection is there and it is
    # canonical. And a core reader still falls back to the manifest.
    repo = _repo_with_projection(tmp_path / "mid-migration")
    package = _package(tmp_path / "pkg-manifest", authoring=_MANIFEST_READER)

    report = cutover.check(repo, package=package)

    assert not report.met
    assert report.exit_code == 1
    unmet = [criterion.name for criterion in report.unmet]
    assert unmet == [cutover.CRITERION_NO_MANIFEST_READ], unmet

    # It NAMES the unmet criterion, and names what is standing in the way — an operator staring at
    # a red cutover needs the criterion and the blocker, not a boolean.
    criterion = report.unmet[0]
    assert criterion.blockers
    assert "authoring" in criterion.blockers[0]
    rendered = report.render()
    assert "NOT COMPLETE" in rendered
    assert cutover.CRITERION_NO_MANIFEST_READ in rendered
    # ...and it still reports the two that DO pass, rather than stopping at the first failure.
    assert rendered.count("[PASS]") == 2

    # Each criterion fails on its own, so the check cannot pass by quietly ignoring one.

    # (a) no projection at all — the shared state does not exist yet. Deliberately NOT "canonical":
    #     an empty projection would round-trip vacuously, and a check that called that done would
    #     report M8 complete on a repo that had not started.
    empty = control_root(tmp_path / "no-projection")
    clean_pkg = _package(tmp_path / "pkg-clean")
    projectionless = cutover.check(empty, package=clean_pkg)
    assert [c.name for c in projectionless.unmet] == [cutover.CRITERION_PROJECTION]
    assert "does not exist yet" in projectionless.unmet[0].blockers[0]

    # (b) a lifecycle module reading GitHub.
    github = cutover.check(
        _repo_with_projection(tmp_path / "reads-github"),
        package=_package(tmp_path / "pkg-github", evidence=_GITHUB_READER),
    )
    assert [c.name for c in github.unmet] == [cutover.CRITERION_NO_HOT_PATH_READ]

    # (c) and all three at once — every one reported, none swallowed.
    everything = cutover.check(
        control_root(tmp_path / "nothing-done"),
        package=_package(tmp_path / "pkg-both",
                         evidence=_GITHUB_READER, authoring=_MANIFEST_READER),
    )
    assert len(everything.unmet) == 3
    assert {c.name for c in everything.unmet} == set(cutover.CRITERIA)
