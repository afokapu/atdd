"""
RED tests for #280 D002 — atdd issue <N> --sync-wmbts backfill path.

WMBT covered:
- wmbt:govern-lifecycle:D002 — acc:govern-lifecycle:D002-UNIT-001-sync-wmbts-backfill

These tests exercise IssueManager.sync_wmbts() against a pure file-system
fixture: a temp repo with a manifest session, a feature YAML, and WMBT
YAMLs. A fake GitHub client captures calls so the tests never touch the
network.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_sync_wmbts.py -v
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

pytestmark = [pytest.mark.platform]


class _FakeGithubClient:
    """Minimal fake of atdd.coach.github.GitHubClient for sync_wmbts tests."""

    def __init__(
        self,
        parent_number: int,
        existing_sub_titles: Optional[List[str]] = None,
    ):
        self.parent_number = parent_number
        self.existing_sub_titles = list(existing_sub_titles or [])
        self.created_issues: List[Dict[str, Any]] = []
        self.sub_issue_links: List[tuple] = []
        self._next_number = 9000

    def list_sub_issues(self, parent_number: int) -> List[Dict[str, Any]]:
        assert parent_number == self.parent_number
        return [
            {"number": 8000 + i, "title": title}
            for i, title in enumerate(self.existing_sub_titles)
        ]

    def create_issue(
        self,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> int:
        self._next_number += 1
        self.created_issues.append(
            {"number": self._next_number, "title": title, "body": body, "labels": list(labels or [])}
        )
        return self._next_number

    def add_sub_issue(self, parent_number: int, sub_number: int) -> None:
        self.sub_issue_links.append((parent_number, sub_number))


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
    fake_client = _FakeGithubClient(parent_number=270, existing_sub_titles=[])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake_client)

    created = manager.sync_wmbts(270)

    assert created == 3
    assert len(fake_client.created_issues) == 3
    created_titles = {issue["title"] for issue in fake_client.created_issues}
    assert any("D006" in t for t in created_titles)
    assert any("D007" in t for t in created_titles)
    assert any("D008" in t for t in created_titles)
    assert len(fake_client.sub_issue_links) == 3
    for parent, _sub in fake_client.sub_issue_links:
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
    fake_client = _FakeGithubClient(parent_number=270, existing_sub_titles=existing)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake_client)

    created = manager.sync_wmbts(270)

    assert created == 0
    assert fake_client.created_issues == []
    assert fake_client.sub_issue_links == []


def test_d002_sync_wmbts_creates_only_missing_when_some_exist(tmp_path, monkeypatch):
    """D002: sync_wmbts must fill in just the gap — existing sub-issues are
    left alone, missing ones are created.
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    existing = [
        "wmbt:implement-code:D006 — minimize composition root drift",
    ]
    fake_client = _FakeGithubClient(parent_number=270, existing_sub_titles=existing)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake_client)

    created = manager.sync_wmbts(270)

    assert created == 2
    created_titles = {issue["title"] for issue in fake_client.created_issues}
    assert not any("D006" in t for t in created_titles)
    assert any("D007" in t for t in created_titles)
    assert any("D008" in t for t in created_titles)


def test_d002_sync_wmbts_errors_when_issue_not_in_manifest(tmp_path, monkeypatch):
    """D002: sync_wmbts must refuse to operate on issue numbers not present
    in the local manifest (prevents drift).
    """
    from atdd.coach.commands.issue import IssueManager

    _build_fixture_repo(tmp_path)
    fake_client = _FakeGithubClient(parent_number=9999)

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: fake_client)

    rc = manager.sync_wmbts(9999)

    assert rc == -1 or rc == 1
    assert fake_client.created_issues == []
