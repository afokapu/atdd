# URN: test:govern-lifecycle:config-driven-four-tier-validators:E049-SMOKE-001-new-violation-beyond-baseline-fails-the-gate
# Acceptance: acc:govern-lifecycle:E049-SMOKE-001-new-violation-beyond-baseline-fails-the-gate
# WMBT: wmbt:govern-lifecycle:E049
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E049 SMOKE — the ratchet bites on growth, over a REAL toolkit scan.

No mocks: ``collect_toolkit_violations`` runs the production config-driven
composition analysis over the real ``src/atdd`` tree and resolves the real
grandfathered baseline from ``.atdd/baselines/``. A genuinely-new violation
(absent from the baseline) is then introduced and must fail the gate, while the
pre-existing grandfathered debt stays absorbed — proving the freeze is a ratchet,
not a blanket skip.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation
from atdd.coder.validators._four_tier_ratchet import (
    collect_toolkit_violations,
    load_grandfathered_baseline,
    new_violations,
    violation_identity,
)

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()


def test_new_violation_beyond_baseline_fails_the_gate():
    """E049-SMOKE-001: a new violation beyond the baseline leaks; legacy stays absorbed."""
    config = load_atdd_config(REPO_ROOT)
    baseline = load_grandfathered_baseline(REPO_ROOT)
    # Real scan of the live toolkit tree (no fakes).
    existing = collect_toolkit_violations(REPO_ROOT, config)
    assert baseline, "the real grandfathered baseline must be present for this smoke"

    synthetic = Violation(
        rule_id="coder.refactor.composition-consumer",
        severity=3,
        location="temp_wagon/brand_new_feature/src/domain/unwired.py",
        detail="spec_id=SPEC-CODER-COMP-0001 synthetic NEW violation not in baseline",
        fix_hint_ref="",
    )
    assert violation_identity(synthetic) not in baseline

    leaked = new_violations(existing + [synthetic], baseline)
    leaked_ids = {violation_identity(v) for v in leaked}

    assert violation_identity(synthetic) in leaked_ids, (
        "a new, unsuppressed violation beyond the baseline must fail the gate"
    )
    # The pre-existing grandfathered debt is absorbed — it is not what failed.
    assert leaked_ids == {violation_identity(synthetic)}, (
        "only the new violation should leak; grandfathered debt stays absorbed"
    )
