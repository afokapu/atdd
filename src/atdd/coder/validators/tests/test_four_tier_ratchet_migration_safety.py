# URN: test:govern-lifecycle:config-driven-four-tier-validators:E049-INTEGRATION-001-no-existing-legacy-file-newly-fails-under-toolkit-root
# Acceptance: acc:govern-lifecycle:E049-INTEGRATION-001-no-existing-legacy-file-newly-fails-under-toolkit-root
# WMBT: wmbt:govern-lifecycle:E049
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E049 — ratchet baseline so config-driving does not light up the wall.

Honoring ``code.toolkit`` surfaces the full legacy four-tier debt at once. The
ratchet grandfathers today's toolkit violations into a frozen baseline so the
gate fails only on NEW or growing violations: no untouched legacy file may start
failing, but a genuinely-new violation must.

RED state: the grandfathered baseline does not exist yet and the
``_four_tier_ratchet`` module is not implemented, so every current toolkit
violation reads as NEW (migration UNSAFE).
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.config import load_atdd_config
from atdd.coach.utils.repo import find_repo_root
from atdd.coder.validators._four_tier_ratchet import (
    collect_toolkit_violations,
    load_grandfathered_baseline,
    new_violations,
    violation_identity,
)

pytestmark = [pytest.mark.platform]

REPO_ROOT = find_repo_root()


def test_no_existing_legacy_file_newly_fails_under_toolkit_root():
    """E049-INTEGRATION-001: current toolkit debt is fully grandfathered."""
    config = load_atdd_config(REPO_ROOT)
    violations = collect_toolkit_violations(REPO_ROOT, config)
    baseline = load_grandfathered_baseline(REPO_ROOT)

    assert baseline, (
        "the grandfathered baseline must snapshot today's toolkit debt "
        "(non-empty) — the debt is frozen and visible, never silently covered"
    )
    leaked = new_violations(violations, baseline)
    assert not leaked, (
        "enabling code.toolkit must not newly-fail any pre-existing legacy file; "
        "these violations are not in the grandfathered baseline:\n"
        + "\n".join(f"  {violation_identity(v)}" for v in leaked)
    )
