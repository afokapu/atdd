"""
RED tests for #304 — GitHubClient mock drift prevention.

WMBT covered:
- wmbt:govern-lifecycle:D304-UNIT-001-sync-wmbts-autospec

These tests use ``unittest.mock.create_autospec(GitHubClient, instance=True)``
so that any method-name drift between the caller in ``IssueManager.sync_wmbts``
and the real ``GitHubClient`` class is caught at mock construction / first
call instead of at runtime in production.

Before the Layer 1 fix (``issue.py:436``), ``sync_wmbts`` calls
``client.list_sub_issues(...)``, which is not a method on the real
``GitHubClient``; with ``create_autospec``, the mock raises ``AttributeError``
on that call, mirroring the production crash.

Run: PYTHONPATH=src python3 -m pytest -q \\
    src/atdd/coach/commands/tests/test_sync_wmbts_autospec.py -v
"""
from pathlib import Path
from typing import List
from unittest.mock import create_autospec

import pytest
import yaml

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.platform]


def _write_atdd_config(atdd_dir: Path) -> None:
    (atdd_dir / "config.yaml").write_text(
        "github:\n"
        "  repo: afokapu/atdd\n"
        "  project_number: 1\n",
        encoding="utf-8",
    )


def _seed_store_with_feature(
    repo_root: Path,
    issue_number: int,
    wagon: str,
    feature: str,
) -> None:
    """Register the work item in the State Store, carrying its wagon and feature.

    #1400 CORE-034 (Y002): ``sync_wmbts`` reads these from the store. The manifest session this
    replaces was a read-fallback, and it is retired.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=repo_root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            feature, WORK_ITEM_KIND, state="PLANNED",
            data={
                "id": str(issue_number),
                "type": "implementation",
                "wagon": wagon,
                "feature": f"feature:{wagon}:{feature}",
            },
        )
        store.external_refs.link(
            feature, GITHUB_PROVIDER, "issue", str(issue_number), data={"source": "test-fixture"},
        )
    finally:
        conn.close()


def _write_feature_yaml(
    plan_dir: Path, wagon: str, feature: str, wmbt_ids: List[str]
) -> None:
    wagon_dir = plan_dir / wagon.replace("-", "_")
    (wagon_dir / "features").mkdir(parents=True, exist_ok=True)
    feature_path = wagon_dir / "features" / f"{feature.replace('-', '_')}.yaml"
    feature_path.write_text(
        yaml.safe_dump(
            {
                "urn": f"feature:{wagon}:{feature}",
                "wagon": f"wagon:{wagon}",
                "wmbts": [f"wmbt:{wagon}:{wid}" for wid in wmbt_ids],
            }
        ),
        encoding="utf-8",
    )


def _write_wmbt_yaml(
    plan_dir: Path, wagon: str, wmbt_id: str, statement: str
) -> None:
    wagon_dir = plan_dir / wagon.replace("-", "_")
    wagon_dir.mkdir(parents=True, exist_ok=True)
    path = wagon_dir / f"{wmbt_id}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "urn": f"wmbt:{wagon}:{wmbt_id}",
                "statement": statement,
                "acceptances": [
                    {
                        "identity": {
                            "urn": f"acc:{wagon}:{wmbt_id}-UNIT-001-example",
                            "purpose": "Example acceptance",
                            "phase": "GREEN",
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_repo(tmp_path: Path, issue_number: int = 304) -> Path:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    _write_atdd_config(atdd_dir)
    _seed_store_with_feature(
        tmp_path,
        issue_number=issue_number,
        wagon="govern-lifecycle",
        feature="fix-github-client-mock-drift",
    )

    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    _write_feature_yaml(
        plan_dir,
        wagon="govern-lifecycle",
        feature="fix-github-client-mock-drift",
        wmbt_ids=["D304"],
    )
    _write_wmbt_yaml(
        plan_dir,
        wagon="govern-lifecycle",
        wmbt_id="D304",
        statement="mock drift detected at construction",
    )

    return tmp_path


def test_sync_wmbts_invokes_get_sub_issues_on_real_client_surface(
    tmp_path, monkeypatch
):
    """D304 RED: sync_wmbts must call ``client.get_sub_issues`` — the real
    ``GitHubClient`` method name — not the hand-rolled ``list_sub_issues``.

    Build the client via ``create_autospec(GitHubClient, instance=True)`` so
    that any attribute not on the real class raises ``AttributeError`` at
    call time. Before the Layer 1 fix this test fails with the same
    AttributeError seen in production.
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)

    client = create_autospec(GitHubClient, instance=True)
    client.get_sub_issues.return_value = []
    client.create_issue.return_value = 9001
    client.add_sub_issue.return_value = None

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    created = manager.sync_wmbts(304)

    assert created == 1
    client.get_sub_issues.assert_called_once_with(304)
    client.create_issue.assert_called_once()
    client.add_sub_issue.assert_called_once()


def test_sync_wmbts_idempotent_against_autospec_client(tmp_path, monkeypatch):
    """D304 RED: sync_wmbts must be idempotent when all WMBT sub-issues
    already exist, using the real-surface ``get_sub_issues`` name."""
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)

    client = create_autospec(GitHubClient, instance=True)
    client.get_sub_issues.return_value = [
        {
            "number": 8001,
            "title": "wmbt:govern-lifecycle:D304 — mock drift detected at construction",
        }
    ]

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    created = manager.sync_wmbts(304)

    assert created == 0
    client.get_sub_issues.assert_called_once_with(304)
    client.create_issue.assert_not_called()
    client.add_sub_issue.assert_not_called()


def test_autospec_rejects_nonexistent_client_method():
    """D304 RED: autospec must guard the boundary: attempting to call a
    method that does not exist on ``GitHubClient`` raises AttributeError at
    call time. This is the drift-detection property the validator relies on.
    """
    client = create_autospec(GitHubClient, instance=True)

    with pytest.raises(AttributeError):
        client.list_sub_issues(123)  # type: ignore[attr-defined]
