# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:E019-SMOKE-002-revise-retitles-live-store-and-projection
# Acceptance: acc:govern-lifecycle:E019-SMOKE-002-revise-retitles-live-store-and-projection
# WMBT: wmbt:govern-lifecycle:E019
# Phase: RED
# Layer: integration
"""E019-SMOKE-002 — a live revise that changes the H1 changes the title too.

The end-to-end shape of the #1639 divergence, against a real ATDD Control Root
and a real ``gh`` subprocess: the installed CLI is run, the store is read back
directly, and the argv the provider was actually invoked with is inspected.

Reading the store directly is the point. ``atdd author issue --check`` is a
substring search rather than a heading check (#1647), so it passes a body whose
H1 contradicts the stored title — it cannot witness this defect and no assertion
here is allowed to rest on it.

Hermetic: ``ATDD_CONTROL_ROOT`` is a tmp_path and ``gh`` is a recording stub on
PATH, so nothing touches the shared Control Root store or production GitHub.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ._helpers import run_cli
from ._publish_helpers import open_store

ISSUE_NUMBER = 555020
SLUG = "e019-retitle-live-store-smoke"

SEEDED_TITLE = "Title and H1 agreeing before the revision"
REVISED_TITLE = "Decommission all 17 planner legacy convention monoliths"


def _body(title: str, issue_type: str = "implementation") -> str:
    from atdd.planner.commands.author import create_issue_body

    return create_issue_body({
        "title": title,
        "status": "INIT",
        "type": issue_type,
        "branch": "fix/author-issue-revise-drops-title",
        "train": "0003-author-substrate",
        "feature": "feature:author-atdd-substrate:author-issue-body",
        "scope": {
            "in_scope": ["re-title the store and the projection in one revise"],
            "out_of_scope": ["the outbox/provider seam (#1655)"],
            "dependencies": ["State Store external_refs links the github issue"],
            "done_when": ["the stored title agrees with the body H1 after a revise"],
        },
    })


def _seed_work_item(control: Path) -> None:
    """Seed a work item whose stored title and body H1 already agree."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control))
    try:
        create_work_item(
            conn,
            SLUG,
            state="INIT",
            data={"title": SEEDED_TITLE, "type": "implementation",
                  "body": _body(SEEDED_TITLE)},
            github_number=ISSUE_NUMBER,
        )
    finally:
        conn.close()


def _recording_gh(tmp_path: Path) -> tuple[str, Path]:
    """A ``gh`` on PATH that records its argv and succeeds.

    Recording argv rather than trusting the exit code is what makes this a test
    of the *projection* and not merely of the store: a body-only edit and a
    body+title edit both exit 0.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    argv_log = tmp_path / "gh-argv.log"
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null 2>&1 || true\n"
        f'printf "%s\\n" "$*" >> {argv_log}\n'
        "exit 0\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}", argv_log


@pytest.mark.smoke
def test_e019_smoke_002_revise_retitles_the_live_store_and_the_projection(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(control))
    _seed_work_item(control)

    revised = _body(REVISED_TITLE, "refactor")
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    path, argv_log = _recording_gh(tmp_path)

    proc = run_cli(
        "author", "issue",
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        "--type", "refactor",
        env={"ATDD_CONTROL_ROOT": str(control), "PATH": path},
    )
    assert proc.returncode == 0, (
        f"`atdd author issue --revise` exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    store, conn = open_store(control)
    try:
        obj = store.objects.get(SLUG)
    finally:
        conn.close()

    assert obj is not None, "the revised work item vanished from the live store"
    assert obj.data["body"] == revised, "the live store did not take the revised body"
    assert obj.data["title"] == REVISED_TITLE, (
        "the live store took the new body but kept the superseded title — the "
        "#1639 divergence, reproduced end to end"
    )
    assert obj.state == "INIT", "a revision must not move the lifecycle state"

    recorded = argv_log.read_text(encoding="utf-8") if argv_log.exists() else ""
    assert REVISED_TITLE in recorded, (
        "the provider was never asked to re-title; the projection still names "
        f"the superseded scope. gh argv was:\n{recorded}"
    )


@pytest.mark.smoke
def test_e019_smoke_002_the_revised_work_item_passes_the_consistency_check(tmp_path, monkeypatch):
    """The store the revise leaves behind must not be one the check would flag."""
    from atdd.planner.commands.author_issue import title_violations

    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(control))
    _seed_work_item(control)

    revised = _body(REVISED_TITLE, "refactor")
    body_path = tmp_path / "revised.md"
    body_path.write_text(revised, encoding="utf-8")
    path, _argv_log = _recording_gh(tmp_path)

    proc = run_cli(
        "author", "issue",
        "--revise", str(ISSUE_NUMBER),
        "--body-file", str(body_path),
        env={"ATDD_CONTROL_ROOT": str(control), "PATH": path},
    )
    assert proc.returncode == 0, proc.stderr

    store, conn = open_store(control)
    try:
        obj = store.objects.get(SLUG)
    finally:
        conn.close()

    assert obj is not None
    assert title_violations(obj.data["title"], obj.data["body"]) == [], (
        "the revise path wrote a work item its own consistency check rejects"
    )
