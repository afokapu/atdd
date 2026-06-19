# URN: test:bind-substrate-runtime:substrate-binding:C002-SMOKE-001-real-contract-compatible
# Acceptance: acc:bind-substrate-runtime:C002-SMOKE-001-real-contract-compatible
# WMBT: wmbt:bind-substrate-runtime:C002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C002-SMOKE-001 — binding a real extension against a real python-pytest provider
passes the SemVer contract check; the plan records the implementation bound to the
provider, with no false contract-mismatch."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.substrate.binding import plan as plan_mod
from atdd.substrate.binding.tests.conftest import install_extension, install_provider


@pytest.mark.smoke
def test_real_compatible_pairing_binds(tmp_path: Path) -> None:
    install_provider(tmp_path)  # contract_version 1.0.0
    install_extension(tmp_path, "acme.extension.demo", convention="demo.pr.gate")  # contract 1.0.0

    plan = plan_mod.build_binding_plan(tmp_path)
    by_convention = {c["convention_id"]: c for c in plan["conventions"]}

    bound = by_convention["demo.pr.gate"]
    assert bound["disposition"] == "bound"
    assert bound["implementation_id"] == "acme.extension.demo.gate.impl"
    assert bound["workspace_id"] == "atdd.workspace.python-pytest"
    # No false contract-mismatch degraded it to legacy-fallback.
    assert all(c["disposition"] == "bound" for c in plan["conventions"])
