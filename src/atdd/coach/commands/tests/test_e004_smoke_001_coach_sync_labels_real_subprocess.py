# URN: test:coach-verb-split:coach-verb-split:E004-SMOKE-001-real-sync-labels-in-temp-control-root
# Acceptance: acc:coach-verb-split:E004-SMOKE-001-real-sync-labels-in-temp-control-root
# WMBT: wmbt:coach-verb-split:E004
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C4 (#1308) SMOKE — `atdd coach sync-labels` re-derives labels for real.

execution_kind: real subprocess (honors #1298 live-smoke honesty). This is NOT a
mock-and-assert unit test: it spawns the actual `python -m atdd` CLI as a child
process and drives the WHOLE verb path end-to-end —
coach.run_cli -> coach_verbs.resolve_verb -> sync_labels.run ->
IssueManager.sync_labels -> _derive_expected_labels -> GitHubClient. The ONLY
thing faked is the `gh` transport at the process boundary: a fake `gh` on PATH
serves a canned issue and RECORDS the label edits the real derivation decides.
There is NO self-skip and NO env gate — the test runs (or fails) every lane.

Hermetic: a temp ATDD_CONTROL_ROOT + a throwaway issue number that is not any
real issue (the #1304 incident archived a real issue by testing on it), and the
fake `gh` guarantees no live GitHub call can escape.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

# A number that is NOT any real GitHub issue.
_FAKE_ISSUE = 999501
# repo `src/` dir so the child `-m atdd` runs THIS branch's code, not the install.
_SRC = Path(__file__).resolve().parents[4]

# Body whose Issue Metadata table drives a known expected label set. Current
# labels are only `atdd-issue`, so the derivation must add exactly these three.
_EXPECTED_ADDS = {"atdd:INIT", "archetype:coach", "wagon:govern-lifecycle"}

_BODY = (
    "## Issue Metadata\n\n"
    "| Field | Value |\n"
    "|-------|-------|\n"
    "| Date | `2026-07-08` |\n"
    "| Status | `INIT` |\n"
    "| Type | `refactor` |\n"
    "| Archetypes | `coach` |\n"
    "| Train | `0002-coach-drives-lifecycle` |\n"
    "| Wagon | `wagon:govern-lifecycle` |\n\n"
    "### Dependencies\n\n- none\n"
)

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


def _setup_env(tmp_path: Path):
    """Build a temp control root + a fake `gh` on PATH; return (env, record_file)."""
    # Control root with the repo config the IssueManager needs.
    atdd = tmp_path / ".atdd"
    atdd.mkdir()
    (atdd / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n", encoding="utf-8"
    )

    # Canned issue served by the fake gh.
    issue_json = tmp_path / "issue.json"
    issue_json.write_text(
        json.dumps(
            {
                "number": _FAKE_ISSUE,
                "title": "throwaway smoke",
                "state": "open",
                "labels": [{"name": "atdd-issue"}],
                "body": _BODY,
            }
        ),
        encoding="utf-8",
    )

    # Fake gh executable, first on PATH.
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
    return env, record


def _recorded_added_labels(record: Path) -> set[str]:
    """Parse the fake gh's edit log for every label passed to --add-label."""
    added: set[str] = set()
    if not record.exists():
        return added
    for line in record.read_text(encoding="utf-8").splitlines():
        toks = line.split()
        if "--add-label" in toks:
            csv = toks[toks.index("--add-label") + 1]
            added.update(csv.split(","))
    return added


def test_coach_sync_labels_rederives_via_real_subprocess(tmp_path):
    """`python -m atdd coach sync-labels <N>` really executes the verb and the
    derivation decides the correct add-delta (recorded through the fake gh)."""
    env, record = _setup_env(tmp_path)

    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "coach", "sync-labels", str(_FAKE_ISSUE)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, (
        f"real `atdd coach sync-labels` subprocess failed: "
        f"rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    added = _recorded_added_labels(record)
    assert _EXPECTED_ADDS.issubset(added), (
        f"the real re-derivation must add the body-declared labels; "
        f"recorded add={added}, expected superset of {_EXPECTED_ADDS}"
    )


