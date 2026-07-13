# URN: test:project-shared-state:verify-projection-canonicality:C002-UNIT-002-roundtrip-identity-holds
# Acceptance: acc:project-shared-state:C002-UNIT-002-roundtrip-identity-holds
# WMBT: wmbt:project-shared-state:C002
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A projection produced by project(store) passes the canonicality check unchanged, exiting zero — and the check reads neither GitHub nor any developer sqlite store. Refs #1433.
"""The round-trip identity holds on a real projection (C002-UNIT-002).

wagon: project-shared-state | feature: verify-projection-canonicality | phase: GREEN
WMBT: wmbt:project-shared-state:C002

The gate must pass what the tool produced — a check that failed on its own output
would be worse than no check. And it must reach neither GitHub nor a developer's
SQLite: CI has neither. Refs #1433 / #1400.
"""
from __future__ import annotations

import ast
from pathlib import Path

import atdd.state.projection as projection_module
from atdd.state.projection_cli import _cmd_canonicality
from atdd.state.projection import check_canonicality, project
from atdd.state.paths import STATE_STORE_RELATIVE
from atdd.state.providers import clear_providers, registered_names

from ._helpers import memory_store, two_work_items


class _Args:
    """The parsed-CLI shape `atdd state canonicality --from <dir>` produces."""

    def __init__(self, from_dir):
        self.op = "canonicality"
        self.from_dir = str(from_dir)
        self.root = None


def test_c002_unit_002_roundtrip_identity_holds(tmp_path, capsys) -> None:
    """project(store) output is canonical; the check exits zero and touches no store or API."""
    clear_providers()
    assert registered_names() == []

    projection_dir = tmp_path / "projection"
    with memory_store() as (conn, store):
        two_work_items(conn)
        result = project(store, projection_dir)
    assert len(result.files) == 2

    report = check_canonicality(projection_dir)

    # The check exits zero and reports the projection as canonical.
    assert report.ok
    assert report.mismatches == []
    assert report.checked == 2
    assert "canonical" in report.render()
    assert _cmd_canonicality(_Args(projection_dir)) == 0
    assert "NOT canonical" not in capsys.readouterr().out

    # The check reads neither GitHub nor any developer sqlite store: it created no
    # state.sqlite anywhere under the working tree...
    assert not (tmp_path / STATE_STORE_RELATIVE).exists()
    assert list(tmp_path.rglob("*.sqlite")) == []

    # ...and the module it runs in names no provider, no GitHub, and no on-disk store.
    source = Path(projection_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("github" in name.lower() for name in imported)
    assert not any(name.endswith("providers") for name in imported)
    assert "init_state_store" not in source
