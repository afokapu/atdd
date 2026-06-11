# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E051-UNIT-001-transition-emits-label-rest-only-no-board-graphql
# Acceptance: acc:govern-lifecycle:E051-UNIT-001-transition-emits-label-rest-only-no-board-graphql
# WMBT: wmbt:govern-lifecycle:E051
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E051-UNIT-001 — a phase transition issues only the atdd:<phase> label swap.

Post-removal contract: IssueManager.update() drives a phase transition off the
``atdd:<phase>`` label (REST) alone and emits ZERO Projects-v2 GraphQL — none of
``get_project_fields`` / ``get_project_item_id`` / ``set_project_field_select`` /
``set_project_field_text`` / ``get_project_item_field_values`` /
``add_issue_to_project``. The local manifest stays the state mirror.

RED now: the current update() still reads (get_project_fields / get_project_item_id)
and writes (set_project_field_select) the board, so the assert_not_called fails.
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


def _setup(tmp_path: Path, status: str = "RED") -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    (cfg / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "sessions": [{"issue_number": 384, "status": status}],
                "issues": {"384": {"slug": "demo", "train": "0001-self-compliance-validate"}},
            }
        )
    )
    return tmp_path


def _make_issue(status: str = "RED") -> dict:
    # cleanup type is train-optional → focuses this test on the board-write path.
    return {
        "number": 384,
        "title": "demo",
        "state": "OPEN",
        "labels": [{"name": f"atdd:{status}"}, {"name": "atdd-issue"}],
        "body": "| Type | `cleanup` |\n",
    }


def test_transition_emits_label_rest_only_no_board_graphql(tmp_path):
    target = _setup(tmp_path, "RED")
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.get_issue.return_value = _make_issue("RED")
    # Provide sane board returns so that IF the (to-be-removed) board path runs
    # the call still completes — the point is it must NOT run at all.
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "field_status", "options": {"GREEN": "opt_green"}}
    }
    client.get_project_item_id.return_value = "item_abc"
    client.get_project_item_field_values.return_value = {"ATDD Train": "0001-self-compliance-validate"}

    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0, "label-only transition should succeed"
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])

    for method in BOARD_METHODS:
        getattr(client, method).assert_not_called()

    manifest = yaml.safe_load((target / ".atdd" / "manifest.yaml").read_text())
    statuses = {e["issue_number"]: e.get("status") for e in manifest["sessions"]}
    assert statuses[384] == "GREEN", "manifest remains the local state mirror"
