# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:E062-UNIT-001-bind-rule-resolves-from-an-installed-wheel
# Acceptance: acc:govern-lifecycle:E062-UNIT-001-bind-rule-resolves-from-an-installed-wheel
# WMBT: wmbt:govern-lifecycle:E062
# Phase: GREEN
# Layer: backend.domain
# Assertion: behavioral
"""E062-UNIT-001 — `bind_rule()` resolves every coder/tester rule id from the wheel.

This is the concrete #1369 failure mode, asserted at its mechanism rather than at
its symptom. `coder/conventions/nodes/` and `tester/conventions/nodes/` were never
globbed into the wheel, so `bind_rule()` — which shipped validators call at MODULE
IMPORT — raised `RuleNotInRegistryError`. An import-time raise aborts pytest at
COLLECTION, so `atdd validate coder` in a consumer repo died before running a
single test.

The registry is resolved in a subprocess whose only `atdd` on the import path is
the UNPACKED WHEEL. That matters: with the source tree importable, a node file
that failed to ship would still be found, and the test would pass while the bug
stayed live.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ._wheel_harness import extracted_wheel_root, repo_root

pytestmark = [pytest.mark.coach]


_PROBE = """
import json, sys
from pathlib import Path
from atdd.coach.utils.rule_binding import bind_rule, RuleNotInRegistryError

import atdd
pkg = Path(atdd.__file__).resolve().parent

rule_ids = []
for phase in ("coder", "tester"):
    nodes = pkg / phase / "conventions" / "nodes"
    if not nodes.is_dir():
        continue
    for node in sorted(nodes.glob("*.convention.yaml")):
        for line in node.read_text().splitlines():
            if line.startswith("rule_id:"):
                rule_ids.append(line.split(":", 1)[1].strip())
                break

unbound = []
for rid in rule_ids:
    try:
        bind_rule(rid)
    except RuleNotInRegistryError:
        unbound.append(rid)

print(json.dumps({
    "package_dir": str(pkg),
    "resolved": len(rule_ids),
    "unbound": unbound,
}))
"""


def _source_node_rule_ids(phase: str) -> set[str]:
    nodes = repo_root() / "src" / "atdd" / phase / "conventions" / "nodes"
    ids = set()
    for node in nodes.glob("*.convention.yaml"):
        for line in node.read_text().splitlines():
            if line.startswith("rule_id:"):
                ids.add(line.split(":", 1)[1].strip())
                break
    return ids


def test_e062_unit_001_bind_rule_resolves_from_an_installed_wheel():
    wheel_root = extracted_wheel_root()

    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, cwd=wheel_root,
        env={"PYTHONPATH": str(wheel_root), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, (
        "resolving the rule registry against the unpacked wheel crashed — this is "
        "the #1369 import-time failure that aborts consumer pytest at collection:\n"
        f"{result.stdout}\n{result.stderr}"
    )

    probe = json.loads(result.stdout.strip().splitlines()[-1])

    # Guard against a vacuous pass: if the nodes did not ship at all, the probe
    # finds zero rule ids and trivially reports zero unbound.
    expected = _source_node_rule_ids("coder") | _source_node_rule_ids("tester")
    assert probe["resolved"] == len(expected), (
        f"the wheel exposes {probe['resolved']} coder+tester rule nodes but the "
        f"source tree declares {len(expected)} — the conventions/nodes/ trees did "
        f"not fully ship, so bind_rule() has nothing to resolve against. "
        f"Package dir under test: {probe['package_dir']}"
    )
    assert not probe["unbound"], (
        f"{len(probe['unbound'])} rule id(s) declared in the source tree do not "
        f"bind from the installed wheel (RuleNotInRegistryError at import — #1369):\n"
        + "\n".join(f"  {r}" for r in probe["unbound"][:15])
    )
