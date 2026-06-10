# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E051-SMOKE-001-full-cycle-zero-projects-v2-graphql
# Acceptance: acc:govern-lifecycle:E051-SMOKE-001-full-cycle-zero-projects-v2-graphql
# WMBT: wmbt:govern-lifecycle:E051
# Phase: RED
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E051-SMOKE-001 — a full RED->COMPLETE drive issues zero Projects-v2 GraphQL.

Against a real repo manifest and a recording GitHub client (no PROJECT_TOKEN),
driving an issue through its phase transitions records ZERO board operations and
each transition is an ``atdd:<phase>`` label swap.

RED now: each update() still touches the board, so board ops accumulate > 0.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.platform]

BOARD_METHODS = (
    "get_project_fields",
    "get_project_item_id",
    "set_project_field_select",
    "set_project_field_text",
    "get_project_item_field_values",
    "add_issue_to_project",
)


def _setup(tmp_path: Path) -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    (cfg / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "sessions": [{"issue_number": 384, "status": "RED"}],
                "issues": {"384": {"slug": "demo", "train": "0001-self-compliance-validate"}},
            }
        )
    )
    return tmp_path


def test_full_cycle_zero_projects_v2_graphql(tmp_path, monkeypatch):
    monkeypatch.delenv("PROJECT_TOKEN", raising=False)
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    current = {"phase": "RED"}

    def _issue_for_phase(_num):
        return {
            "number": 384,
            "title": "demo",
            "state": "OPEN",
            "labels": [{"name": f"atdd:{current['phase']}"}, {"name": "atdd-issue"}],
            "body": "| Type | `cleanup` |\n",
        }

    client = MagicMock()
    client.get_issue.side_effect = _issue_for_phase
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "f", "options": {p: f"opt_{p}" for p in ("GREEN", "SMOKE", "REFACTOR", "COMPLETE")}}
    }
    client.get_project_item_id.return_value = "item_abc"
    client.get_project_item_field_values.return_value = {"ATDD Train": "0001-self-compliance-validate"}

    transitions = ["GREEN", "SMOKE", "REFACTOR", "COMPLETE"]
    label_swaps = []

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        for nxt in transitions:
            rc = mgr.update("384", status=nxt)
            assert rc == 0, f"transition to {nxt} should succeed"
            current["phase"] = nxt

    label_swaps = [c.args for c in client.add_label.call_args_list]
    assert label_swaps == [(384, [f"atdd:{p}"]) for p in transitions], label_swaps

    for method in BOARD_METHODS:
        getattr(client, method).assert_not_called()
