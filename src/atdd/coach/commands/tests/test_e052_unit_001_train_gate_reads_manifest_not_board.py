# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E052-UNIT-001-train-gate-reads-manifest-not-board
# Acceptance: acc:govern-lifecycle:E052-UNIT-001-train-gate-reads-manifest-not-board
# WMBT: wmbt:govern-lifecycle:E052
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E052-UNIT-001 — the Train gate resolves the train from the manifest.

Post-removal contract: the only decision-bearing board read (the Train gate's
``get_project_item_field_values`` lookup of "ATDD Train") is replaced by the
local manifest mirror, validated against plan/_trains.yaml — zero board GraphQL.

RED now: update() reads ``get_project_item_field_values`` for the train gate, so
assert_not_called fails.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.platform]


def _setup(tmp_path: Path, train: str) -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    (cfg / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "sessions": [{"issue_number": 384, "status": "PLANNED"}],
                "issues": {"384": {"slug": "demo", "train": train}},
            }
        )
    )
    # Real plan/_trains.yaml so membership can be validated locally.
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "_trains.yaml").write_text(
        yaml.safe_dump(
            {"trains": {"commons": {"validate": [{"train_id": "0001-self-compliance-validate"}]}}}
        )
    )
    return tmp_path


def _make_issue() -> dict:
    # implementation type → train is REQUIRED past PLANNED, so the gate runs.
    return {
        "number": 384,
        "title": "demo",
        "state": "OPEN",
        "labels": [{"name": "atdd:RED"}, {"name": "atdd-issue"}],
        "body": "| Type | `implementation` |\n",
    }


def test_train_gate_reads_manifest_not_board(tmp_path):
    target = _setup(tmp_path, "0001-self-compliance-validate")
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue()
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "field_status", "options": {"GREEN": "opt_green"}}
    }
    client.get_project_item_id.return_value = "item_abc"
    # If the legacy board read runs it would also satisfy the gate — prove it
    # is the manifest, not this, that the gate consults.
    client.get_project_item_field_values.return_value = {"ATDD Train": "0001-self-compliance-validate"}

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0, "in-train issue should pass the gate from the manifest"
    client.get_project_item_field_values.assert_not_called()
