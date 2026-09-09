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

from atdd.enforce.conventions import is_interlocking_rule
from atdd.enforce.interlocking_layout import package_declares_interlocking_surfaces

pytestmark = [pytest.mark.platform]

#: The REPO ROOT — the value `runner` actually passes as ``substrate_home``; it
#: joins ``.atdd`` itself. Passing the already-joined path here is what let a
#: missing-segment bug pass every unit test while starving every rule in the real
#: run: the tests agreed with the code because both were given the same wrong shape.
_SUBSTRATE = Path(".")
_INTERLOCKING_PKGS = (
    "atdd.extension.coder.train-interlocking",
    "atdd.extension.tester.train-interlocking",
)


def _scope_selector_surfaces(pkg: str) -> set[str]:
    root = _SUBSTRATE / ".atdd" / "extensions" / pkg
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


def test_the_fix_feeds_rules_the_old_prefix_starved():
    """The regression this exists for, stated as a DELTA.

    A previous version of this test filtered the lock to the interlocking packages
    and then asked the package-level predicate about those same packages — which is
    true by construction and could never fail. It asserted nothing.

    The real claim is a difference between two predicates over the SAME bound rules:
    every rule these packages realize must be fed, and the retired name prefix fed
    only some. If the two ever agree, the fix has been reverted or the rule names
    have changed, and either way this must fail loudly rather than pass quietly.
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

    bound = [
        (str(e["convention_id"]), str(e.get("package_id") or ""))
        for e in walk(lock)
        if str(e.get("package_id") or "") in _INTERLOCKING_PKGS
    ]
    assert bound, "no interlocking rules bound — this test has nothing to police"

    fed_now = {r for r, pkg in bound if package_declares_interlocking_surfaces(_SUBSTRATE, pkg)}
    fed_before = {r for r, _ in bound if is_interlocking_rule(r)}

    # 1. every bound rule of a declaring package is fed
    assert fed_now == {r for r, _ in bound}, (
        f"still starved: {sorted({r for r, _ in bound} - fed_now)}"
    )
    # 2. and the retired predicate genuinely fed fewer — the delta is the point
    gained = fed_now - fed_before
    assert gained, (
        "the retired prefix already fed every bound rule; this fix is a no-op "
        "and the test's premise is stale"
    )
    # 3. name them, so a silent change in WHICH rules gain is visible in the diff
    assert gained == {
        "coder.train.runtime-executes-the-declaration",
        "coder.train.station-master-interlocking-routing",
        "tester.interlocking.production-runner-used",
        "tester.interlocking.route-coverage",
        "tester.interlocking.smoke-coverage-for-station-master",
        "tester.interlocking.trace-binds-declared-route",
        "tester.interlocking.train-sequence-is-exercised",
    }, f"the set of newly-fed rules changed: {sorted(gained)}"


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
