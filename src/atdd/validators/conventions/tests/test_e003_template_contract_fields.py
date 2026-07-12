# URN: test:validate-conventions:family-template-catalogue:E003-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E003-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E003 — _support/template_contract.py defines all eight mandatory template fields."""
from __future__ import annotations

import importlib
from pathlib import Path

def test_template_contract_defines_mandatory_fields(
    conventions_dir: Path, mandatory_template_fields: list
) -> None:
    contract_path = conventions_dir / "_support" / "template_contract.py"
    assert contract_path.exists(), f"template contract not found at {contract_path}"

    mod = importlib.import_module(
        "atdd.validators.conventions._support.template_contract"
    )
    # The contract must expose the mandatory field names introspectably, whether
    # as a dataclass, TypedDict, or an explicit REQUIRED_FIELDS collection.
    declared = getattr(mod, "REQUIRED_FIELDS", None)
    if declared is None:
        contract_type = getattr(mod, "TemplateContract", None)
        assert contract_type is not None, (
            "template_contract.py must expose REQUIRED_FIELDS or a TemplateContract type"
        )
        declared = getattr(contract_type, "__annotations__", {}).keys()

    missing = [f for f in mandatory_template_fields if f not in set(declared)]
    assert not missing, f"template contract missing mandatory fields: {missing}"
