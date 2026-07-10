# URN: test:reconcile-dispositions:E001-SMOKE-001-enforce-does-not-fail-a-bound-documentation-only-rule
# Acceptance: acc:reconcile-dispositions:E001-SMOKE-001-enforce-does-not-fail-a-bound-documentation-only-rule
# WMBT: wmbt:reconcile-dispositions:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — against the committed vendored substrate, the bound
documentation-only rule ``tester.filename.urn`` cannot produce a fail verdict,
even with violations. This is the live bug the total mapping closes."""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.conventions import rule_metadata
from atdd.enforce.runner import _verdict_for_rule, resolve_substrate_home

_ONE_VIOLATION = [{"rule_id": "x", "file": "a.py", "line": 1, "col": 1}]
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_e001_smoke_001_enforce_does_not_fail_a_bound_documentation_only_rule():
    substrate_home = resolve_substrate_home(_REPO_ROOT)
    meta = rule_metadata(substrate_home, "tester.filename.urn")
    # The real vendored node declares documentation-only ...
    assert meta.disposition == "documentation-only"
    # ... so it never fails the build, even when the provider reports violations.
    assert _verdict_for_rule(meta, _ONE_VIOLATION) == "pass"
