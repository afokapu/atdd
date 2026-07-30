# URN: test:govern-lifecycle:bind-issue-feature:Y006-SMOKE-001-real-cli-revise-populates-the-store
# Acceptance: acc:govern-lifecycle:Y006-SMOKE-001-real-cli-revise-populates-the-store
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: Against the real CLI in a real checkout with a real State Store, setting --feature on an existing issue changes the stored binding.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:Y006-SMOKE-001-real-cli-revise-populates-the-store
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:Y006

Purpose: close the measured gap where the body updated and the store did not.

An in-process unit proves the seam threads the argument; it does not prove the
shipped entry point does. That distinction is the whole of Break 4 — the flag
looked functional because the command exited 0 and the body changed.

Real: a real `python -m atdd` subprocess, a real on-disk SQLite State Store,
and a real `plan/` tree. The GitHub projection is made unreachable by pointing
PATH at a directory with no `gh`, so the outbox path is taken and the store
write must stand on its own.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import (
    ABSENT_FEATURE_URN,
    FEATURE_URN,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 93001
_REPO_SRC = Path(__file__).resolve().parents[4]  # .../src


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the real CLI in a separate process against ``root``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    # No `gh` on PATH: the GitHub projection must be unreachable so the store
    # write is what the assertion observes.
    env["PATH"] = str(root / "empty-bin")
    (root / "empty-bin").mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue", "--revise", *args],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.fixture()
def repo(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug="smoke-binding-probe", issue_number=_ISSUE, feature=None)
    # A schema-valid body: `_run_issue_revise` gates on `validate_issue_body`
    # before it ever reaches the feature check, so a hand-rolled fragment would
    # make the CLI exit non-zero for a schema reason and the assertions below
    # would prove nothing about plan/ resolution.
    from atdd.planner.commands.author_issue import create_issue_body

    body = tmp_path / "body.md"
    body.write_text(
        create_issue_body({"title": "smoke binding probe", "feature": FEATURE_URN}),
        encoding="utf-8",
    )
    return root, store, body


def test_real_cli_revise_writes_the_feature_to_the_store(repo) -> None:
    """The shipped artifact writes the field, not merely the body."""
    root, store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--feature", FEATURE_URN)

    assert result.returncode == 0, (
        f"real CLI revise exited {result.returncode}\nstderr:\n{result.stderr}"
    )
    assert read_issue_data(store, _ISSUE)["feature"] == FEATURE_URN, (
        "the real CLI exited 0 and left the stored feature unchanged — the "
        "exact behaviour measured across eight issues on 2026-07-28, and "
        "reproduced on #1635 itself while publishing its own plan"
    )


def test_store_write_stands_when_the_projection_is_deferred(repo) -> None:
    """Provider unreachable must not cost the binding."""
    root, store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--feature", FEATURE_URN)

    assert result.returncode == 0, result.stderr
    assert read_issue_data(store, _ISSUE)["feature"] == FEATURE_URN, (
        "the binding was lost because the GitHub projection was unreachable; "
        "the store is authoritative and must not depend on provider reachability"
    )


def test_a_non_resolving_feature_exits_non_zero_and_changes_nothing(repo) -> None:
    """A URN that resolves to nothing in plan/ is refused by the real CLI.

    `--body-file` is supplied so the revision is otherwise well-formed. Without
    it the command exits non-zero for an unrelated reason — the `_run_issue_revise`
    precondition that `--revise` requires `--body-file` and/or `--type` — and the
    assertion would pass while proving nothing about plan/ resolution.
    """
    root, store, body = repo
    before = read_issue_data(store, _ISSUE)["feature"]

    result = _run_cli(root, str(_ISSUE), "--body-file", str(body),
                      "--feature", ABSENT_FEATURE_URN)

    assert result.returncode != 0, (
        "the real CLI accepted a feature URN that resolves to nothing in plan/"
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert ABSENT_FEATURE_URN in combined, (
        "the CLI exited non-zero without naming the URN that failed to resolve, "
        "so the refusal is not attributable to plan/ resolution"
    )
    assert read_issue_data(store, _ISSUE)["feature"] == before, (
        "a refused revision still mutated the stored binding"
    )


def test_cli_reports_the_binding_it_wrote(repo) -> None:
    """The operator can tell from the output which binding landed."""
    root, _store, _body = repo

    result = _run_cli(root, str(_ISSUE), "--feature", FEATURE_URN)

    combined = (result.stdout or "") + (result.stderr or "")
    assert FEATURE_URN in combined, (
        "the CLI wrote a binding without naming it, so an operator cannot tell "
        "a successful write from a silently-ignored flag — the ambiguity that "
        "let Break 4 survive"
    )
    assert json.dumps(FEATURE_URN)  # guard: the URN is a plain serialisable value
