# URN: test:govern-lifecycle:agent-behavior-rules-enforcement:E015-UNIT-003-agent-rules-yaml-is-valid-yaml
# Acceptance: acc:govern-lifecycle:E015-UNIT-003-agent-rules-yaml-is-valid-yaml
# WMBT: wmbt:govern-lifecycle:E015
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E015-UNIT-003 — .atdd/agent-rules.yaml parses and has required structure."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_agent_rules_yaml_is_valid_yaml():
    rules_path = Path(".atdd/agent-rules.yaml")
    assert rules_path.exists(), ".atdd/agent-rules.yaml must exist in the repo"

    parsed = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    assert "rules" in parsed, "agent-rules.yaml must have top-level 'rules' key"
    assert len(parsed["rules"]) >= 2, f"expected at least 2 rules, got {len(parsed['rules'])}"

    for rule in parsed["rules"]:
        assert "id" in rule, f"each rule must have 'id' field: {rule}"
        assert "rule" in rule, f"each rule must have 'rule' field: {rule}"
