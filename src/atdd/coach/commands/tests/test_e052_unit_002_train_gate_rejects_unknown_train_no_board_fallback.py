# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E052-UNIT-002-train-gate-rejects-unknown-train-no-board-fallback
# Acceptance: acc:govern-lifecycle:E052-UNIT-002-train-gate-rejects-unknown-train-no-board-fallback
# WMBT: wmbt:govern-lifecycle:E052
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E052-UNIT-002 — an unknown manifest train fails the gate loudly, no board fallback.

Post-removal contract: when the manifest train is absent from plan/_trains.yaml,
the Train gate fails loudly (rc=1) identifying the unknown value and does NOT fall
back to ``get_project_item_field_values`` (or any board read) to recover the train.

RED now: update() still consults the board for the train; a valid-looking board
value lets the transition succeed (rc=0), so the rc=1 / no-board assertions fail.
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
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "_trains.yaml").write_text(
        yaml.safe_dump(
            {"trains": {"commons": {"validate": [{"train_id": "0001-self-compliance-validate"}]}}}
        )
    )
    return tmp_path


def _make_issue() -> dict:
    return {
        "number": 384,
        "title": "demo",
        "state": "OPEN",
        "labels": [{"name": "atdd:RED"}, {"name": "atdd-issue"}],
        "body": "| Type | `implementation` |\n",
    }


def test_train_gate_rejects_unknown_train_no_board_fallback(tmp_path):
    target = _setup(tmp_path, "9999-not-a-real-train")
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue()
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "field_status", "options": {"GREEN": "opt_green"}}
    }
    client.get_project_item_id.return_value = "item_abc"
    # A valid-looking board value must NOT rescue an unknown manifest train.
    client.get_project_item_field_values.return_value = {"ATDD Train": "0001-self-compliance-validate"}

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 1, "unknown manifest train must fail the gate loudly"
    client.get_project_item_field_values.assert_not_called()
    client.add_label.assert_not_called()
