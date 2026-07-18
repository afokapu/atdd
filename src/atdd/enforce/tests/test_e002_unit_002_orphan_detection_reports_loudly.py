# URN: test:govern-providers:E002-UNIT-002-orphan-detection-reports-loudly
# Acceptance: acc:govern-providers:E002-UNIT-002-orphan-detection-reports-loudly
# WMBT: wmbt:govern-providers:E002
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E002-UNIT-002-orphan-detection-reports-loudly.

When an orphan binding exists the guard fails LOUDLY — it raises, naming each orphan
convention_id — rather than passing silently (the way a nodeless bound rule would
otherwise default to strict). Over a substrate whose bound conventions all have
nodes, the same guard passes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.orphans import OrphanDetectorError, assert_no_orphan_detectors

from .conftest import write_binding_lock, write_convention_node


def test_orphan_detection_reports_loudly(tmp_path: Path) -> None:
    write_binding_lock(
        tmp_path,
        [
            {
                "convention_id": "coder.demo.orphaned",
                "disposition": "bound",
                "implementation_id": "coder.demo.orphaned",
                "workspace_id": "atdd.workspace.python-pytest",
                "contract_version": "1.0.0",
            }
        ],
    )

    with pytest.raises(OrphanDetectorError) as exc:
        assert_no_orphan_detectors(tmp_path)

    assert "coder.demo.orphaned" in str(exc.value)


def test_clean_substrate_passes(tmp_path: Path) -> None:
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
            }
        ],
    )

    # No orphans → returns cleanly, does not raise.
    assert assert_no_orphan_detectors(tmp_path) == []
