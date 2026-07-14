# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:E062-UNIT-001-bind-rule-resolves-from-an-installed-wheel
# Acceptance: acc:govern-lifecycle:E062-UNIT-001-bind-rule-resolves-from-an-installed-wheel
# WMBT: wmbt:govern-lifecycle:E062
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""E062-UNIT-001 — `bind_rule()` resolves from the wheel every id a validator binds.

This is the #1369 failure mode asserted at its mechanism rather than its symptom.
`coder/conventions/nodes/` and `tester/conventions/nodes/` were never globbed into
the wheel, so `bind_rule()` — which shipped validators call at MODULE SCOPE — raised
`RuleNotInRegistryError` during IMPORT. An import-time raise aborts pytest at
COLLECTION, so a consumer's `atdd validate coder` died before running a single test.

The population under test is *the rule ids shipped validators actually pass to
`bind_rule()`*, harvested from the shipped validator sources. Deliberately NOT
"every rule id declared in a node file": some declared ids do not bind even from the
source tree (`tester.coverage.every-acceptance-criterion-must` is one;
`coder.train.acceptance-commit-idempotent` is `status: draft`). That is pre-existing
repo debt with nothing to do with packaging, and asserting on it here would make this
test fail for a reason it does not own.

The registry is resolved in a subprocess whose only `atdd` on the import path is the
UNPACKED WHEEL. That matters: with the source tree importable, a node file that
failed to ship would still be found and the test would pass while the bug stayed live.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Set

import pytest

from ._wheel_harness import extracted_wheel_root, repo_root

pytestmark = [pytest.mark.coach]

_PHASES = ("coder", "tester")


def harvest_bind_rule_ids(source: str) -> Set[str]:
    """Rule ids passed to a real `bind_rule("...")` CALL in *source*.

    AST rather than regex: a regex also scrapes `bind_rule("...")` out of comments
    and docstrings — `coder/validators/test_duplication_detector.py` contains exactly
    that — and the placeholder would then be reported as an unbound rule.
    """
    ids: Set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ids
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "bind_rule":
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)
    return ids


# Same harvest, executed inside the wheel-only subprocess.
_PROBE = '''
import ast, json
from pathlib import Path

import atdd
from atdd.coach.utils.rule_binding import bind_rule, RuleNotInRegistryError


def harvest_bind_rule_ids(source):
    ids = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ids
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "bind_rule":
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            ids.add(first.value)
    return ids


pkg = Path(atdd.__file__).resolve().parent

bound_ids = set()
for phase in ("coder", "tester"):
    for src in sorted((pkg / phase / "validators").rglob("*.py")):
        bound_ids |= harvest_bind_rule_ids(src.read_text())

unbound = []
for rid in sorted(bound_ids):
    try:
        bind_rule(rid)
    except RuleNotInRegistryError:
        unbound.append(rid)

node_counts = {}
for phase in ("coder", "tester"):
    nodes = pkg / phase / "conventions" / "nodes"
    node_counts[phase] = len(list(nodes.glob("*.convention.yaml"))) if nodes.is_dir() else 0

print(json.dumps({
    "package_dir": str(pkg),
    "bind_rule_ids": sorted(bound_ids),
    "unbound": unbound,
    "node_counts": node_counts,
}))
'''


def _source_bind_rule_ids() -> Set[str]:
    """Every rule id the source tree's coder/tester validators bind at import."""
    ids: Set[str] = set()
    for phase in _PHASES:
        for src in (repo_root() / "src" / "atdd" / phase / "validators").rglob("*.py"):
            ids |= harvest_bind_rule_ids(src.read_text())
    return ids


def _source_node_counts() -> dict:
    counts = {}
    for phase in _PHASES:
        nodes = repo_root() / "src" / "atdd" / phase / "conventions" / "nodes"
        counts[phase] = len(list(nodes.glob("*.convention.yaml")))
    return counts


@pytest.fixture(scope="module")
def probe() -> dict:
    wheel_root = extracted_wheel_root()
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=wheel_root,
        env={"PYTHONPATH": str(wheel_root), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, (
        "resolving the rule registry against the unpacked wheel crashed — this is the "
        "#1369 import-time failure that aborts a consumer's pytest at collection:\n"
        f"{result.stdout}\n{result.stderr}"
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_e062_unit_001_conventions_nodes_ship_in_full(probe: dict):
    """The node trees ship — completely, not partially."""
    assert probe["node_counts"] == _source_node_counts(), (
        f"the wheel's coder/tester convention-node trees do not match the source "
        f"tree's: wheel={probe['node_counts']} source={_source_node_counts()}. These "
        f"are the files bind_rule() reads at import; a short count is #1369. "
        f"Package dir under test: {probe['package_dir']}"
    )


def test_e062_unit_001_bind_rule_resolves_from_an_installed_wheel(probe: dict):
    """Every id a shipped validator binds at import resolves from the wheel."""
    # Anti-vacuity: had the validator modules not shipped, the probe would harvest
    # zero ids and trivially report zero unbound.
    expected = _source_bind_rule_ids()
    assert expected, "no bind_rule() calls found in the source tree — harvest is broken"
    assert set(probe["bind_rule_ids"]) == expected, (
        f"the wheel's coder/tester validators bind a different id set than the source "
        f"tree's ({len(probe['bind_rule_ids'])} vs {len(expected)}) — the validator "
        f"modules did not ship intact, so this test would be asserting on nothing"
    )

    assert not probe["unbound"], (
        f"{len(probe['unbound'])} rule id(s) that shipped validators pass to "
        f"bind_rule() AT IMPORT do not resolve from the installed wheel. Each raises "
        f"RuleNotInRegistryError while pytest is still collecting, aborting the whole "
        f"sweep — this is #1369:\n"
        + "\n".join(f"  {r}" for r in probe["unbound"][:15])
    )
