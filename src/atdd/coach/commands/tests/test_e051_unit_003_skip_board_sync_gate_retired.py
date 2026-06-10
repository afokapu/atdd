# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E051-UNIT-003-skip-board-sync-gate-retired
# Acceptance: acc:govern-lifecycle:E051-UNIT-003-skip-board-sync-gate-retired
# WMBT: wmbt:govern-lifecycle:E051
# Phase: RED
# Harness: unit
# Assertion: behavioral
# Layer: backend
"""E051-UNIT-003 — the ATDD_SKIP_BOARD_SYNC bridge gate is retired.

Post-removal contract: label-only sync is UNCONDITIONAL. The temporary
``ATDD_SKIP_BOARD_SYNC`` env gate is deleted (not merely defaulted on), and
update() emits zero board GraphQL whether the var is unset or set to any value.

RED now: update() unconditionally reads/writes the board, so the "zero board
GraphQL regardless of env" assertion fails (the env var has no effect today).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import atdd.coach.commands.issue as issue_mod
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


def _make_issue() -> dict:
    return {
        "number": 384,
        "title": "demo",
        "state": "OPEN",
        "labels": [{"name": "atdd:RED"}, {"name": "atdd-issue"}],
        "body": "| Type | `cleanup` |\n",
    }


def _run_update(tmp_path):
    _setup(tmp_path)
    mgr = IssueManager(target_dir=tmp_path)
    client = MagicMock()
    client.get_issue.return_value = _make_issue()
    client.get_project_fields.return_value = {
        "ATDD Status": {"id": "field_status", "options": {"GREEN": "opt_green"}}
    }
    client.get_project_item_id.return_value = "item_abc"
    with patch.object(mgr, "_get_github_client", return_value=client), \
         patch.object(IssueManager, "_commit_manifest_change"):
        rc = mgr.update("384", status="GREEN")
    return rc, client


def test_skip_board_sync_token_absent_from_module(tmp_path):
    """The env gate is deleted from the shipped module, not merely defaulted on."""
    src = Path(issue_mod.__file__).read_text(encoding="utf-8")
    assert "ATDD_SKIP_BOARD_SYNC" not in src, (
        "ATDD_SKIP_BOARD_SYNC bridge gate must be removed, not defaulted on"
    )


def test_label_only_with_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ATDD_SKIP_BOARD_SYNC", raising=False)
    rc, client = _run_update(tmp_path)
    assert rc == 0
    for method in BOARD_METHODS:
        getattr(client, method).assert_not_called()


def test_label_only_with_env_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_SKIP_BOARD_SYNC", "1")
    rc, client = _run_update(tmp_path)
    assert rc == 0
    for method in BOARD_METHODS:
        getattr(client, method).assert_not_called()
