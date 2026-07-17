# URN: test:migrate-projection-authority:remove-github-reads:Y001-UNIT-001-static-scan-finds-no-provider-read
# Acceptance: acc:migrate-projection-authority:Y001-UNIT-001-static-scan-finds-no-provider-read
# WMBT: wmbt:migrate-projection-authority:Y001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A static import-boundary scan over the core lifecycle DECISION modules — phase transitions, gates, validators — finds no module that imports a GitHub client, shells out to `gh`, or makes a provider HTTP call; and the scan is proven to BITE by planting each of those three violations in a synthetic package. Refs #1434.
"""No lifecycle decision, gate or validator calls the GitHub API (Y001-UNIT-001).

wagon: migrate-projection-authority | feature: remove-github-reads | phase: RED
WMBT: wmbt:migrate-projection-authority:Y001

The RED this closes was real and it was load-bearing: ``train.persistence.materialize_evidence``
asked the GitHub adapter for the live phase **label** and let it overrule the phase the store held.
A gate that lets the mirror outvote the source of truth is a gate GitHub can be wrong about, an
outage can block, and a rate limit can make non-deterministic (I7).

The guard is **static** — it parses source and imports nothing — and that is not an optimisation.
A guard written as ``try: import github / except ImportError: pass`` passes on any machine where
the provider merely is not installed, which is every runner core has, which means it would have
proved nothing at all.

A guard that has never failed is a guard nobody has tested, so the second half of this test plants
each of the three violations in a synthetic package and proves the scan catches each one.
Refs #1434 / #1400.
"""
from __future__ import annotations

from atdd.state import hot_path

_LIFECYCLE = "from atdd.state import projection\n"


def _package(root, **modules):
    """A synthetic ``atdd``-shaped package with one decision module, plus whatever else is named."""
    package = root / "atdd"
    (package / "state").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "state" / "__init__.py").write_text("")
    (package / "state" / "projection.py").write_text("PHASES = ()\n")
    for name, source in modules.items():
        (package / "state" / f"{name}.py").write_text(source)
    return package


def test_y001_unit_001_static_scan_finds_no_provider_read(tmp_path) -> None:
    """The real decision surface is GitHub-free — and the scan that says so demonstrably bites."""
    # The real thing: every declared decision module, walked transitively.
    report = hot_path.check()
    assert report.ok, report.render()
    assert report.roots, "the guard covers no decision module — it would pass vacuously"
    assert not report.missing, f"a declared decision module is absent: {report.missing}"

    # The surface really does include the gates and validators, not just `atdd.state`.
    assert "atdd.train.persistence" in report.roots
    assert "atdd.coach.runtime.graph" in report.roots
    assert "atdd.tester.validators._acceptance_walker" in report.roots
    assert "atdd.state.work_item_reader" in report.roots

    # Now prove it BITES, once per rule, in a synthetic package.
    modules = ("projection",)

    # (1) importing a GitHub client.
    package = _package(tmp_path / "api", gate=_LIFECYCLE + "import github\n")
    caught = hot_path.check(package, modules=("state.gate",))
    assert not caught.ok
    assert caught.violations[0].rule == hot_path.RULE_GITHUB_API

    # (2) shelling out to `gh` — a GitHub dependency spelled without an import, and the one an
    #     import-only check sails straight past.
    package = _package(
        tmp_path / "shell",
        gate=_LIFECYCLE + "import subprocess\n"
                          "def phase(n):\n"
                          "    return subprocess.run(['gh', 'issue', 'view', str(n)])\n",
    )
    caught = hot_path.check(package, modules=("state.gate",))
    assert not caught.ok
    assert caught.violations[0].rule == hot_path.RULE_GH_SHELL_OUT

    # (3) reading GitHub's own lifecycle opinion — the labels — as code.
    package = _package(
        tmp_path / "labels",
        gate=_LIFECYCLE + "def phase(issue):\n    return issue.issue_labels[0]\n",
    )
    caught = hot_path.check(package, modules=("state.gate",))
    assert not caught.ok
    assert caught.violations[0].rule == hot_path.RULE_GITHUB_IDENTIFIER

    # (4) TRANSITIVELY: a gate that imports a core helper that imports the provider is just as
    #     dependent as one that typed it itself. This is the case a direct-import check misses.
    package = _package(
        tmp_path / "transitive",
        gate=_LIFECYCLE + "from atdd.state import helper\n",
        helper="from atdd.integrations.github import issue_state\n",
    )
    caught = hot_path.check(package, modules=("state.gate",))
    assert not caught.ok
    assert any(v.rule == hot_path.RULE_GITHUB_API and v.module == "atdd.state.helper"
               for v in caught.violations), [v.render() for v in caught.violations]

    # And the seam is NOT a violation: reaching the SyncProvider registry is the sanctioned path —
    # that is what having built a seam is FOR. Refusing it here would make the boundary unusable.
    package = _package(tmp_path / "seam", gate=_LIFECYCLE + "from atdd.state import providers\n")
    (package / "state" / "providers.py").write_text("def discover_providers():\n    return {}\n")
    assert hot_path.check(package, modules=("state.gate",)).ok
    assert modules == ("projection",)
