# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E052-SMOKE-001-train-gate-enforces-offline-zero-board-graphql
# Acceptance: acc:govern-lifecycle:E052-SMOKE-001-train-gate-enforces-offline-zero-board-graphql
# WMBT: wmbt:govern-lifecycle:E052
# Phase: RED
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E052-SMOKE-001 — the Train gate enforces offline with zero board GraphQL.

Against a real repo manifest + plan/_trains.yaml and a recording client (no
PROJECT_TOKEN), the gate enforces membership using only the manifest, recording
zero Projects-v2 field-value queries.

RED now: update() still queries ``get_project_item_field_values`` for the gate.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.platform]


def _setup(tmp_path: Path) -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    (cfg / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "sessions": [{"issue_number": 384, "status": "PLANNED"}],
                "issues": {"384": {"slug": "demo", "train": "0001-self-compliance-validate"}},
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


def test_train_gate_enforces_offline_zero_board_graphql(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_TOKEN", raising=False)
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = {
        "number": 384,
        "title": "demo",
        "state": "OPEN",
        "labels": [{"name": "atdd:RED"}, {"name": "atdd-issue"}],
        "body": "| Type | `implementation` |\n",
    }
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "f", "options": {"GREEN": "opt_green"}}
    }
    client.get_project_item_id.return_value = "item_abc"
    client.get_project_item_field_values.return_value = {"ATDD Train": "0001-self-compliance-validate"}

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0, "gate enforces successfully from manifest + plan/_trains.yaml"
    client.get_project_item_field_values.assert_not_called()
