# URN: test:govern-providers:E002-UNIT-001-orphan-binding-detected
# Acceptance: acc:govern-providers:E002-UNIT-001-orphan-binding-detected
# WMBT: wmbt:govern-providers:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E002-UNIT-001-orphan-binding-detected.

A bound convention_id with no matching convention node under ``.atdd/extensions``
is an ORPHAN — a mechanism enforcing an obligation nobody wrote down. It is reported
by name; a bound convention_id that HAS a node is not; and a non-bound
(legacy-fallback) entry is ignored — only a bound implementation can be orphaned.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.orphans import find_orphan_detectors

from .conftest import write_binding_lock, write_convention_node


def test_orphan_binding_detected(tmp_path: Path) -> None:
    # A node-backed bound convention (not an orphan).
    write_convention_node(tmp_path, "acme.extension.rules", "coder.demo.declared")
    write_binding_lock(
        tmp_path,
        [
            {
                "convention_id": "coder.demo.declared",
                "disposition": "bound",
                "implementation_id": "coder.demo.declared",
                "workspace_id": "atdd.workspace.python-pytest",
                "contract_version": "1.0.0",
            },
            {
                "convention_id": "coder.demo.orphaned",
                "disposition": "bound",
                "implementation_id": "coder.demo.orphaned",
                "workspace_id": "atdd.workspace.python-pytest",
                "contract_version": "1.0.0",
            },
            # legacy-fallback: not bound, so never an orphan even without a node.
            {"convention_id": "coder.demo.legacy", "disposition": "legacy-fallback"},
        ],
    )

    orphans = find_orphan_detectors(tmp_path)

    assert "coder.demo.orphaned" in orphans
    assert "coder.demo.declared" not in orphans
    assert "coder.demo.legacy" not in orphans
