# URN: test:validate-conventions:y003-anchor
# Acceptance: acc:validate-conventions:Y003-SMOKE-001-no-dangling-legacy-reference
# Acceptance: acc:validate-conventions:Y003-SMOKE-002-coverage-preserved
# WMBT: wmbt:validate-conventions:Y003
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: #1365 anchor stub. Real wired guard tests pending the issue's RED→GREEN cycle.

"""#1365 (binding-family legacy decommission) anchor stub.

Each test function below is a pytest.skip placeholder so the bidirectional
binding validator (tester.acceptance-violation.validator-binding-must-be-bidirectional)
can resolve harness.type to a real test file. Each function corresponds to
exactly one acceptance URN declared in the WMBT YAML at
plan/validate_conventions/Y003.yaml — the two guards that prove coverage did
not drop when the binding-family legacy validators are retired.

The two guards are new (they complement, not duplicate, the existing decommission
catches): Y001 (test_y001_no_unsafe_deletion) checks legacy-validator-map safety
but does not inspect rule-level implementation.ref/validator; Y002
(test_y002_decommission_preflight_classifier) classifies preflight readiness but
does not assert the replacement convention variant actually executes.

Replace each pytest.skip body with the real guard once the issue's RED phase ships.
Delete this file when every acceptance under the WMBT is anchored to its real test.
"""

from __future__ import annotations

import pytest


def test_y003_smoke_001_no_dangling_legacy_reference() -> None:
    """Anchor stub for acc:validate-conventions:Y003-SMOKE-001-no-dangling-legacy-reference (real guard pending implementation)."""
    pytest.skip("#1365 anchor stub — real wired guard pending implementation")


def test_y003_smoke_002_coverage_preserved() -> None:
    """Anchor stub for acc:validate-conventions:Y003-SMOKE-002-coverage-preserved (real guard pending implementation)."""
    pytest.skip("#1365 anchor stub — real wired guard pending implementation")
