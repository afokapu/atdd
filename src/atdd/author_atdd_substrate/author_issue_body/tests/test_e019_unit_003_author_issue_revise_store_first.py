# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-003-author-issue-revise-store-first
# Acceptance: acc:govern-lifecycle:E019-UNIT-003-author-issue-revise-store-first
# WMBT: wmbt:govern-lifecycle:E019
# Phase: RED
# Layer: application
"""E019-UNIT-003 — `atdd author issue --revise` validates, stores, then projects.

The later-body-edit path must not be a raw ``gh issue edit`` escape hatch. It
validates the replacement body against ``issue.schema.json`` first, writes the
canonical work item in the State Store, and only then projects the body to
GitHub via the adapter (or the outbox on projection failure).
"""
from __future__ import annotations

from pathlib import Path

from ._publish_helpers import open_store, run_author_issue, work_item, work_item_uid

ISSUE_NUMBER = 1430


def _body(issue_type: str = "refactor") -> str:
    from atdd.planner.commands.author import create_issue_body

    return create_issue_body({
        "title": "Detailed Wave 0 follow-up",
        "status": "INIT",
        "type": issue_type,
        "branch": "feat/revise-issue-body-and-type-via-store",
        "train": "0003-author-substrate",
        "feature": "feature:author-atdd-substrate:author-issue-body",
        "scope": {
            "in_scope": [
                "revise an existing issue body through the store-first author path",
                "keep the revised body detailed enough for worker handoff",
            ],
            "out_of_scope": ["create the Wave 0 F1/F2 follow-up issues"],
            "dependencies": ["State Store external_refs has the GitHub issue link"],
            "done_when": ["the revision writes store data before GitHub projection"],
        },
    })


def _seed_issue(control_root: Path) -> None:
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control_root))
    try:
        create_work_item(
            conn,
            "revise-probe",
            state="INIT",
            data={
                "title": "Old body",
                "type": "implementation",
                "body": "old body",
            },
            github_number=ISSUE_NUMBER,
        )
    finally:
        conn.close()


def test_revise_updates_store_then_projects_body(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed_issue(tmp_path)
    revised = _body("refactor")
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    projected: list[tuple[int, str]] = []

    def _fake_update_body(issue: int, body: str) -> None:
        store, conn = open_store(tmp_path)
        try:
            obj = work_item(store, "revise-probe")
        finally:
            conn.close()
        assert obj is not None
        assert obj.data["body"] == body
        assert obj.data["type"] == "refactor"
        projected.append((issue, body))

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_body",
        _fake_update_body,
        raising=False,
    )

    code, out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
    ])

    assert code == 0
    assert out == revised
    assert projected == [(ISSUE_NUMBER, revised)]

    store, conn = open_store(tmp_path)
    try:
        obj = work_item(store, "revise-probe")
        events = store.events.list(object_uid=work_item_uid(store, "revise-probe"))
    finally:
        conn.close()

    assert obj is not None
    assert obj.state == "INIT", "revision must preserve lifecycle state"
    assert obj.data["body"] == revised
    assert obj.data["type"] == "refactor"
    assert [e.event_type for e in events] == ["issue_revised"]


def test_revise_rejects_invalid_body_before_store_or_github_write(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed_issue(tmp_path)
    invalid = _body("refactor").replace("### Graph Context", "### Missing Graph Context")
    body_path = tmp_path / "invalid.md"
    body_path.write_text(invalid, encoding="utf-8")

    def _fail_update_body(*_args, **_kwargs) -> None:
        raise AssertionError("invalid body must not reach GitHub projection")

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_body",
        _fail_update_body,
        raising=False,
    )

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
    ])

    assert code == 1
    store, conn = open_store(tmp_path)
    try:
        obj = work_item(store, "revise-probe")
        events = store.events.list(object_uid=work_item_uid(store, "revise-probe"))
    finally:
        conn.close()

    assert obj is not None
    assert obj.data["body"] == "old body"
    assert obj.data["type"] == "implementation"
    assert events == []


def test_revise_dry_run_validates_without_store_or_github(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    revised = _body("refactor")
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")

    def _fail_update_body(*_args, **_kwargs) -> None:
        raise AssertionError("dry-run must not project to GitHub")

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_body",
        _fail_update_body,
        raising=False,
    )

    code, out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
        "--dry-run",
    ])

    assert code == 0
    assert out == revised
    assert not (tmp_path / ".atdd" / "state" / "state.sqlite").exists()


def test_issue_body_validator_rejects_out_of_enum_type():
    from atdd.planner.commands.author import validate_issue_body

    invalid = _body("spaceship")
    violations = validate_issue_body(invalid)

    assert violations
    assert any("type" in v.lower() for v in violations)
