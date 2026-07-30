# URN: test:govern-lifecycle:R009-SMOKE-001-a-refused-transition-exits-red-with-a-diagnosis
# Acceptance: acc:govern-lifecycle:R009-SMOKE-001-a-refused-transition-exits-red-with-a-diagnosis
# WMBT: wmbt:govern-lifecycle:R009
# Phase: SMOKE
# Layer: backend.application
# Assertion: behavioral
"""R009-SMOKE-001 — a real refused transition exits red with a diagnosis, not a traceback.

REAL, not simulated. The CLI runs as an actual subprocess against an actual
Control Root carrying an actual migrated State Store, with an actual approval
token the real signing path produced. Nothing is imported in-process and no
part of the refusal handling is re-implemented here.

The ONE thing stubbed is the network boundary: a real ``gh`` executable on PATH
that answers the read and then **refuses the label write** with the exact stderr
GitHub produced on run 30199788383 of #1601. That is the same seam R006-SMOKE-001
and R005 use.

Why this has to be a subprocess. The whole defect (#1621) was about *presentation*
— a refusal that escaped as an unhandled ``GitHubClientError`` and so read like a
network blip. Presentation is exactly what an in-process unit test cannot check:
the assertions that matter here are "the diagnosis reached stdout", "the process
exit code is non-zero", and "there is no traceback", and none of those exist
until a real process really exits.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Toolkit dogfood: REPO_ROOT below resolves to the toolkit checkout (#1475).
pytestmark = [pytest.mark.coach, pytest.mark.smoke, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]

ISSUE = 4009
FROM_PHASE = "PLANNED"
TO_PHASE = "RED"
BRANCH = "feat/refused-label-write"

# The exact stderr from run 30199788383 on #1601.
_LIVE_REFUSAL = (
    "GraphQL: Resource not accessible by personal access token "
    "(removeLabelsFromLabelable)"
)

#: A template-compliant body. The transition runs a template-compliance gate
#: BEFORE the label write, so a stub issue with an empty body never reaches the
#: operation under test — and every assertion here would pass for the wrong
#: reason, the run having exited red over a malformed body rather than a refused
#: write. This body exists solely to get past that gate.
_COMPLIANT_BODY = """# A record whose label write will be refused

## Issue Metadata

| Field | Value |
|-------|-------|
| Status | `PLANNED` |
| Type | `bug` |
| Branch | `feat/refused-label-write` |
| Archetypes | coach |
| Train | `train:self-compliance:validate-lifecycle` |
| Feature | `feature:govern-lifecycle:fix-auto-phase-label-write-credential` |

## Scope

### In Scope

- Reaching the label write.

### Out of Scope

- Everything else.

### Dependencies

- None.

### Done-when

- The refusal is diagnosed.

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| fixture | a stub | a stub | none |

### User Impact

None — this is a test fixture.

### Root Cause

Not applicable.

## Architecture

### Graph Context

Not applicable.

### Mirror Across Agents

| Agent | Current state | Target state | Action |
|-------|---------------|--------------|--------|
| coach | fixture | fixture | none |

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| gh stub | R006-SMOKE-001 | real executable on PATH |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| fixture | a stand-in | this body |

## Phases

### Phase 1: Reach the write

**Deliverables:**
- The label write is attempted.

**Files:**

| File | Change |
|------|--------|
| none | none |

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | RED | see this file | FAIL | R009-SMOKE-001 | TODO |

### Success Criteria

- [ ] The refusal is diagnosed.

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Real body? | yes | the compliance gate runs first |

## Activity Log

### Entry 1 (2026-07-29)

**Completed:**
- Authored as a test fixture.

**Next:**
- Be refused.

## Artifacts

### Created

- None.

### Modified

- None.

### Deleted

- None.

## Release Gate

INTERIM (see #1172): bump the version manually.

- [ ] Rebase on main.

## Notes

Test fixture for R009-SMOKE-001.
"""


def _write_gh_stub(bin_dir: Path) -> None:
    """A real `gh` that answers reads and refuses every label write."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    issue = {
        "number": ISSUE,
        "title": "a record whose label write will be refused",
        "state": "OPEN",
        "body": _COMPLIANT_BODY,
        "labels": [{"name": "atdd-issue"}, {"name": f"atdd:{FROM_PHASE}"}],
    }
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"ISSUE = {json.dumps(issue)}\n"
        f"REFUSAL = {json.dumps(_LIVE_REFUSAL)}\n"
        "argv = sys.argv[1:]\n"
        # The label write — the operation under test. Refuse it exactly as
        # GitHub did, on stderr, with a non-zero exit.
        "if argv[:2] == ['issue', 'edit'] and any(\n"
        "        a in ('--add-label', '--remove-label') for a in argv):\n"
        "    sys.stderr.write(REFUSAL + '\\n')\n"
        "    sys.exit(1)\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps(ISSUE))\n"
        "elif argv[:2] == ['issue', 'list']:\n"
        "    print(json.dumps([ISSUE]))\n"
        "elif argv[:2] == ['pr', 'list']:\n"
        "    print(json.dumps([]))\n"
        "elif argv[:1] == ['auth']:\n"
        "    print('logged in')\n"
        "else:\n"
        "    print('{}')\n"
    )
    stub.chmod(0o755)


def _seed_store(control_root: Path) -> None:
    """A REAL work item in a REAL migrated store at the FROM phase."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    db_path = init_state_store(start=control_root)
    conn = connect(db_path)
    try:
        create_work_item(
            conn, "refused-label-write", state=FROM_PHASE, github_number=ISSUE,
            data={"issue_number": ISSUE},
        )
        conn.commit()
    finally:
        conn.close()


def _write_approval(control_root: Path) -> None:
    """A REAL operator approval, produced by the real signing path.

    The operator-approval gate (E050) sits in front of the transition, so
    without this the run would stop before the label write and prove nothing
    about refusals. Signed through ``build_token`` rather than hand-written, so
    a change to the signing scheme fails this test loudly instead of silently
    routing around the gate.
    """
    from atdd.coach.gate.approval import approval_relpath, build_token

    token = build_token(
        ISSUE, FROM_PHASE, TO_PHASE,
        approved_by="smoke-operator",
        approved_at="2026-07-29T00:00:00+00:00",
    )
    path = control_root / approval_relpath(ISSUE, FROM_PHASE, TO_PHASE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token))


@pytest.fixture
def control_root(tmp_path: Path) -> Path:
    """A real Control Root: config, a real migrated store, a real approval."""
    root = tmp_path / "repo"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "github:\n  owner: afokapu\n  repo: atdd\n"
    )
    _seed_store(root)
    _write_approval(root)
    return root


@pytest.fixture
def refused_run(control_root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the REAL CLI transition against a `gh` that refuses the label write."""
    bin_dir = tmp_path / "bin"
    _write_gh_stub(bin_dir)
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ATDD_CONTROL_ROOT"] = str(control_root)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["GH_TOKEN"] = "ghp_a_token_without_issues_write"
    return subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "transition",
         str(ISSUE), TO_PHASE],
        cwd=control_root, env=env, capture_output=True, text=True, timeout=180,
    )


def test_the_transition_verb_is_actually_reachable(refused_run) -> None:
    """Assert the surface dispatched before asserting anything about its output.

    A verb that never ran would make every assertion below vacuous — the output
    would lack the strings for entirely the wrong reason.
    """
    combined = refused_run.stdout + refused_run.stderr
    assert "invalid choice" not in combined, (
        f"`atdd coach transition` did not dispatch:\n{combined}"
    )


def test_a_refused_label_write_exits_non_zero(refused_run) -> None:
    """Exit red, so CI cannot read a half-applied transition as done.

    This is the assertion the auto-phase workflow depends on: ``auto_phase.run``
    returns this subprocess's return code, so a zero here is a green CI job over
    a label that never moved.
    """
    assert refused_run.returncode != 0, (
        "a refused label write reported success\n"
        f"stdout:\n{refused_run.stdout}\nstderr:\n{refused_run.stderr}"
    )


def test_the_output_diagnoses_the_refusal(refused_run) -> None:
    """It must name permission as the cause and say retrying will not help."""
    combined = refused_run.stdout + refused_run.stderr
    assert "permission" in combined.lower(), (
        f"nothing in the output named permission as the cause:\n{combined}"
    )
    assert "retry" in combined.lower(), (
        f"the output never told the operator whether retrying would help:\n{combined}"
    )


def test_the_output_records_the_store_label_divergence(refused_run) -> None:
    """The store moved first (#1452); a refusal leaves it ahead of the label."""
    combined = refused_run.stdout + refused_run.stderr
    assert "objects.state" in combined or "store" in combined.lower(), (
        "the output did not say that the store had already advanced, so the "
        f"operator cannot know the two now disagree:\n{combined}"
    )


def test_the_refusal_is_not_a_traceback(refused_run) -> None:
    """The defect was presentation. A traceback is the presentation that failed.

    Twice the unhandled ``GitHubClientError`` was read as GitHub flakiness. A
    stack trace is what made that reading reasonable, so its absence is part of
    the fix, not a cosmetic preference.
    """
    combined = refused_run.stdout + refused_run.stderr
    assert "Traceback (most recent call last)" not in combined, (
        f"the refusal escaped as a traceback:\n{combined}"
    )
    assert "GitHubPermissionError:" not in combined, (
        "the exception type leaked into the operator-facing output instead of "
        f"a diagnosis:\n{combined}"
    )
