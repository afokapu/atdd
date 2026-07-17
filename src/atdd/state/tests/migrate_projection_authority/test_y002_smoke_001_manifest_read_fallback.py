# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-SMOKE-001-manifest-read-fallback
# Acceptance: acc:migrate-projection-authority:Y002-SMOKE-001-manifest-read-fallback
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state manifest-fallback` command exits 0 against this checkout; and in a real checkout with NO .atdd/manifest.yaml, every core lifecycle command still succeeds, while a repo carrying a real manifest reader is refused by the shipped command, which names the file and line. Refs #1434.
"""SMOKE — the shipped command proves the fallback is gone (Y002-SMOKE-001).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:Y002

Three things, through the real command surface:

1. the guard passes against **this** checkout — the tree that actually ships;
2. a real repo with **no manifest at all** runs the whole lifecycle without one, which is the claim
   Y002 makes and the one an operator following the runbook is about to bet on when they type
   ``git rm .atdd/manifest.yaml``;
3. the guard **bites**: pointed at a package carrying a genuine manifest reader, the shipped command
   exits non-zero and names the file and the line, because a guard nobody has seen fail is a guard
   nobody has tested. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from ._live import atdd_state, make_checkout


def _package_with_a_reader(root: Path) -> Path:
    """A synthetic core package whose coach command still falls back to the manifest."""
    package = root / "atdd"
    (package / "coach" / "commands").mkdir(parents=True)
    for init in ("__init__.py", "coach/__init__.py", "coach/commands/__init__.py"):
        (package / init).write_text("")
    (package / "coach" / "commands" / "issue.py").write_text(
        "from pathlib import Path\n"
        "import yaml\n"
        "class IssueManager:\n"
        "    def __init__(self, root):\n"
        "        self.manifest_file = Path(root) / '.atdd' / 'manifest.yaml'\n"
        "    def status(self, n):\n"
        "        with open(self.manifest_file) as f:\n"
        "            manifest = yaml.safe_load(f)\n"
        "        for s in manifest['sessions']:\n"
        "            if s['issue_number'] == n:\n"
        "                return s['status']\n"
    )
    return package


def test_y002_smoke_001_manifest_read_fallback(tmp_path) -> None:
    """The real command passes on this tree, the lifecycle runs manifest-less, and the guard bites."""
    repo = make_checkout(tmp_path / "repo")

    # (1) The guard passes against the tree that actually ships.
    passing = atdd_state(repo, "manifest-fallback")
    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert "no core reader consults" in passing.stdout

    # (2) The whole lifecycle runs with NO manifest — which is the bet `git rm` is asking for.
    assert not (repo / ".atdd" / "manifest.yaml").exists()
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "widget", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    # (`hydrate` is deliberately absent: it refuses a store carrying un-replayed local overlay
    # events, which this one does. That is wagon 2's dirty-store gate (I5) doing its job, and it has
    # nothing to do with the manifest — K001-SMOKE-001 drives hydrate from the checkout where it is
    # the right call, which is the one PULLING a projection rather than authoring it.)
    for step in (
        ("project",),
        ("canonicality",),
        ("digest",),
        ("shadow",),
        ("object", "rename", uid, "--slug", "widget-v2"),
        ("project",),
        ("canonicality",),
        ("cutover",),
    ):
        result = atdd_state(repo, *step)
        assert result.returncode == 0, (
            f"`atdd state {' '.join(step)}` failed with the manifest absent: "
            f"{result.stdout}{result.stderr}"
        )
    assert not (repo / ".atdd" / "manifest.yaml").exists(), (
        "a core command RECREATED the manifest — the mirror is not decommissioned"
    )

    # (3) The guard bites: a package carrying a real manifest reader is refused, by file and line.
    package = _package_with_a_reader(tmp_path / "regressed")
    refused = atdd_state(repo, "manifest-fallback", "--package", str(package))
    assert refused.returncode != 0, refused.stdout
    report = refused.stdout + refused.stderr
    assert "atdd.coach.commands.issue" in report, report
    assert "manifest-read" in report
    assert "removed, not deprecated in place" in report
