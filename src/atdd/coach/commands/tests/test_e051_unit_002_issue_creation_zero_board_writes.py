# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E051-UNIT-002-issue-creation-zero-board-writes
# Acceptance: acc:govern-lifecycle:E051-UNIT-002-issue-creation-zero-board-writes
# WMBT: wmbt:govern-lifecycle:E051
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E051-UNIT-002 — the issue-creation drive path performs zero board writes.

Post-removal contract: creating a new ATDD issue carries state via the initial
``atdd:INIT`` label (REST) plus a State Store work item — no
``add_issue_to_project``, ``set_project_field_select`` or
``set_project_field_text`` Projects-v2 writes. (#1270 Slice G: the
``.atdd/manifest.yaml`` mirror was deleted; the store is the sole registry.)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER
from atdd.state.store import StateStore

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
    return tmp_path


def test_issue_creation_zero_board_writes(tmp_path):
    target = _setup(tmp_path)
    mgr = IssueManager(target_dir=target)

    client = MagicMock()
    client.create_issue.return_value = 777

    with patch.object(mgr, "_build_github_client", return_value=client), \
         patch.object(mgr, "_discover_wmbts", return_value=[]):
        rc = mgr.create_new_issue("demo-decouple", issue_type="cleanup")

    assert rc != 1, "creation should not fail"

    # Initial label carries the phase via REST.
    create_calls = client.create_issue.call_args
    labels = create_calls.kwargs.get("labels") if create_calls.kwargs else create_calls.args[2]
    assert "atdd:INIT" in labels, "initial phase carried by the atdd:INIT label"

    for method in BOARD_WRITE_METHODS:
        getattr(client, method).assert_not_called()

    # The new issue is registered in the State Store (sole registry), not a manifest.
    db = init_state_store(start=target)
    store = StateStore(connect(db))
    ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", "777")
    assert ref is not None, "new issue registered as a store work item"
    assert store.objects.get(ref.object_uid).state == "INIT"
    assert not (target / ".atdd" / "manifest.yaml").exists()
