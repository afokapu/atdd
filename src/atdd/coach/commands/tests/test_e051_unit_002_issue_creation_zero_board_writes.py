# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E051-UNIT-002-issue-creation-zero-board-writes
# Acceptance: acc:govern-lifecycle:E051-UNIT-002-issue-creation-zero-board-writes
# WMBT: wmbt:govern-lifecycle:E051
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E051-UNIT-002 — the issue-creation drive path performs zero board writes.

Post-removal contract: creating a new ATDD issue carries state via the initial
``atdd:INIT`` label (REST) plus the manifest entry — no ``add_issue_to_project``,
``set_project_field_select`` or ``set_project_field_text`` Projects-v2 writes.

RED now: create_new_issue() still calls ``client.add_issue_to_project(...)`` on
the creation path, so assert_not_called fails.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.platform]

BOARD_WRITE_METHODS = (
    "add_issue_to_project",
    "set_project_field_select",
    "set_project_field_text",
)


def _setup(tmp_path: Path) -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    (cfg / "manifest.yaml").write_text(yaml.safe_dump({"sessions": [], "issues": {}}))
    return tmp_path


def test_issue_creation_zero_board_writes(tmp_path):
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.create_issue.return_value = 777

    with patch.object(mgr, "_build_github_client", return_value=client), \
         patch.object(mgr, "_discover_wmbts", return_value=[]), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.create_new_issue("demo-decouple", issue_type="cleanup")

    assert rc != 1, "creation should not fail"

    # Initial label carries the phase via REST.
    create_calls = client.create_issue.call_args
    labels = create_calls.kwargs.get("labels") if create_calls.kwargs else create_calls.args[2]
    assert "atdd:INIT" in labels, "initial phase carried by the atdd:INIT label"

    for method in BOARD_WRITE_METHODS:
        getattr(client, method).assert_not_called()

    manifest = yaml.safe_load((target / ".atdd" / "manifest.yaml").read_text())
    assert "777" in manifest.get("issues", {}), "new issue registered in manifest"
