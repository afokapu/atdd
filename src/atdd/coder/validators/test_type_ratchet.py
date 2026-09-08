# URN: test:enforce-conventions-ci:enforce-conventions-ci:E004-SMOKE-002-the-committed-type-baseline-holds
# Acceptance: acc:enforce-conventions-ci:E004-SMOKE-002-the-committed-type-baseline-holds
# WMBT: wmbt:enforce-conventions-ci:E004
# Phase: SMOKE
# Layer: application

"""Gate: `coder.types.pyright-ratchet` (E004 / AC-SMOKE-002).

74% of non-test source files carry annotations that nothing verified. This gate
does not demand they all be correct — it demands the count stop growing.

Toolkit-self only: `platform`-marked and guarded on `is_atdd_source_repo`, so a
consumer's `atdd validate coder` deselects it and never runs pyright. An absent
tool FAILS rather than skips, naming the tool and how to install it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coder.validators._static_ratchet import (
    TYPE_BASELINE_REL,
    ToolUnavailable,
    collect_type_findings,
    format_new_findings,
    load_baseline,
    new_findings,
)

_RULE = bind_rule("coder.types.pyright-ratchet")


@pytest.mark.coder
@pytest.mark.platform
def test_no_new_type_errors():
    """
    E004 AC-SMOKE-002: no type error reaches main that the baseline does not already carry.

    Given: The repository's own src tree and .atdd/baselines/types_toolkit.yaml
    When: pyright runs over it under the committed pyrightconfig.json
    Then: Every error is one the baseline already froze
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self ratchet — runs only inside the atdd source repo")

    repo_root = Path(find_repo_root())
    baseline_path = repo_root / TYPE_BASELINE_REL
    assert baseline_path.exists(), (
        f"{TYPE_BASELINE_REL} is missing, so this gate has nothing to ratchet against "
        f"and would pass on any amount of new debt. Regenerate it deliberately."
    )

    try:
        findings = collect_type_findings(repo_root)
    except ToolUnavailable as exc:
        pytest.fail(f"{_RULE.rule_id}: {exc}")

    unbaselined = new_findings(findings, load_baseline(baseline_path))
    assert not unbaselined, format_new_findings(unbaselined, "pyright", TYPE_BASELINE_REL)
