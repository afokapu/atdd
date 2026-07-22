# URN: test:govern-providers:E003-UNIT-001-generated-lock-carries-no-package-identity
# Acceptance: acc:govern-providers:E003-UNIT-001-generated-lock-carries-no-package-identity
# WMBT: wmbt:govern-providers:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E003-UNIT-001-generated-lock-carries-no-package-identity.

Building the binding plan over a real locked substrate whose extension PACKAGE id is
``atdd.extension.coder`` produces a lock that keys each bound entry by convention_id,
implementation_id, workspace_id and contract_version — and contains the package id
string zero times. The marriage records the mechanism, never the package identity.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.substrate.binding.plan import build_binding_plan

from .conftest import install_extension_impl, install_provider


def test_generated_lock_carries_no_package_identity(tmp_path: Path) -> None:
    install_provider(tmp_path, contract_version="1.0.0")
    install_extension_impl(
        tmp_path,
        ext_id="atdd.extension.coder",
        convention="coder.demo.rule",
        implementation_id="coder.demo.rule",
    )

    plan = build_binding_plan(tmp_path)

    bound = [c for c in plan["conventions"] if c.get("disposition") == "bound"]
    assert bound, "the compatible implementation must bind"
    entry = next(c for c in bound if c["convention_id"] == "coder.demo.rule")
    assert set(entry) >= {
        "convention_id",
        "implementation_id",
        "workspace_id",
        "contract_version",
    }

    serialized = yaml.safe_dump(plan, sort_keys=False)
    assert "atdd.extension.coder" not in serialized
