# URN: test:dispatch-validators:e001-anchor
# Acceptance: acc:dispatch-validators:E001-UNIT-001-pytest-plugin-captures-all-violations
# Acceptance: acc:dispatch-validators:E001-CONTRACT-001-violations-jsonl-schema-conformant
# WMBT: wmbt:dispatch-validators:E001
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: Coach v9 anchor stub. Real wired tests pending the issue's RED→GREEN cycle.

"""Coach v9 anchor stub.

Each test function below is a pytest.skip placeholder so the bidirectional
binding validator (tester.acceptance-violation.validator-binding-must-be-bidirectional)
can resolve harness.type to a real test file. Each function corresponds to
exactly one acceptance URN declared in the WMBT YAML at
plan/dispatch_validators/E001.yaml.

Replace each pytest.skip body with the real test once the issue's RED phase ships.
Delete this file when every acceptance under the WMBT is anchored to its real test.
"""

from __future__ import annotations

import pytest


def test_e001_unit_001_pytest_plugin_captures_all_violations() -> None:
    """Anchor stub for acc:dispatch-validators:E001-UNIT-001-pytest-plugin-captures-all-violations (real test pending implementation).""" 
    pytest.skip("coach v9 anchor stub — real wired test pending implementation")


def test_e001_contract_001_violations_jsonl_schema_conformant() -> None:
    """Anchor stub for acc:dispatch-validators:E001-CONTRACT-001-violations-jsonl-schema-conformant (real test pending implementation).""" 
    pytest.skip("coach v9 anchor stub — real wired test pending implementation")


