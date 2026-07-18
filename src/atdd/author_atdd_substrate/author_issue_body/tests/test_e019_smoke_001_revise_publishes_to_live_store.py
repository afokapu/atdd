# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-SMOKE-001-revise-publishes-to-live-store
# Acceptance: acc:govern-lifecycle:E019-SMOKE-001-revise-publishes-to-live-store
# WMBT: wmbt:govern-lifecycle:E019
# Phase: SMOKE
# Layer: integration
"""E019-SMOKE-001 — `atdd author issue --revise` revises against a live State Store.

Real end-to-end via the installed CLI (``python -m atdd``) against a real ATDD
Control Root + State Store, with a stubbed ``gh`` on PATH so the projection runs
as a real subprocess without touching production GitHub. The peer of
E019-UNIT-003, which proves the same store-first ordering in-process.

Both halves of the invariant are exercised against real infrastructure:

* the happy path — the store write lands and the body is projected to ``gh``;
* the projection-failure path — ``gh`` exits non-zero, and the **store revision
  still stands** while the body update is deferred to the outbox. The State Store
  is authoritative; GitHub is a projection. A revision must never be lost because
  the provider was unreachable.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ._helpers import run_cli
from ._publish_helpers import open_store

ISSUE_NUMBER = 555019
SLUG = "e019-revise-live-store-smoke"


def _revised_body(issue_type: str = "refactor") -> str:
    from atdd.planner.commands.author import create_issue_body

    return create_issue_body({
        "title": "Revised through the live store",
        "status": "INIT",
        "type": issue_type,
        "branch": "feat/e019-revise-live-store-smoke",
        "train": "0003-author-substrate",
        "feature": "feature:author-atdd-substrate:author-issue-body",
        "scope": {
            "in_scope": [
                "revise an issue-backed work item store-first via the real CLI",
                "project the revised body to the provider as a best-effort mirror",
            ],
            "out_of_scope": ["creating the work item (E008 covers the create path)"],
            "dependencies": ["State Store external_refs links the github issue"],
            "done_when": [
                "the store revision is authoritative and survives a projection failure",
            ],
        },
    })


def _seed_work_item(control: Path) -> None:
    """Create the issue-backed work item the revision targets, in the real store."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control))
    try:
        create_work_item(
            conn,
            SLUG,
            state="INIT",
            data={"title": "Body before revision", "type": "implementation",
                  "body": "body before revision"},
            github_number=ISSUE_NUMBER,
        )
    finally:
        conn.close()


def _stub_gh(tmp_path: Path, *, exit_code: int) -> str:
    """A ``gh`` on PATH that drains stdin and exits with ``exit_code``.

    ``exit_code=0`` stands in for a reachable provider; non-zero stands in for an
    unreachable one, which must deflect the body update into the outbox rather
    than roll back the authoritative store write.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null 2>&1 || true\n"
        f"exit {exit_code}\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"


def _run_revise(control: Path, body_path: Path, *, gh_exit: int):
    return run_cli(
        "author", "issue",
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
        env={
            "ATDD_CONTROL_ROOT": str(control),
            "PATH": _stub_gh(control.parent, exit_code=gh_exit),
        },
    )


@pytest.mark.smoke
def test_e019_smoke_001_revise_writes_live_store_then_projects(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(control))
    _seed_work_item(control)
    revised = _revised_body()
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")

    proc = _run_revise(control, body_path, gh_exit=0)
    assert proc.returncode == 0, (
        f"`atdd author issue --revise` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    store, conn = open_store(control)
    try:
        obj = store.objects.get(SLUG)
        events = store.events.list(object_uid=SLUG)
        pending = store.sync.pending_outbox()
    finally:
        conn.close()

    assert obj is not None, "the revised work item vanished from the live store"
    assert obj.data["body"] == revised, "the live store did not take the revised body"
    assert obj.data["type"] == "refactor", "the live store did not take the revised type"
    assert obj.state == "INIT", "a revision must not move the lifecycle state"
    assert "issue_revised" in [e.event_type for e in events]
    assert pending == [], "a reachable provider must not leave a deferred projection"


@pytest.mark.smoke
def test_e019_smoke_001_projection_failure_defers_to_outbox_and_store_stands(tmp_path, monkeypatch):
    """The store is authoritative: an unreachable provider defers, it does not roll back."""
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(control))
    _seed_work_item(control)
    revised = _revised_body()
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")

    proc = _run_revise(control, body_path, gh_exit=1)
    assert proc.returncode == 0, (
        "a projection failure must not fail the revision — the store write is "
        f"authoritative (exit {proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    store, conn = open_store(control)
    try:
        obj = store.objects.get(SLUG)
        pending = store.sync.pending_outbox()
    finally:
        conn.close()

    assert obj is not None
    assert obj.data["body"] == revised, "the store revision must stand despite the failed projection"
    assert obj.data["type"] == "refactor"

    assert len(pending) == 1, f"the failed body projection must be deferred to the outbox, got {pending}"
    assert pending[0].payload["issue_number"] == ISSUE_NUMBER
    assert pending[0].payload["body"] == revised
