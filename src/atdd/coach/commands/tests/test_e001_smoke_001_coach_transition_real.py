# URN: test:coach-verb-split:coach-verb-split:E001-SMOKE-001-real-transition-in-temp-control-root
# Acceptance: acc:coach-verb-split:E001-SMOKE-001-real-transition-in-temp-control-root
# WMBT: wmbt:coach-verb-split:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C1 (#1304) SMOKE — `atdd coach transition` drives a REAL State Store phase
write in a temp control root, and the deprecated `atdd issue --status` shim still
routes to the same engine.

execution_kind: real subprocess (honors #1298 live-smoke honesty). This is NOT a
mock-and-assert unit test: it spawns the actual `python -m atdd` CLI as a child
process and drives the WHOLE transition path end-to-end —
coach.run_cli -> coach_verbs.resolve_verb -> issue_transition.apply_transition ->
IssueManager.update -> _store_set_status (the store-first write). The ONLY thing
faked is the `gh` transport at the process boundary: a fake `gh` on PATH serves a
canned issue (atdd:RED + a template-compliant body) and RECORDS the label edits,
so no live GitHub call can escape.

Post-#1270: the manifest mirror is decommissioned (Slices D-F stopped its reads
and writes; Slice G deletes the file), so the SoT assertion is on the STATE STORE
only — the acceptance's original "manifest mirror matches" clause is retired.

Hermetic: a temp ATDD_CONTROL_ROOT with its own State Store seeded to a throwaway
work item (slug is not any real issue; number 999011 is not any real issue — the
#1304 incident archived a real issue by testing on it). RED->GREEN is chosen
because the operator-approval gate enforces only PLANNED->RED by default config
(src/atdd/coach/gate/registrations.py), so no signed token is needed and no gate
is bypassed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# A number/slug that is NOT any real GitHub issue — see the hermeticity note above.
_FAKE_ISSUE = 999011
_SLUG = "throwaway-e001-smoke-transition"
# repo `src/` dir so the child `-m atdd` runs THIS branch's code, not the install.
_SRC = Path(__file__).resolve().parents[4]


def _compliant_body() -> str:
    """Build a template-compliant issue body from the live required-section spec,
    so the #0011 compliance gate (PLANNED+ transitions) passes without leftover
    placeholders. Generated from the source of truth so it never drifts."""
    from atdd.coach.commands.issue_template import (
        REQUIRED_SUBSECTIONS,
        load_required_sections,
    )

    real = "Real, non-placeholder content describing the concrete work.\n\n"
    body = ""
    for section in load_required_sections():
        body += f"{section}\n\n{real}"
        if section == "## Context":
            body += "### Graph Context\n\nReal graph context: nodes and edges.\n\n"
        if section == "## Architecture":
            body += "### Mirror Across Agents\n\nplanner/tester/coder/coach roles.\n\n"
    for sub in REQUIRED_SUBSECTIONS:
        if sub not in body:
            body += f"{sub}\n\n{real}"
    return body


_FAKE_GH = """#!/usr/bin/env python3
import sys, os, json
args = sys.argv[1:]
rec = os.environ["FAKE_GH_RECORD"]
issue_path = os.environ["FAKE_GH_ISSUE_JSON"]
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[:2] == ["issue", "view"]:
    sys.stdout.write(open(issue_path).read())
    sys.exit(0)
if args[:2] == ["issue", "edit"]:
    with open(rec, "a") as f:
        f.write(" ".join(args) + "\\n")
    sys.exit(0)
# Any other gh call is a no-op — the real network is never reached.
sys.exit(0)
"""


def _seed_store_red(control_root: Path) -> None:
    """Seed the temp control root's State Store with a throwaway work item at RED,
    linked to the fake issue number, carrying the train E008 requires."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=control_root))
    try:
        create_work_item(
            conn,
            _SLUG,
            state="RED",
            data={
                "type": "refactor",
                "train": "0002-coach-drives-lifecycle",
                "body": _compliant_body(),
            },
            github_number=_FAKE_ISSUE,
        )
        conn.commit()
    finally:
        conn.close()


def _store_state(control_root: Path) -> str | None:
    """Read the throwaway work item's lifecycle state straight from the store.

    Resolved through the slug, not fetched by it: identity is a minted uid (#1622),
    so the slug is a field to look up rather than the key to read at.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.work_item_writer import resolve_work_item

    conn = connect(init_state_store(start=control_root))
    try:
        obj = resolve_work_item(StateStore(conn), _SLUG)
        return obj.state if obj is not None else None
    finally:
        conn.close()


def _setup(tmp_path: Path):
    """Temp control root + seeded RED store + fake `gh` on PATH. Returns env."""
    atdd = tmp_path / ".atdd"
    atdd.mkdir()
    (atdd / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n  project_number: 1\n", encoding="utf-8"
    )

    _seed_store_red(tmp_path)

    issue_json = tmp_path / "issue.json"
    issue_json.write_text(
        json.dumps(
            {
                "number": _FAKE_ISSUE,
                "title": "throwaway e001 smoke",
                "state": "open",
                "labels": [{"name": "atdd-issue"}, {"name": "atdd:RED"}],
                "body": _compliant_body(),
            }
        ),
        encoding="utf-8",
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)

    record = tmp_path / "gh_edits.log"
    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}" + env.get("PATH", "")
    env["PYTHONPATH"] = f"{_SRC}{os.pathsep}" + env.get("PYTHONPATH", "")
    env["ATDD_CONTROL_ROOT"] = str(tmp_path)
    env["FAKE_GH_RECORD"] = str(record)
    env["FAKE_GH_ISSUE_JSON"] = str(issue_json)
    return env


def test_coach_transition_writes_real_store_state(tmp_path):
    """`python -m atdd coach transition <N> GREEN` really executes the transition
    against the temp control root and the throwaway work item's STORE state
    becomes GREEN (the sole SoT; the manifest mirror is decommissioned)."""
    env = _setup(tmp_path)
    assert _store_state(tmp_path) == "RED", "precondition: seeded at RED"

    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "coach", "transition", str(_FAKE_ISSUE), "GREEN"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, (
        f"real `atdd coach transition` subprocess failed: rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert _store_state(tmp_path) == "GREEN", (
        f"the real transition must write the store; state={_store_state(tmp_path)}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )


