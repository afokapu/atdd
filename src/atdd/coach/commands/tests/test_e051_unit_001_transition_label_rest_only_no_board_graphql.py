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
``add_issue_to_project``. The State Store is the local state mirror (#1270
Slice G deleted the ``.atdd/manifest.yaml`` mirror).

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
    # Seed the State Store directly (the sole local registry, #1270 Slice G).
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
    from atdd.state.store import StateStore

    db = init_state_store(db_path=cfg / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        store.objects.upsert("demo", WORK_ITEM_KIND, state=status,
                             data={"issue_number": 384,
                                   "train": "0001-self-compliance-validate"})
        store.external_refs.link("demo", GITHUB_PROVIDER, "issue", "384",
                                 data={"source": "test-seed"})
    finally:
        conn.close()
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

    with patch.object(mgr, "_get_github_client", return_value=client):
        rc = mgr.update("384", status="GREEN")

    assert rc == 0, "label-only transition should succeed"
    client.add_label.assert_called_once_with(384, ["atdd:GREEN"])

    for method in BOARD_METHODS:
        getattr(client, method).assert_not_called()

    # #1270 Slice G: the local state mirror is the State Store, not the manifest.
    from atdd.state.work_item_reader import WorkItemReader
    with WorkItemReader(control_root=target) as reader:
        assert reader.status(384) == "GREEN", "the store is the local state mirror"
