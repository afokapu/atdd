# URN: test:author-atdd-substrate:substrate-spine:C006-UNIT-002-contract-compat
# Acceptance: acc:author-atdd-substrate:C006-UNIT-002-contract-compat
# WMBT: wmbt:author-atdd-substrate:C006
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C006-UNIT-002 — the provider<->implementation contract: compatible versions accepted, incompatible refused."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author_manifest import (
    contract_satisfies,
    extension_targets_satisfied_by,
    implementation_accepted_by,
)


@pytest.mark.parametrize("version,spec,ok", [
    ("1.0.0", "^1.0.0", True),
    ("1.4.2", "^1.0.0", True),
    ("2.0.0", "^1.0.0", False),   # major bump breaks caret
    ("0.9.0", "^1.0.0", False),   # below base
    ("1.2.5", "~1.2.0", True),
    ("1.3.0", "~1.2.0", False),   # minor bump breaks tilde
    ("1.0.0", "1.0.0", True),
    ("1.0.1", "1.0.0", False),    # exact mismatch
    ("1.7.0", "1.x", True),
    ("2.0.0", "1.x", False),
])
def test_contract_satisfies(version, spec, ok):
    assert contract_satisfies(version, spec) is ok


_PROVIDER = {"workspace_id": "atdd.workspace.python-pytest", "contract_version": "1.3.0",
             "discovers": {"requires_contract": "^1.0.0"}}


def test_extension_target_compatibility():
    ext_ok = {"depends_on": {"workspaces": [{"id": "atdd.workspace.python-pytest", "contract": "^1.0.0"}]}}
    ext_bad = {"depends_on": {"workspaces": [{"id": "atdd.workspace.python-pytest", "contract": "^2.0.0"}]}}
    assert extension_targets_satisfied_by(ext_ok, _PROVIDER) is True
    assert extension_targets_satisfied_by(ext_bad, _PROVIDER) is False


def test_implementation_acceptance():
    assert implementation_accepted_by({"contract_version": "1.0.0"}, _PROVIDER) is True
    assert implementation_accepted_by({"contract_version": "2.0.0"}, _PROVIDER) is False
