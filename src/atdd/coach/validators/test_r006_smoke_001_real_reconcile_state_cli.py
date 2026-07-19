# URN: test:govern-lifecycle:R006-SMOKE-001-real-reconcile-state-cli
# Acceptance: acc:govern-lifecycle:R006-SMOKE-001-real-reconcile-state-cli
# WMBT: wmbt:govern-lifecycle:R006
# Phase: SMOKE
# Layer: backend.application
# Assertion: behavioral
"""R006-SMOKE-001 — the real ``atdd coach reconcile-state`` CLI classifies a real
State Store record, and really refuses the legacy-undriven one.

REAL, not simulated. Each case runs the installed CLI as an actual subprocess
against an actual Control Root with an actual migrated State Store carrying an
actual work item. Nothing is imported in-process and no classification is
re-implemented here — if the verb were not wired into ``atdd coach``, or the
store read were broken, or the argv contract wrong, these tests go red where a
unit test driving ``classify()`` directly would stay green.

The ONE thing stubbed is the network boundary: a real ``gh`` executable placed
on PATH that answers ``gh issue list`` and ``gh pr list`` with canned JSON. That
is the same seam #1452's R005 smoke and #1477's E019 smoke use — it keeps the
run hermetic and off production GitHub while leaving the CLI, the dispatch, the
store and the classifier genuinely real.

Issue #1338.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Toolkit dogfood: REPO_ROOT below resolves to the toolkit checkout, so every
# test here asserts on a toolkit-only path (#1475).
pytestmark = [pytest.mark.coach, pytest.mark.smoke, pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[4]

# The two records under test. The first is the #1434 signature — the smoking-gun
# record the issue names as the class-2 worked example. The second is the live
# signature of the 82 legacy-undriven records that must be refused.
DRIFTED_ISSUE = 4001
LEGACY_ISSUE = 4002


def _write_gh_stub(bin_dir: Path, issues: list, merged_prs: list) -> None:
    """A real executable named ``gh`` that answers the two calls the verb makes."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"ISSUES = {json.dumps(issues)}\n"
        f"MERGED = {json.dumps(merged_prs)}\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['issue', 'list']:\n"
        "    print(json.dumps(ISSUES))\n"
        "elif argv[:2] == ['pr', 'list']:\n"
        "    print(json.dumps(MERGED))\n"
        "else:\n"
        "    sys.stderr.write('unexpected gh call: %r\\n' % (argv,))\n"
        "    sys.exit(3)\n"
    )
    stub.chmod(0o755)


def _seed_store(control_root: Path, slug: str, issue_number: int, state: str) -> None:
    """Create a REAL work item in a REAL migrated store at ``state``."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    db_path = init_state_store(start=control_root)
    conn = connect(db_path)
    try:
        create_work_item(
            conn, slug, state=state, github_number=issue_number,
            data={"issue_number": issue_number},
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def control_root(tmp_path: Path) -> Path:
    """A real Control Root: .atdd/config.yaml + a real migrated State Store."""
    root = tmp_path / "repo"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "github:\n  owner: afokapu\n  repo: atdd\n"
    )
    _seed_store(root, "drifted-record", DRIFTED_ISSUE, "SMOKE")
    _seed_store(root, "legacy-record", LEGACY_ISSUE, "INIT")
    return root


def _run_cli(control_root: Path, tmp_path: Path, args: list) -> subprocess.CompletedProcess:
    """Run the REAL CLI as a subprocess with a real `gh` stub on PATH."""
    bin_dir = tmp_path / "bin"
    _write_gh_stub(
        bin_dir,
        issues=[
            {"number": DRIFTED_ISSUE, "title": "drifted", "state": "CLOSED",
             "labels": [{"name": "atdd-issue"}, {"name": "atdd:COMPLETE"}]},
            {"number": LEGACY_ISSUE, "title": "legacy", "state": "CLOSED",
             "labels": [{"name": "atdd-issue"}, {"name": "atdd:COMPLETE"}]},
        ],
        merged_prs=[
            {"number": 9, "closingIssuesReferences": [{"number": DRIFTED_ISSUE}]},
            {"number": 10, "closingIssuesReferences": [{"number": LEGACY_ISSUE}]},
        ],
    )
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ATDD_CONTROL_ROOT"] = str(control_root)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "atdd.cli", "coach", "reconcile-state", *args],
        cwd=control_root, env=env, capture_output=True, text=True, timeout=180,
    )


def test_the_verb_is_actually_reachable_through_the_real_cli(control_root, tmp_path):
    """Assert the surface exists before asserting anything about its output.

    A verb that never dispatched would make every substring assertion below
    vacuous — the output would simply lack the strings for the wrong reason.
    """
    result = _run_cli(control_root, tmp_path, [str(DRIFTED_ISSUE)])
    combined = result.stdout + result.stderr
    assert "invalid choice" not in combined and "Unknown" not in combined, (
        f"`atdd coach reconcile-state` did not dispatch:\n{combined}"
    )
    assert "reconcile-state" in result.stdout, (
        f"The real CLI produced no reconcile-state report.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_real_cli_classifies_the_drifted_record_as_a_replay(control_root, tmp_path):
    """A real store at SMOKE + a real merged-PR reference ⇒ class 2, REFACTOR then COMPLETE."""
    result = _run_cli(control_root, tmp_path, [str(DRIFTED_ISSUE)])
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "class 2" in result.stdout, (
        f"Expected the #1434 signature to classify as class 2.\n{result.stdout}"
    )
    assert "REFACTOR -> COMPLETE" in result.stdout, (
        f"Expected the missing legal steps to be named.\n{result.stdout}"
    )


def test_real_cli_reports_without_writing(control_root, tmp_path):
    """Reporting is the default; the store must be untouched afterwards."""
    from atdd.state.work_item_reader import WorkItemReader

    _run_cli(control_root, tmp_path, [str(DRIFTED_ISSUE)])
    with WorkItemReader(control_root=control_root) as reader:
        after = reader.status(DRIFTED_ISSUE)
    assert after == "SMOKE", (
        f"The default report advanced objects.state to {after!r}. Reporting must "
        "write nothing — the operator approves the plan before it is applied."
    )
    result = _run_cli(control_root, tmp_path, [str(DRIFTED_ISSUE)])
    assert "DRY RUN" in result.stdout


def test_real_cli_refuses_the_legacy_undriven_record(control_root, tmp_path):
    """The refusal survives the whole real stack, not just the pure classifier."""
    result = _run_cli(control_root, tmp_path, [str(LEGACY_ISSUE), "--apply"])
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"A real class-4 record exited 0 through the real CLI.\n{combined}"
    )
    assert "REFUSED" in combined, (
        f"The real CLI did not report a refusal.\n{combined}"
    )
    from atdd.state.work_item_reader import WorkItemReader

    with WorkItemReader(control_root=control_root) as reader:
        after = reader.status(LEGACY_ISSUE)
    assert after == "INIT", (
        f"The refused record's store moved to {after!r}. A refusal that still "
        "writes is not a refusal — and this write would be the fabricated history."
    )


def test_real_cli_refuses_bulk_apply(control_root, tmp_path):
    """`--all --apply` is refused: bulk repair is an operator-gated migration."""
    result = _run_cli(control_root, tmp_path, ["--all", "--apply"])
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"`--all --apply` was allowed to run.\n{combined}"
    )
    assert "report-only" in combined, (
        f"The refusal must explain that --all is report-only.\n{combined}"
    )


def test_real_cli_all_reports_every_class_present(control_root, tmp_path):
    """The sweep classifies both seeded records and refuses the legacy one."""
    result = _run_cli(control_root, tmp_path, ["--all"])
    assert result.returncode == 0, result.stderr
    assert "class 2" in result.stdout and "class 4" in result.stdout, (
        f"Expected both the replay and the refusal class in the sweep.\n{result.stdout}"
    )
    assert "REFUSED" in result.stdout
