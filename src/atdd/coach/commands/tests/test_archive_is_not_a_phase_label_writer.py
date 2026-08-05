# URN: test:coach:issue:archive-is-not-a-phase-label-writer
# Issue: #1742 (child of #1400)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1742 — `IssueManager._archive_github` must not be a second `atdd:*` writer.

Every REFACTOR→COMPLETE transition wrote `atdd:COMPLETE` twice: once by
`IssueManager.update` (the sanctioned projection) and again ~3 s later by a raw
remove-then-add swap inside `_archive_github`, reached from
`issue_transition.apply_transition`. Nine sampled issues showed the identical
four-event terminal shape on the wire; the diagnosis is committed at
`docs/1400-findings/1742-second-writer-diagnosis.md`.

Two defects held it open, and both are asserted here:

1. The already-archived short-circuit compared ``state == "closed"`` while
   ``gh issue view --json state`` answers UPPERCASE ``"CLOSED"`` — so the guard
   never fired, for any issue, ever. All nine samples were already closed by
   their merge before the terminal transition ran.
2. The swap itself bypassed ``_write_phase_label``, the sole authoritative
   label writer, and so escaped the phase machine, the train gate and the
   COMPLETE gates.

The casing assertions below deliberately drive the client with ``"CLOSED"`` —
the value the real ``gh`` returns. A fixture that said ``"closed"`` would have
passed against the broken guard and proved nothing.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from atdd.coach.commands.issue import IssueManager
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore


def _init_repo(tmp_path):
    """A control root whose store holds #1689 at REFACTOR."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "github:\n  repo: owner/repo\n  project_id: PVT_test\n", encoding="utf-8"
    )
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    conn = connect(db)
    try:
        store = StateStore(conn)
        store.objects.upsert(
            "second-writer-sample", WORK_ITEM_KIND, state="REFACTOR",
            data={"id": "1689", "issue_number": 1689, "type": "implementation"},
        )
        store.external_refs.link(
            "second-writer-sample", GITHUB_PROVIDER, "issue", "1689",
            data={"source": "test-seed"},
        )
    finally:
        conn.close()
    return IssueManager(target_dir=tmp_path)


def _store(tmp_path):
    return StateStore(connect(tmp_path / ".atdd" / "state" / "state.sqlite"))


def _client(monkeypatch, mgr, *, state, labels=None, subs=None):
    """A GitHub client answering exactly what `gh` answers on the wire."""
    client = MagicMock()
    client.get_issue.return_value = {
        "number": 1689,
        "state": state,
        "labels": labels if labels is not None
        else [{"name": "atdd-issue"}, {"name": "atdd:COMPLETE"}],
    }
    client.get_sub_issues.return_value = subs if subs is not None else []
    monkeypatch.setattr(mgr, "_get_github_client", lambda: client)
    return client


# ---------------------------------------------------------------------------
# The casing guard (defect 1)
# ---------------------------------------------------------------------------


def test_uppercase_closed_short_circuits_every_github_mutation(tmp_path, monkeypatch):
    """`gh` says "CLOSED"; the guard must recognize it and write nothing.

    This is the exact reproduction of all nine sampled duplicates: the merge
    closed the issue, then the terminal transition ran `archive()` over it.
    """
    mgr = _init_repo(tmp_path)
    client = _client(monkeypatch, mgr, state="CLOSED")

    assert mgr._archive_github("1689") == 0

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()
    client.close_issue.assert_not_called()


def test_lowercase_closed_is_short_circuited_too(tmp_path, monkeypatch):
    """The REST API spells it lowercase. Normalization covers both spellings."""
    mgr = _init_repo(tmp_path)
    client = _client(monkeypatch, mgr, state="closed")

    assert mgr._archive_github("1689") == 0

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()
    client.close_issue.assert_not_called()


def test_already_closed_still_records_the_archive_in_the_store(tmp_path, monkeypatch):
    """The short-circuit skips GitHub, not the store.

    The store carries the terminal phase and the archived date. The pre-#1742
    early return sat *above* both writes — harmless only because it never fired.
    Now that it does fire (and fires on the common path), the record must
    survive it, or the fix would silently strand the archive metadata for every
    merged issue.
    """
    mgr = _init_repo(tmp_path)
    _client(monkeypatch, mgr, state="CLOSED")

    assert mgr._archive_github("1689") == 0

    ref = _store(tmp_path).external_refs.resolve(GITHUB_PROVIDER, "issue", "1689")
    obj = _store(tmp_path).objects.get(ref.object_uid)
    assert obj.state == "COMPLETE"
    assert obj.data["archived"]


def test_open_issue_is_still_closed_with_its_sub_issues(tmp_path, monkeypatch):
    """The guard must not swallow the work archive actually exists to do."""
    mgr = _init_repo(tmp_path)
    client = _client(
        monkeypatch, mgr, state="OPEN",
        labels=[{"name": "atdd-issue"}, {"name": "atdd:REFACTOR"}],
        subs=[{"number": 1690, "state": "open"}, {"number": 1691, "state": "closed"}],
    )

    assert mgr._archive_github("1689") == 0

    closed = [c.args[0] for c in client.close_issue.call_args_list]
    assert closed == [1690, 1689]
