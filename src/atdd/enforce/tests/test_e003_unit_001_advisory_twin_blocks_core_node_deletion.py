# URN: test:govern-registry:E003-UNIT-001-advisory-twin-blocks-core-node-deletion
# Acceptance: acc:govern-registry:E003-UNIT-001-advisory-twin-blocks-core-node-deletion
# WMBT: wmbt:govern-registry:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E003-UNIT-001-advisory-twin-blocks-core-node-deletion.

Deleting a core rule whose extension twin is bound but enforced only advisorily
(Path B not a blocking gate) is refused — the latent hole where deletion silently
removes the sole blocking enforcement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.registry import CoreSuccessionError, guard_core_deletion

from .conftest import write_binding_lock, write_mirror_node


def test_advisory_twin_blocks_core_node_deletion(tmp_path: Path) -> None:
    core_rule = "coder.dead-code.reachability"

    # An extension node mirrors the core rule, and the lock binds it...
    write_mirror_node(tmp_path, rule_id=core_rule, legacy_rule_id=core_rule)
    write_binding_lock(
        tmp_path,
        [
            {
                "convention_id": core_rule,
                "disposition": "bound",
                "implementation_id": core_rule,
                "workspace_id": "atdd.workspace.python-pytest",
                "contract_version": "1.0.0",
            }
        ],
    )

    # ...but Path B is advisory (not blocking). Deleting the core rule is refused.
    with pytest.raises(CoreSuccessionError) as exc:
        guard_core_deletion([core_rule], tmp_path, path_b_blocking=False)
    message = str(exc.value)
    assert core_rule in message
    assert "advisory" in message
