# URN: test:enforce-conventions-ci:enforce-conventions-ci:E004-SMOKE-001-the-committed-lint-baseline-holds
# Acceptance: acc:enforce-conventions-ci:E004-SMOKE-001-the-committed-lint-baseline-holds
# WMBT: wmbt:enforce-conventions-ci:E004
# Phase: SMOKE
# Layer: application

"""Gate: `coder.lint.ruff-ratchet` (E004 / AC-SMOKE-001).

Toolkit-self only. `platform`-marked and guarded on `is_atdd_source_repo`, so a
consumer's `atdd validate coder` deselects it and never runs ruff.

An absent tool FAILS here rather than skipping. A gate that skips when it cannot
run reports green over an observation nobody made, which is the exact defect this
repository has now fixed in five separate places; the message names the tool and
how to install it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coder.validators._static_ratchet import (
    LINT_BASELINE_REL,
    ToolUnavailable,
    collect_lint_findings,
    format_new_findings,
    load_baseline,
    new_findings,
)

_RULE = bind_rule("coder.lint.ruff-ratchet")


@pytest.mark.coder
@pytest.mark.platform
def test_no_new_lint_findings():
    """
    E004 AC-SMOKE-001: no lint finding reaches main that the baseline does not already carry.

    Given: The repository's own src tree and .atdd/baselines/lint_toolkit.yaml
    When: ruff runs over it under the committed [tool.ruff] configuration
    Then: Every finding is one the baseline already froze
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self ratchet — runs only inside the atdd source repo")

    repo_root = Path(find_repo_root())
    baseline_path = repo_root / LINT_BASELINE_REL
    assert baseline_path.exists(), (
        f"{LINT_BASELINE_REL} is missing, so this gate has nothing to ratchet against "
        f"and would pass on any amount of new debt. Regenerate it deliberately."
    )

    try:
        findings = collect_lint_findings(repo_root)
    except ToolUnavailable as exc:
        pytest.fail(f"{_RULE.rule_id}: {exc}")

    unbaselined = new_findings(findings, load_baseline(baseline_path))
    assert not unbaselined, format_new_findings(unbaselined, "ruff", LINT_BASELINE_REL)
