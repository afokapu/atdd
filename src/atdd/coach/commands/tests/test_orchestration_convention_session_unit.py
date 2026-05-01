"""
Test that orchestration.convention.yaml is amended for pane mode.

WMBT: wmbt:govern-lifecycle:D017
- AC-UNIT-001: rule renamed to one_agent_per_session_unit with workspace + pane sub-rules
- AC-UNIT-002: babysit shared-state caveat documented for pane mode
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]

CONVENTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "coach"
    / "conventions"
    / "orchestration.convention.yaml"
)


def _load_convention() -> dict:
    with CONVENTION_PATH.open() as f:
        return yaml.safe_load(f)


def test_convention_renames_to_one_agent_per_session_unit():
    """D017-AC-UNIT-001: rule renamed; sub-rules cover workspace mode and pane mode."""
    doc = _load_convention()
    rules = doc["rules"]

    assert "one_agent_per_session_unit" in rules, (
        "Expected 'one_agent_per_session_unit' as the renamed rule key"
    )

    rule = rules["one_agent_per_session_unit"]
    # Two sub-rules must be present: workspace mode + pane mode
    sub_rules = rule.get("sub_rules") or rule.get("modes") or {}
    assert isinstance(sub_rules, dict)
    assert "workspace" in sub_rules, "workspace-mode sub-rule missing"
    assert "pane" in sub_rules, "pane-mode sub-rule missing"

    # Anti-pattern about sub-agent delegation must remain present somewhere
    serialised = yaml.safe_dump(rule)
    assert "sub-agent" in serialised.lower() or "sub_agent" in serialised.lower(), (
        "Anti-pattern about sub-agent delegation must remain documented"
    )


def test_convention_old_key_removed_or_marked_deprecated():
    """D017-AC-UNIT-001: old key removed or explicitly marked deprecated."""
    doc = _load_convention()
    rules = doc["rules"]
    if "one_agent_per_workspace" in rules:
        deprecated = rules["one_agent_per_workspace"].get("deprecated")
        pointer = rules["one_agent_per_workspace"].get("see") or rules[
            "one_agent_per_workspace"
        ].get("renamed_to")
        assert deprecated, "Legacy key kept without deprecation marker"
        assert pointer == "one_agent_per_session_unit", (
            "Deprecated key must point to the new key"
        )


def test_convention_documents_babysit_shared_state_caveat():
    """D017-AC-UNIT-002: pane mode shared WorkspaceState caveat is documented."""
    doc = _load_convention()
    serialised = yaml.safe_dump(doc).lower()

    assert "shared" in serialised
    assert "workspacestate" in serialised or "workspace state" in serialised
    assert "pane" in serialised
