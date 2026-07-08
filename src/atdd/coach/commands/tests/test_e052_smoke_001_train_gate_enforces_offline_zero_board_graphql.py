# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E052-SMOKE-001-train-gate-enforces-offline-zero-board-graphql
# Acceptance: acc:govern-lifecycle:E052-SMOKE-001-train-gate-enforces-offline-zero-board-graphql
# WMBT: wmbt:govern-lifecycle:E052
# Phase: RED
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E052-SMOKE-001 — the Train gate enforces offline with zero board GraphQL.

Against a real local source + plan/_trains.yaml and a recording client (no
PROJECT_TOKEN), the gate enforces membership using only the local source,
recording zero Projects-v2 field-value queries.

#1270 slice D: that local source is now the State Store (authoritative since
#1203); the manifest-mirror read-fallback is retired. The load-bearing contract
— enforce offline, zero board GraphQL — is unchanged.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.platform]


def _seed_store(root: Path, *, slug: str, issue_number: int, train: str) -> None:
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        store = StateStore(conn)
        store.objects.upsert(
            slug, WORK_ITEM_KIND, state="PLANNED",
            data={"issue_number": issue_number, "train": train},
        )
        store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number), data={})
    finally:
        conn.close()


def _setup(tmp_path: Path) -> Path:
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    (cfg / "config.yaml").write_text(
        yaml.safe_dump({"github": {"repo": "owner/repo", "project_id": "PVT_test"}})
    )
    # #1270 slice D: the train gate reads the local State Store, not the manifest.
    _seed_store(tmp_path, slug="demo", issue_number=384, train="0001-self-compliance-validate")
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

    assert rc == 0, "gate enforces successfully from the local store + plan/_trains.yaml"
    client.get_project_item_field_values.assert_not_called()
