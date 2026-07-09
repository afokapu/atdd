# URN: test:coach-verb-split:coach-verb-split:E006-SMOKE-001-real-removal-and-repointed-blockers
# Acceptance: acc:coach-verb-split:E006-SMOKE-001-real-subprocess-removal-and-repointed-blockers
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C5b (#1309) SMOKE — the removal is proven by REAL subprocess exit codes, and no
shipped text still sends an operator to the deleted command.

#1298 (live-smoke execution honesty): these run the actual `atdd` CLI as a child
process against a temp ATDD_CONTROL_ROOT. Nothing is mocked — a mocked "removal"
proves nothing about what an operator's shell does. No live `gh` mutation occurs:
the only commands driven are read-only or fail before any network call.

The four orphan classes this pins:
  1. the CLI surface itself                (`atdd issue` -> fail-loud, rc != 0)
  2. the shipped `gh issue create` blockers (gh.shim / pre-commit / PreToolUse)
  3. the coach convention `cli_commands:`   (issue.convention.yaml)
  4. the managed CONDUCTOR.md `issues:` block
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

_TIMEOUT = 60


def _run_atdd(args, cwd, control_root):
    env = dict(os.environ)
    env["ATDD_CONTROL_ROOT"] = str(control_root)
    env["CI"] = "true"
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


@pytest.fixture
def temp_root(tmp_path):
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    return tmp_path


# =============================================================================
# 1. The CLI surface is really gone
# =============================================================================
def test_real_atdd_issue_exits_non_zero_naming_the_replacements(temp_root):
    """A real `atdd issue open` must fail loud, not silently succeed."""
    result = _run_atdd(["issue", "open"], cwd=temp_root, control_root=temp_root)

    assert result.returncode != 0, (
        "`atdd issue open` must exit non-zero after 4.0.0 removal; "
        f"got rc=0\nstdout:\n{result.stdout}"
    )
    combined = result.stdout + result.stderr
    assert "4.0.0" in combined
    assert "atdd coach" in combined
    assert "atdd author issue" in combined
    assert "invalid choice" not in combined, (
        "the removal guard must run before argparse so the operator sees the "
        "replacement, not a bare `invalid choice` error"
    )


def test_real_atdd_help_no_longer_lists_the_issue_subcommand(temp_root):
    result = _run_atdd(["--help"], cwd=temp_root, control_root=temp_root)
    assert result.returncode == 0, result.stderr
    # argparse renders the choice list as `{a,b,c}` and again as a help row.
    assert ",issue," not in result.stdout.replace(" ", "")
    assert "{issue" not in result.stdout.replace(" ", "")


def test_real_author_issue_dry_run_validates_and_writes_nothing(temp_root):
    """The ported `--dry-run`: exit 0, print a body, touch no store."""
    store = temp_root / ".atdd" / "state" / "state.sqlite"
    result = _run_atdd(
        [
            "author",
            "issue",
            "--title",
            "refactor(atdd): E006 smoke dry run",
            "--slug",
            "e006-smoke-dry-run",
            "--dry-run",
        ],
        cwd=temp_root,
        control_root=temp_root,
    )
    assert result.returncode == 0, (
        f"`atdd author issue --dry-run` failed (rc={result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "# " in result.stdout, "dry-run must print the rendered body"
    assert not store.exists(), "dry-run must not create/write the State Store"


# =============================================================================
# 2-4. Nothing shipped still names `atdd issue` as canonical
# =============================================================================
def _repo_text(rel: str) -> str:
    return (Path(find_repo_root()) / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "rel",
    [
        "src/atdd/coach/templates/bin/gh.shim",
        "src/atdd/coach/templates/hooks/pre-commit-gh-issue-create.sh",
    ],
)
def test_gh_issue_create_blockers_point_at_atdd_author_issue(rel):
    """The educational alternative must not be a removed command.

    Repointed to `atdd author issue`, which does NOT contain the substring
    `atdd issue` — the eight assertions coupled to that substring move with it.
    """
    text = _repo_text(rel)
    assert "atdd author issue" in text, f"{rel} must name `atdd author issue`"
    assert "atdd issue <slug>" not in text, (
        f"{rel} still tells the operator to run the removed `atdd issue <slug>`"
    )


def test_issue_convention_cli_commands_names_coach_and_author():
    text = _repo_text("src/atdd/coach/conventions/issue.convention.yaml")
    head = text.split("hard_dependencies:")[0]
    assert "atdd coach" in head or "atdd author issue" in head
    for removed in (
        "atdd issue <slug>",
        "atdd issue <NN>",
        "atdd issue open",
    ):
        assert removed not in head, (
            f"issue.convention.yaml still presents `{removed}` as canonical"
        )


def test_conductor_template_issues_block_names_coach_and_author():
    text = _repo_text("src/atdd/coach/templates/CONDUCTOR.md")
    assert 'enter: "atdd coach' in text or "enter: 'atdd coach" in text
    assert '"atdd issue <N>"' not in text
    assert '"atdd issue <N> --status <STATUS>"' not in text


def test_no_deprecation_warning_recommends_the_removed_command():
    """The four surviving hints (archive, update x2, close-wmbt) are repointed.

    Matched with the C2 validator's OWN regex rather than a line substring, so
    prose in a comment that merely mentions `_deprecation_warning("atdd issue
    ...")` cannot false-flag (or, worse, false-pass) this check.

    Scans CALLSITES, not the deduped registry: two `atdd update` callsites share
    a head, so the registry keeps only the first and would hide a dangling
    second (cli.py:2452 vs cli.py:2461).
    """
    from atdd.coach.validators.test_fix_hint_completeness import (
        iter_deprecation_callsites,
    )

    callsites = iter_deprecation_callsites(_repo_text("src/atdd/cli.py"))
    offenders = [(old, new) for old, new in callsites if "atdd issue" in new]
    assert not offenders, (
        f"these _deprecation_warning callsites still recommend `atdd issue`: {offenders}"
    )
