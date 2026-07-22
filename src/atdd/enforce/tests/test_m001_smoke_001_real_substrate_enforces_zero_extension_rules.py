# URN: test:verify-enforcement:M001-SMOKE-001-real-substrate-enforces-zero-extension-rules
# Acceptance: acc:verify-enforcement:M001-SMOKE-001-real-substrate-enforces-zero-extension-rules
# WMBT: wmbt:verify-enforcement:M001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:verify-enforcement:M001-SMOKE-001-real-substrate-enforces-zero-extension-rules.

Over the toolkit's real substrate and real CI wiring the extension-enforced set
is EMPTY while the bound set is not — every bound extension rule is REPORTED-only
today, enforced solely by its blocking core twin. This is the latent hole, named.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.coverage_report import live_coverage_report
from atdd.enforce.registry import path_b_is_blocking


def test_real_substrate_enforces_zero_extension_rules() -> None:
    repo = find_repo_root()

    # Path B (atdd enforce over the extensions) is NOT a blocking CI gate today.
    assert path_b_is_blocking(repo) is False

    report = live_coverage_report(repo, repo)

    # The real lock genuinely binds extension conventions...
    assert report.bound, "expected the real binding.lock to bind extension conventions"
    # ...yet the extension path enforces NOTHING, because its verdict is advisory.
    assert report.enforced == []
    # So every bound extension rule is REPORTED-only: the bound set is not the
    # enforced set over the real toolkit.
    assert report.reported == report.bound
    assert set(report.enforced) < set(report.bound)
