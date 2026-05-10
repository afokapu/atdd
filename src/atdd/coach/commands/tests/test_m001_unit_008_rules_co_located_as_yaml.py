# URN: test:observe-and-correct:observer-runtime-and-rules:M001-UNIT-008-rules-co-located-as-yaml
# Acceptance: acc:observe-and-correct:M001-UNIT-008-rules-co-located-as-yaml
# WMBT: wmbt:observe-and-correct:M001
# Phase: RED
# Layer: application
"""M001-UNIT-008 — Seven rule files exist at `.atdd/observer/rules/`.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3.

Each canonical rule file resolves to a registered `rule_id` via
`bind_rule()`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.rule_binding import bind_rule

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULES_DIR = REPO_ROOT / ".atdd" / "observer" / "rules"

EXPECTED_FILES = (
    "01-unstructured-question.yaml",
    "02-token-silence.yaml",
    "03-completion-claim-without-commit.yaml",
    "04-out-of-scope-edit.yaml",
    "05-missed-heartbeat.yaml",
    "08-reviewer-edit-attempt.yaml",
    "09-validator-failure-ignored.yaml",
)


@pytest.mark.parametrize("filename", EXPECTED_FILES)
def test_rule_file_exists(filename: str):
    assert (RULES_DIR / filename).exists(), (
        f".atdd/observer/rules/{filename} must exist for #L2"
    )


@pytest.mark.parametrize("filename", EXPECTED_FILES)
def test_rule_id_resolves_via_bind_rule(filename: str):
    payload = yaml.safe_load((RULES_DIR / filename).read_text(encoding="utf-8"))
    rid = payload["rule_id"]
    meta = bind_rule(rid)
    assert meta.rule_id == rid


def test_rule_load_and_evaluate_does_not_raise_for_any_rule():
    """End-to-end load: each YAML produces a valid ObserverRule via the
    observer's own loader (no registry-bypass, no YAML-bypass)."""
    from atdd.coach.commands import observer

    for filename in EXPECTED_FILES:
        payload = yaml.safe_load((RULES_DIR / filename).read_text(encoding="utf-8"))
        rule = observer._build_rule_from_yaml(
            payload, source_path=RULES_DIR / filename
        )
        assert rule.rule_id == payload["rule_id"]
