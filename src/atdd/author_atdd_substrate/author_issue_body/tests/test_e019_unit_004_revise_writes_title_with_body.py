# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-UNIT-004-revise-writes-title-with-body
# Acceptance: acc:govern-lifecycle:E019-UNIT-004-revise-writes-title-with-body
# WMBT: wmbt:govern-lifecycle:E019
# Phase: RED
# Layer: application
"""E019-UNIT-004 — `--revise` carries the title with the body, or carries neither.

``--revise`` was built to correct bodies, and it corrected only bodies: it wrote
``data.body`` and left ``data.title`` naming whatever the issue used to be about.
Measured on #1639, whose stored title still read *"…atomize component + interface
into nodes"* after a revise whose H1 read *"Decommission all 17 planner legacy
convention monoliths"*. The store disagreed with itself, and the GitHub title —
never reprojected — matched neither.

The title is not a second thing to remember to update. It is the same fact the
body's H1 states, so the write that takes one takes the other, and the
projection that carries one carries the other. These tests pin that: derived
from the H1 by default, refused when an explicit ``--title`` contradicts it,
projected in a single edit, and outboxed together when the provider is down.

Nothing here rests on ``atdd author issue --check`` — per #1647 that is a
substring search, not a heading check, and would pass a body whose H1 disagrees
with the stored title. Every assertion reads ``data.title`` out of the store.
"""
from __future__ import annotations

from pathlib import Path

from ._publish_helpers import open_store, run_author_issue

ISSUE_NUMBER = 1639
SLUG = "retitle-probe"

SEEDED_TITLE = "Body and title before the revision"
REVISED_TITLE = "Decommission all 17 planner legacy convention monoliths"


def _body(title: str, issue_type: str = "refactor") -> str:
    from atdd.planner.commands.author import create_issue_body

    return create_issue_body({
        "title": title,
        "status": "INIT",
        "type": issue_type,
        "branch": "fix/author-issue-revise-drops-title",
        "train": "0003-author-substrate",
        "feature": "feature:author-atdd-substrate:author-issue-body",
        "scope": {
            "in_scope": ["carry the title with the body through the revise path"],
            "out_of_scope": ["the rename verb's uid grammar (#1653)"],
            "dependencies": ["State Store external_refs links the github issue"],
            "done_when": ["data.title, the body H1 and the GitHub title agree"],
        },
    })


def _seed(control_root: Path) -> None:
    """Seed a work item whose stored title and body H1 already agree.

    Starting from agreement matters: it makes the post-condition a statement
    about the revision rather than about the seed.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control_root))
    try:
        create_work_item(
            conn,
            SLUG,
            state="INIT",
            data={
                "title": SEEDED_TITLE,
                "type": "implementation",
                "body": _body(SEEDED_TITLE, "implementation"),
            },
            github_number=ISSUE_NUMBER,
        )
    finally:
        conn.close()


def _stored(control_root: Path):
    store, conn = open_store(control_root)
    try:
        return store.objects.get(SLUG)
    finally:
        conn.close()


def _capture_projection(monkeypatch) -> list[dict]:
    """Record what the provider projection was asked to write."""
    seen: list[dict] = []

    def _fake_update_issue(issue: int, *, title=None, body=None) -> None:
        seen.append({"issue": issue, "title": title, "body": body})

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_issue",
        _fake_update_issue,
        raising=False,
    )
    return seen


def test_revise_derives_the_stored_title_from_the_new_body_h1(tmp_path, monkeypatch):
    """The defect, directly: a body H1 change must move `data.title` with it."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(REVISED_TITLE)
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    projected = _capture_projection(monkeypatch)

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
    ])

    assert code == 0
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["body"] == revised
    assert obj.data["title"] == REVISED_TITLE, (
        "the store took the new body but kept the superseded title — this is "
        "exactly the #1639 divergence"
    )
    assert obj.state == "INIT", "a revision must not move the lifecycle state"
    assert projected == [
        {"issue": ISSUE_NUMBER, "title": REVISED_TITLE, "body": revised}
    ], "the projection must re-title in the same edit that rewrites the body"


def test_revise_leaves_the_title_alone_when_the_h1_is_unchanged(tmp_path, monkeypatch):
    """Deriving the title is not the same as churning it."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(SEEDED_TITLE, "refactor")
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    _capture_projection(monkeypatch)

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
    ])

    assert code == 0
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["title"] == SEEDED_TITLE
    assert obj.data["type"] == "refactor"


def test_an_explicit_title_agreeing_with_the_h1_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(REVISED_TITLE)
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    projected = _capture_projection(monkeypatch)

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--title", REVISED_TITLE,
    ])

    assert code == 0
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["title"] == REVISED_TITLE
    assert projected and projected[0]["title"] == REVISED_TITLE


def test_an_explicit_title_contradicting_the_h1_is_refused_before_any_write(tmp_path, monkeypatch):
    """Two sources of the same fact that disagree is the bug, not an input format."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(REVISED_TITLE)
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")

    def _fail(*_args, **_kwargs):
        raise AssertionError("a contradicted title must not reach the provider")

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_issue", _fail, raising=False,
    )
    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_body", _fail, raising=False,
    )

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--title", "Something else entirely",
    ])

    assert code == 1, "a contradicted title is a schema violation, not a store failure"
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["title"] == SEEDED_TITLE, "the refused revision must leave the store untouched"
    assert obj.data["body"] == _body(SEEDED_TITLE, "implementation")


def test_a_title_only_revision_needs_no_body_file(tmp_path, monkeypatch):
    """Correcting a title alone is the operation #1639 actually wanted."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    projected = _capture_projection(monkeypatch)

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--title", "A corrected title",
    ])

    assert code == 0
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["title"] == "A corrected title"
    assert obj.data["body"] == _body(SEEDED_TITLE, "implementation"), (
        "a title-only revision must not disturb the body"
    )
    assert projected == [
        {"issue": ISSUE_NUMBER, "title": "A corrected title", "body": None}
    ], "a title-only revision projects the title and nothing else"


def test_a_failed_projection_outboxes_the_title_alongside_the_body(tmp_path, monkeypatch):
    """A deferred retry that carries only the body would re-open the divergence."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(REVISED_TITLE)
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")

    def _unreachable(*_args, **_kwargs):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.update_issue", _unreachable, raising=False,
    )

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
    ])

    assert code == 0, "the store write is authoritative; a projection failure defers"
    obj = _stored(tmp_path)
    assert obj is not None
    assert obj.data["title"] == REVISED_TITLE, "the store revision stands"

    store, conn = open_store(tmp_path)
    try:
        pending = store.sync.pending_outbox()
    finally:
        conn.close()

    assert len(pending) == 1, f"expected one deferred projection, got {pending}"
    assert pending[0].payload["title"] == REVISED_TITLE, (
        "the deferred payload must carry the title, or the retry restores the "
        "body and leaves the title superseded all over again"
    )
    assert pending[0].payload["body"] == revised


def test_the_revision_leaves_store_title_and_body_h1_in_agreement(tmp_path, monkeypatch):
    """The invariant the whole issue is about, asserted end to end in the store."""
    from atdd.planner.commands.author_issue import title_violations

    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed(tmp_path)
    revised = _body(REVISED_TITLE)
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    _capture_projection(monkeypatch)

    code, _out = run_author_issue([
        "--revise", str(ISSUE_NUMBER), "--body-file", str(body_path),
    ])

    assert code == 0
    obj = _stored(tmp_path)
    assert obj is not None
    assert title_violations(obj.data["title"], obj.data["body"]) == [], (
        "a work item the revise path just wrote must not be one the consistency "
        "check would flag"
    )
