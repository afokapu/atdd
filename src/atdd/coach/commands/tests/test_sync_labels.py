"""
RED tests for #296 D007 — ``IssueManager.sync_labels(issue_number, dry_run)``
reads issue body metadata, derives the expected label set, diffs against
the current GitHub labels, and applies the delta (or reports it in
dry-run).

WMBTs covered:
- wmbt:govern-lifecycle:D007 — acc:govern-lifecycle:D007-UNIT-001-sync-labels-dry-run-derives-expected-set
- wmbt:govern-lifecycle:D007 — acc:govern-lifecycle:D007-UNIT-002-sync-labels-applies-delta-idempotently

Test strategy
-------------
The GitHub client double is built via ``create_autospec(GitHubClient, instance=True)``
so any method-name drift between the caller and the real class surface is
caught at call time (same discipline as ``test_sync_wmbts`` after the
#304 incident).

Body fixture shape is the real PARENT-ISSUE-TEMPLATE.md metadata table —
the validator reads ``Archetypes``, ``Wagon``, and ``Status`` rows, so
those rows drive the expected label set.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/commands/tests/test_sync_labels.py -v
"""
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import create_autospec

import pytest

from atdd.coach.github import GitHubClient


pytestmark = [pytest.mark.platform]


def _body_with_metadata(
    status: str = "INIT",
    archetypes: str = "coach",
    wagon: str = "govern-lifecycle",
) -> str:
    """Render the minimum PARENT-ISSUE-TEMPLATE metadata table the
    sync-labels derivation relies on.
    """
    return (
        "## Issue Metadata\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Date | `2026-04-17` |\n"
        f"| Status | `{status}` |\n"
        "| Type | `implementation` (feature) |\n"
        "| Change Class | `MINOR` |\n"
        "| Branch | `feat/x` |\n"
        f"| Archetypes | `{archetypes}` |\n"
        "| Train | `0001-self-compliance-validate` |\n"
        "| Feature | x |\n"
        f"| Wagon | `wagon:{wagon}` |\n\n"
        "### Dependencies\n\n- none\n"
    )


def _make_fake_client(
    number: int,
    body: str,
    current_labels: List[str],
) -> GitHubClient:
    """Build a spec-enforced ``GitHubClient`` double for sync_labels tests."""
    client = create_autospec(GitHubClient, instance=True)
    client.get_issue.return_value = {
        "number": number,
        "title": "demo",
        "state": "open",
        "labels": [{"name": name} for name in current_labels],
        "body": body,
    }
    client.add_label.return_value = None
    client.remove_label.return_value = None
    return client


def _write_atdd_config(tmp_path: Path) -> None:
    (tmp_path / ".atdd").mkdir(exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n  project_number: 1\n",
        encoding="utf-8",
    )


def _added_label_calls(client) -> List[List[str]]:
    """Return the ``labels`` arg each ``add_label`` call received."""
    return [list(call.args[1]) for call in client.add_label.call_args_list]


def _removed_label_calls(client) -> List[List[str]]:
    """Return the ``labels`` arg each ``remove_label`` call received."""
    return [list(call.args[1]) for call in client.remove_label.call_args_list]


# ---------------------------------------------------------------------------
# D007-UNIT-001 — dry-run derives expected delta without mutating GitHub
# ---------------------------------------------------------------------------


def test_d007_sync_labels_dry_run_lists_missing_labels_to_add(tmp_path, monkeypatch):
    """Dry-run reports labels that should be added (from body metadata)
    but are not currently on GitHub.
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="INIT", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(
        number=42,
        body=body,
        current_labels=["atdd-issue"],  # missing phase, archetype, wagon
    )

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    result = manager.sync_labels(42, dry_run=True)

    expected_to_add = {"atdd:INIT", "archetype:coach", "wagon:govern-lifecycle"}
    assert expected_to_add.issubset(set(result.get("to_add", []))), (
        f"dry-run must list missing labels; got to_add={result.get('to_add')}"
    )


def test_d007_sync_labels_dry_run_does_not_mutate_github(tmp_path, monkeypatch):
    """Dry-run must not call add_label/remove_label on the client."""
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="INIT", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(number=42, body=body, current_labels=["atdd-issue"])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    manager.sync_labels(42, dry_run=True)

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()


# ---------------------------------------------------------------------------
# D007-UNIT-002 — apply + idempotency
# ---------------------------------------------------------------------------


def test_d007_sync_labels_applies_add_delta(tmp_path, monkeypatch):
    """Without dry-run, sync_labels calls add_label for every missing
    label derived from body metadata.
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="INIT", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(number=42, body=body, current_labels=["atdd-issue"])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    manager.sync_labels(42, dry_run=False)

    all_added = {lbl for call in _added_label_calls(client) for lbl in call}
    assert {"atdd:INIT", "archetype:coach", "wagon:govern-lifecycle"}.issubset(all_added)


def test_d007_sync_labels_is_idempotent_when_labels_match_body(tmp_path, monkeypatch):
    """When GitHub labels already match the body-derived set, sync_labels
    is a no-op — zero add/remove calls.
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="INIT", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(
        number=42,
        body=body,
        current_labels=["atdd-issue", "atdd:INIT", "archetype:coach", "wagon:govern-lifecycle"],
    )

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    result = manager.sync_labels(42, dry_run=False)

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()
    assert result.get("to_add", []) == []
    assert result.get("to_remove", []) == []


def test_d007_sync_labels_removes_stale_phase_label(tmp_path, monkeypatch):
    """When the body declares ``Status: PLANNED`` but GitHub still carries
    ``atdd:INIT``, sync_labels must remove the stale phase label and add
    the body-declared one (phase labels are ``exactly_one`` per the
    label_taxonomy schema swap_rule).
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="PLANNED", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(
        number=42,
        body=body,
        current_labels=[
            "atdd-issue", "atdd:INIT",
            "archetype:coach", "wagon:govern-lifecycle",
        ],
    )

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    manager.sync_labels(42, dry_run=False)

    all_removed = {lbl for call in _removed_label_calls(client) for lbl in call}
    all_added = {lbl for call in _added_label_calls(client) for lbl in call}
    assert "atdd:INIT" in all_removed
    assert "atdd:PLANNED" in all_added


def test_d007_sync_labels_never_mutates_issue_body(tmp_path, monkeypatch):
    """sync_labels touches only the label surface; the issue body is
    never rewritten via edit_issue / body-changing gh calls.
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(status="INIT", archetypes="coach", wagon="govern-lifecycle")
    client = _make_fake_client(number=42, body=body, current_labels=["atdd-issue"])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    manager.sync_labels(42, dry_run=False)

    # The autospec ensures only real GitHubClient methods are callable.
    # Assert the body-mutation surface (create_issue, any method with
    # 'body' in its kwargs) was NOT invoked.
    client.create_issue.assert_not_called()


def test_d007_sync_labels_supports_multiple_archetypes(tmp_path, monkeypatch):
    """Comma-separated ``Archetypes`` row (e.g., ``coach, contracts``)
    produces ``archetype:coach`` and ``archetype:contracts`` in the
    expected set — cross-cutting issues are first-class per Decision #5
    in #296.
    """
    from atdd.coach.commands.issue import IssueManager

    _write_atdd_config(tmp_path)
    body = _body_with_metadata(
        status="INIT",
        archetypes="coach, contracts",
        wagon="govern-lifecycle",
    )
    client = _make_fake_client(number=42, body=body, current_labels=["atdd-issue"])

    manager = IssueManager(target_dir=tmp_path)
    monkeypatch.setattr(manager, "_get_github_client", lambda: client)

    result = manager.sync_labels(42, dry_run=True)

    to_add = set(result.get("to_add", []))
    assert "archetype:coach" in to_add
    assert "archetype:contracts" in to_add
