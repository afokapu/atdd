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

import logging
from unittest.mock import MagicMock

import atdd.coach.commands.issue as issue_module
import atdd.coach.commands.issue_lifecycle as lifecycle_module
from atdd.coach.commands.issue import IssueManager
from atdd.coach.commands.issue_transition import apply_transition
from atdd.coach.github import GitHubClientError
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


# ---------------------------------------------------------------------------
# The second writer itself (defect 2)
# ---------------------------------------------------------------------------


def test_archive_writes_no_phase_label_on_an_open_issue(tmp_path, monkeypatch):
    """Archive closes issues. It does not project phase — not on any path.

    The casing fix alone would have left the swap sitting behind a guard, one
    open issue away from firing. `archive()` has exactly one caller,
    `issue_transition.apply_transition`, which runs `IssueManager.update` —
    and therefore `_write_phase_label` — before it. The swap was redundant
    there and unsanctioned everywhere.
    """
    mgr = _init_repo(tmp_path)
    client = _client(
        monkeypatch, mgr, state="OPEN",
        labels=[{"name": "atdd-issue"}, {"name": "atdd:REFACTOR"}],
    )

    assert mgr._archive_github("1689") == 0

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()


def test_archive_leaves_a_stale_phase_label_alone(tmp_path, monkeypatch):
    """Not even a *wrong* label is archive's to correct.

    A label that disagrees with the store is a projection to be re-rendered by
    the authoritative writer, or reconciled by `atdd coach sync-labels`. Fixing
    it here is how the second writer justified itself in the first place.
    """
    mgr = _init_repo(tmp_path)
    client = _client(
        monkeypatch, mgr, state="OPEN",
        labels=[{"name": "atdd-issue"}, {"name": "atdd:RED"}],
    )

    assert mgr._archive_github("1689") == 0

    client.add_label.assert_not_called()
    client.remove_label.assert_not_called()


# ---------------------------------------------------------------------------
# The silent-success hole — the #1621 failure class
# ---------------------------------------------------------------------------


def test_unclosable_sub_issue_fails_the_archive(tmp_path, monkeypatch):
    """A refused sub-issue close is a failed archive, not a logged warning.

    This path used to print `Warning: Could not close sub-issues` and return 0,
    leaving WMBTs open under an issue reported as archived.
    """
    mgr = _init_repo(tmp_path)
    client = _client(
        monkeypatch, mgr, state="OPEN", subs=[{"number": 1690, "state": "open"}],
    )
    client.close_issue.side_effect = GitHubClientError("403 Forbidden")

    assert mgr._archive_github("1689") != 0


def test_unreadable_sub_issues_fails_the_archive(tmp_path, monkeypatch):
    """Not knowing what to close is not the same as having closed it.

    Also covers a latent crash: `subs` was assigned inside the `try`, so a
    failure in `get_sub_issues` left it unbound and the summary line below
    raised `NameError` over the warning that had just claimed success.
    """
    mgr = _init_repo(tmp_path)
    client = _client(monkeypatch, mgr, state="OPEN")
    client.get_sub_issues.side_effect = GitHubClientError("502 Bad Gateway")

    assert mgr._archive_github("1689") != 0


def test_unclosable_parent_is_reported_not_raised(tmp_path, monkeypatch, caplog):
    """The parent close was unguarded — the error escaped as a traceback.

    #1621 is on record twice about a raw traceback being read as GitHub
    flakiness. It must come back as a non-zero return with a diagnosis, and
    that diagnosis must be *logged*, not only printed: a handler that prints
    and returns leaves no record a CI run or a later audit can find. That is
    `coder.logging.coach-silent-swallow`, and it is how the first cut of this
    very fix failed validate-coder.
    """
    mgr = _init_repo(tmp_path)
    client = _client(monkeypatch, mgr, state="OPEN")
    client.close_issue.side_effect = GitHubClientError("403 Forbidden")

    with caplog.at_level(logging.ERROR):
        assert mgr._archive_github("1689") != 0

    assert any(r.levelno >= logging.ERROR for r in caplog.records), (
        "The archive failure must leave a structured log record, not just "
        "stdout prose."
    )


def test_failed_archive_fails_the_whole_transition(tmp_path, monkeypatch, capsys):
    """`atdd coach transition <N> COMPLETE` must not exit 0 over a failed archive.

    `apply_transition` printed `Warning: Archive step returned N` and then
    returned the re-enter code, so the command reported success over a
    half-applied terminal transition — exactly the shape #1621 was about.
    """
    calls = []

    class _Lifecycle:
        def __init__(self, target_dir=None):
            self.target_dir = target_dir

        def _transition_gate(self, *a, **k):
            return 0

        def _compliance_gate(self, *a, **k):
            return 0

        def _reenter_display_only(self, *a, **k):
            calls.append("reenter")
            return 0

    class _Manager:
        def __init__(self, target_dir=None):
            pass

        def update(self, **kwargs):
            return 0

        def archive(self, **kwargs):
            return 1

    monkeypatch.setattr(lifecycle_module, "IssueLifecycle", _Lifecycle)
    monkeypatch.setattr(issue_module, "IssueManager", _Manager)

    rc = apply_transition(1689, "COMPLETE", target_dir=tmp_path)

    assert rc != 0, "A failed archive must fail the transition, not warn about it."
    assert "archive step failed" in capsys.readouterr().out
    assert calls == [], (
        "The re-enter display must not run over a failed archive — it is what "
        "made the failure look like an ordinary successful transition."
    )
