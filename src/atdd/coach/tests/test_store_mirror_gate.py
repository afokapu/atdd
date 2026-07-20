"""Fault injection for the store-mirror gate (#1503).

A gate that cannot fail is a stub — ``test_wheel_completeness`` looked like a
gate for months while skipping in every environment. So every blocking rule here
is proven in **both** directions: injected fault blocks, clean state allows.

Hermetic throughout: an in-memory SQLite Store and a stubbed provider. Nothing
touches the shared store or the network.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from atdd.coach import store_mirror_gate as gate


BRANCH = "feat/some-work"


@pytest.fixture()
def conn():
    """A minimal Store with just the tables the gate reads."""
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE objects (
            uid TEXT PRIMARY KEY, kind TEXT NOT NULL,
            state TEXT, data TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE external_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_uid TEXT NOT NULL, provider TEXT NOT NULL,
            ref_kind TEXT NOT NULL, ref_value TEXT NOT NULL
        );
        """
    )
    return c


def _add_work_item(conn, uid, *, body=None, state="RED", branch=BRANCH, issue="42"):
    data = {"branch": branch, "type": "implementation"}
    if body is not None:
        data["body"] = body
    conn.execute(
        "INSERT INTO objects (uid, kind, state, data) VALUES (?, 'work_item', ?, ?)",
        (uid, state, json.dumps(data)),
    )
    if issue is not None:
        conn.execute(
            "INSERT INTO external_refs (object_uid, provider, ref_kind, ref_value) "
            "VALUES (?, 'github', 'issue', ?)",
            (uid, issue),
        )
    conn.commit()


# --- Blocking rule 1: the bound work_item must carry prose -------------------


def test_bodyless_work_item_blocks_the_push(conn):
    """FAULT: the branch's work_item is a shell. The push must be blocked."""
    _add_work_item(conn, "shell", body=None)

    result = gate.evaluate(conn, BRANCH, check_provider=False)

    assert result.blocked
    assert result.exit_code == gate.EXIT_BLOCK
    assert "has no body in the Store" in result.blocking[0]


def test_work_item_with_body_allows_the_push(conn):
    """CLEAN: same shape, prose present. The push must be allowed."""
    _add_work_item(conn, "real", body="# Real issue\n\nWith actual content.")

    result = gate.evaluate(conn, BRANCH, check_provider=False)

    assert not result.blocked
    assert result.exit_code == gate.EXIT_ALLOW


def test_whitespace_only_body_counts_as_bodyless(conn):
    """A body of spaces is a shell wearing a hat; it must not satisfy the gate."""
    _add_work_item(conn, "blank", body="   \n\t  ")

    assert gate.evaluate(conn, BRANCH, check_provider=False).blocked


# --- Blocking rule 2: Store phase and GitHub label must agree ---------------


def test_label_divergence_blocks_the_push(conn, monkeypatch):
    """FAULT: Store says RED, GitHub says INIT."""
    _add_work_item(conn, "diverged", body="content", state="RED")
    monkeypatch.setattr(gate, "_github_labels", lambda n: ["atdd-issue", "atdd:INIT"])

    result = gate.evaluate(conn, BRANCH)

    assert result.blocked
    assert "Store says RED" in result.blocking[0]
    assert "GitHub label says INIT" in result.blocking[0]


def test_matching_label_allows_the_push(conn, monkeypatch):
    """CLEAN: both say RED."""
    _add_work_item(conn, "agreed", body="content", state="RED")
    monkeypatch.setattr(gate, "_github_labels", lambda n: ["atdd-issue", "atdd:RED"])

    assert not gate.evaluate(conn, BRANCH).blocked


def test_missing_atdd_label_blocks_the_push(conn, monkeypatch):
    """FAULT: the #1235/#1236 shape — a real issue carrying no atdd: label at all.

    A GitHub-derived phase read returns nothing here while the Store says RED,
    so 'no label' must block rather than read as agreement.
    """
    _add_work_item(conn, "unlabelled", body="content", state="RED")
    monkeypatch.setattr(gate, "_github_labels", lambda n: [])

    result = gate.evaluate(conn, BRANCH)

    assert result.blocked
    assert "no atdd: label at all" in result.blocking[0]


def test_unreachable_provider_is_advisory_not_a_silent_pass(conn, monkeypatch):
    """Offline must be reported, never mistaken for agreement."""
    _add_work_item(conn, "offline", body="content", state="RED")
    monkeypatch.setattr(gate, "_github_labels", lambda n: None)

    result = gate.evaluate(conn, BRANCH)

    assert not result.blocked
    assert any("divergence check skipped" in line for line in result.advisory)


# --- Scoping: blocking stays on the touched work_item ------------------------


def test_other_branches_drift_does_not_block_this_push(conn):
    """The operator chose scoped blocking: history must not hold this push hostage."""
    _add_work_item(conn, "mine", body="content", branch=BRANCH, issue="1")
    for i in range(5):  # unrelated shells on other branches
        _add_work_item(conn, f"other-{i}", body=None,
                       branch=f"feat/other-{i}", issue=str(100 + i))

    result = gate.evaluate(conn, BRANCH, check_provider=False)

    assert not result.blocked, "unrelated shells must not block this branch"
    assert any("repo-wide drift: 5/6" in line for line in result.advisory)


def test_unregistered_branch_is_not_this_gates_failure(conn):
    """No work_item for the branch is the registration gate's business."""
    result = gate.evaluate(conn, "feat/unknown", check_provider=False)

    assert not result.blocked
    assert any("not applicable" in line for line in result.advisory)


# --- The advisory count must read the authoritative binding -----------------


def test_drift_count_ignores_rows_with_no_external_ref(conn):
    """An unbound row is #1516's defect; counting it would inflate this number.

    This is the mistake that produced a wrong shell census: reading binding off
    the ``data`` blob instead of ``external_refs``.
    """
    _add_work_item(conn, "bound", body=None, branch="feat/a", issue="7")
    _add_work_item(conn, "unbound", body=None, branch="feat/b", issue=None)

    bodyless, total = gate.repo_wide_drift(conn)

    assert (bodyless, total) == (1, 1)


def test_clean_store_reports_no_drift(conn):
    """CLEAN: nothing bodyless, so no advisory line at all."""
    _add_work_item(conn, "a", body="content", branch="feat/a", issue="7")

    result = gate.evaluate(conn, "feat/a", check_provider=False)

    assert not result.blocked
    assert not any("repo-wide drift" in line for line in result.advisory)
