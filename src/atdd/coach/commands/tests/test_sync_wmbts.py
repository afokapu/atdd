"""
RED tests for #280 D002 — atdd issue <N> --sync-wmbts backfill path.

WMBT covered:
- wmbt:govern-lifecycle:D002 — acc:govern-lifecycle:D002-UNIT-001-sync-wmbts-backfill

These tests exercise IssueManager.sync_wmbts() against a pure file-system
fixture: a temp repo with a manifest session, a feature YAML, and WMBT
YAMLs. The GitHub client double is built via
``unittest.mock.create_autospec(GitHubClient, instance=True)`` so any
method-name drift between the caller and the real class surface is caught
at call time — this file previously used a hand-rolled stub and was part
of the #304 root cause.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_sync_wmbts.py -v
"""
from pathlib import Path
from typing import List, Optional
from unittest.mock import create_autospec

import pytest
import yaml

from atdd.coach.github import GitHubClient

pytestmark = [pytest.mark.platform]


def _make_fake_client(
    parent_number: int,
    existing_sub_titles: Optional[List[str]] = None,
):
    """Build a spec-enforced ``GitHubClient`` double for sync_wmbts tests.

    Returns an autospec mock. Sub-issue titles are wired onto
    ``get_sub_issues.return_value``; ``create_issue`` receives a
    side-effecting counter so the caller can observe distinct numbers per
    creation; ``add_sub_issue`` is a plain recorder.
    """
    titles = list(existing_sub_titles or [])
    client = create_autospec(GitHubClient, instance=True)
    client.get_sub_issues.return_value = [
        {"number": 8000 + i, "title": title}
        for i, title in enumerate(titles)
    ]

    state = {"next_number": 9000}

    def _create_issue(title, body, labels=None):
        state["next_number"] += 1
        return state["next_number"]

    client.create_issue.side_effect = _create_issue
    client.add_sub_issue.return_value = None
    return client


def _created_titles(client) -> List[str]:
    """Return the titles passed through ``create_issue`` on the autospec."""
    return [call.kwargs.get("title") or call.args[0] for call in client.create_issue.call_args_list]


def _sub_issue_parents(client) -> List[int]:
    """Return the parent-number arg each ``add_sub_issue`` call received."""
    return [call.args[0] for call in client.add_sub_issue.call_args_list]


def _write_atdd_config(atdd_dir: Path) -> None:
    (atdd_dir / "config.yaml").write_text(
        "github:\n"
        "  repo: afokapu/atdd\n"
        "  project_number: 1\n",
        encoding="utf-8",
    )


def _write_manifest_with_feature(
    atdd_dir: Path,
    issue_number: int,
    wagon: str,
    feature: str,
) -> None:
    (atdd_dir / "manifest.yaml").write_text(
        "version: '2.0'\n"
        "created: '2026-04-14'\n"
        "sessions:\n"
        f"  - id: '{issue_number}'\n"
        f"    slug: {feature}\n"
        "    file: null\n"
        f"    issue_number: {issue_number}\n"
        "    type: implementation\n"
        "    status: PLANNED\n"
        "    created: '2026-04-14'\n"
        "    archived: null\n"
        f"    wagon: {wagon}\n"
        f"    feature: 'feature:{wagon}:{feature}'\n",
        encoding="utf-8",
    )


def _write_feature_yaml(plan_dir: Path, wagon: str, feature: str, wmbt_ids: List[str]) -> None:
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


def _write_wmbt_yaml(plan_dir: Path, wagon: str, wmbt_id: str, statement: str) -> None:
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


def _build_fixture_repo(tmp_path: Path, issue_number: int = 270) -> Path:
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    _write_atdd_config(atdd_dir)
    _write_manifest_with_feature(
        atdd_dir,
        issue_number=issue_number,
        wagon="implement-code",
        feature="enforce-train-composition",
    )

    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    _write_feature_yaml(
        plan_dir,
        wagon="implement-code",
        feature="enforce-train-composition",
        wmbt_ids=["D006", "D007", "D008"],
    )
    for wmbt_id, stmt in [
        ("D006", "minimize composition root drift"),
        ("D007", "minimize wagon export drift"),
        ("D008", "minimize train yaml drift"),
    ]:
        _write_wmbt_yaml(plan_dir, wagon="implement-code", wmbt_id=wmbt_id, statement=stmt)

    return tmp_path


def test_d002_sync_wmbts_creates_missing_subissues(tmp_path, monkeypatch):
    """D002: sync_wmbts creates a GitHub sub-issue for every WMBT URN in the
    feature YAML that is not already present as a sub-issue.
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    client = _make_fake_client(parent_number=270, existing_sub_titles=[])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    created = manager.sync_wmbts(270)

    assert created == 3
    assert client.create_issue.call_count == 3
    titles = _created_titles(client)
    assert any("D006" in t for t in titles)
    assert any("D007" in t for t in titles)
    assert any("D008" in t for t in titles)
    assert client.add_sub_issue.call_count == 3
    for parent in _sub_issue_parents(client):
        assert parent == 270


def test_d002_sync_wmbts_is_idempotent_when_all_subissues_exist(tmp_path, monkeypatch):
    """D002: re-running sync_wmbts against a parent whose sub-issues already
    exist must create zero new issues and exit cleanly.
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    existing = [
        "wmbt:implement-code:D006 — minimize composition root drift",
        "wmbt:implement-code:D007 — minimize wagon export drift",
        "wmbt:implement-code:D008 — minimize train yaml drift",
    ]
    client = _make_fake_client(parent_number=270, existing_sub_titles=existing)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    created = manager.sync_wmbts(270)

    assert created == 0
    client.create_issue.assert_not_called()
    client.add_sub_issue.assert_not_called()


def test_d002_sync_wmbts_creates_only_missing_when_some_exist(tmp_path, monkeypatch):
    """D002: sync_wmbts must fill in just the gap — existing sub-issues are
    left alone, missing ones are created.
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    existing = [
        "wmbt:implement-code:D006 — minimize composition root drift",
    ]
    client = _make_fake_client(parent_number=270, existing_sub_titles=existing)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    created = manager.sync_wmbts(270)

    assert created == 2
    titles = _created_titles(client)
    assert not any("D006" in t for t in titles)
    assert any("D007" in t for t in titles)
    assert any("D008" in t for t in titles)


def test_d002_sync_wmbts_errors_when_issue_not_in_manifest(tmp_path, monkeypatch):
    """D002: sync_wmbts must refuse to operate on issue numbers not present
    in the local manifest (prevents drift).
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    client = _make_fake_client(parent_number=9999)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    rc = manager.sync_wmbts(9999)

    assert rc == -1 or rc == 1
    client.create_issue.assert_not_called()
