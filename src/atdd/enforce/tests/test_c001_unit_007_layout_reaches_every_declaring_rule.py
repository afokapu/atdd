# URN: component:code:enforce:InterlockingLayoutScope:backend:tests
# Runtime: python
# Purpose: the per-repo interlocking layout reaches every rule whose package declares it (#1867).
"""The layout is scoped by the DECLARING PACKAGE, not by the rule's name (#1867).

`is_interlocking_rule` said "the rules the detector realizes" and implemented
"ids starting with `coder.train.interlocking-`". Those agreed until the package
gained rules named otherwise. Seven bound rules were then starved of the repo's
declared scan surfaces and fell back to the detector's defaults —
`python/trains/**/*.py` and `python/app.py`, neither of which exists in this
repo, whose runtime is `src/atdd/runtime/interlocking/`.

A rule scanning globs that match nothing reports PASS having read no file. That
is the failure class #1818 was filed about, reached from inside core.

These tests pin the SCOPING DECISION — which rules receive the layout — not any
individual rule's verdict, which belongs to the vendored detector.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.enforce.conventions import (
    is_interlocking_rule,
    package_declares_interlocking_surfaces,
)

pytestmark = [pytest.mark.platform]

_SUBSTRATE = Path(".atdd")
_INTERLOCKING_PKGS = (
    "atdd.extension.coder.train-interlocking",
    "atdd.extension.tester.train-interlocking",
)


def _scope_selector_surfaces(pkg: str) -> set[str]:
    root = _SUBSTRATE / "extensions" / pkg
    out: set[str] = set()
    for scope in root.glob("*/scopes/*.yaml"):
        doc = yaml.safe_load(scope.read_text(encoding="utf-8")) or {}
        for sel in doc.get("selectors") or []:
            sid = (sel or {}).get("selector_id")
            if isinstance(sid, str):
                out.add(sid.rsplit(".", 1)[-1])
    return out


@pytest.mark.parametrize("pkg", _INTERLOCKING_PKGS)
def test_a_package_declaring_the_surfaces_receives_the_layout(pkg):
    assert _scope_selector_surfaces(pkg), f"{pkg} ships no scope selectors to key on"
    assert package_declares_interlocking_surfaces(_SUBSTRATE, pkg)


@pytest.mark.parametrize(
    "pkg",
    ["atdd.extension.coder.base", "atdd.extension.tester.base", "atdd.workspace.python-pytest"],
)
def test_an_unrelated_package_does_not_receive_the_layout(pkg):
    """Scoping must still be narrow — the env var never leaks onto unrelated rules."""
    assert not package_declares_interlocking_surfaces(_SUBSTRATE, pkg)


def test_an_absent_package_is_false_rather_than_raising():
    assert not package_declares_interlocking_surfaces(_SUBSTRATE, "no.such.package")


def test_every_bound_rule_of_a_declaring_package_receives_the_layout():
    """The regression this exists for.

    Reads the live binding lock: for every bound rule whose package declares the
    surfaces, the scoping predicate must say yes. Under the old name prefix seven
    rules said no — the two coder rules not named `interlocking-*`, and all five
    `tester.interlocking.*` rules, which that prefix can never match.
    """
    lock = yaml.safe_load(Path(".atdd/binding.lock.yaml").read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if "convention_id" in node:
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    starved = [
        entry["convention_id"]
        for entry in walk(lock)
        if str(entry.get("package_id") or "") in _INTERLOCKING_PKGS
        and not package_declares_interlocking_surfaces(
            _SUBSTRATE, str(entry.get("package_id") or "")
        )
    ]
    assert starved == [], f"bound rules starved of the declared layout: {starved}"


def test_the_retired_name_prefix_would_still_starve_those_rules():
    """Pins WHY the predicate changed, so nobody reverts it as redundant."""
    for rule_id in (
        "coder.train.runtime-executes-the-declaration",
        "coder.train.station-master-interlocking-routing",
        "tester.interlocking.route-coverage",
    ):
        assert not is_interlocking_rule(rule_id), (
            f"{rule_id} now matches the retired prefix; this test's premise is stale"
        )
