# URN: test:place-worktrees:place-worktrees:E002-UNIT-001-launch-prompt-names-the-created-path
# Acceptance: acc:place-worktrees:E002-UNIT-001-launch-prompt-names-the-created-path
# WMBT: wmbt:place-worktrees:E002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E002-UNIT-001 — the launch prompt names the path the resolver created.

Issue #1524. The Phase 0 audit resolved the second open touchpoint: cmux DOES
derive worktree paths independently, but not where the issue's Notes looked.
`cmux_launch.py` takes `cwd` as a parameter and derives nothing. The derivation
is one layer up:

    session_template.py:225
        worktree_path=worktree_path or f"../{meta.get('Branch', '').replace('/', '-')}"

That is a THIRD algorithm — string manipulation of the branch name, producing a
relative `../` string rather than a resolved path — and its result is what the
launch prompt hands a spawned agent. Under a configured `worktree_root` the
agent is told to `cd` to a directory that was never created.

Phase RED: fails because build_context ignores `worktree_root` and emits
`../feat-<slug>`.
Phase GREEN: the fallback runs through the same resolver as the creation paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.session_template import build_context

pytestmark = [pytest.mark.coach]

ISSUE = 1524
SLUG = "config-driven-worktree-placement"
BRANCH = f"feat/{SLUG}"
WORKTREE_ROOT = "worktrees"

BODY = f"""# Config-driven worktree placement

## Issue Metadata

| Field | Value |
|-------|-------|
| Branch | `{BRANCH}` |
| Train | `train:coach:place-worktrees` |
| Feature | `feature:place-worktrees:place-worktrees` |
"""


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A control root configuring a NON-default worktree root."""
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        f"worktree_root: {WORKTREE_ROOT}\n"
    )
    monkeypatch.setattr(
        "atdd.coach.utils.repo.find_repo_root", lambda *a, **k: root, raising=False
    )
    return root


def test_e002_unit_001_launch_prompt_names_the_created_path(repo):
    # No explicit worktree_path — this is the spawn path that falls back to
    # deriving one, which is precisely the derivation under test.
    context = build_context(ISSUE, BODY, title="Config-driven worktree placement")

    emitted = context.worktree_path

    # Guard against a vacuous red: the fallback must actually have produced
    # something, otherwise the assertions below prove nothing.
    assert emitted, "build_context emitted no worktree_path at all"

    expected = repo / WORKTREE_ROOT / f"feat-{SLUG}"

    # The string-manipulation form is the defect: a relative `../` path that
    # encodes the flat-sibling layout as an assumption.
    assert not str(emitted).startswith("../"), (
        f"launch prompt emitted the relative string {emitted!r}; the spawned "
        "agent needs the path the resolver actually created"
    )
    assert Path(emitted) == expected, (
        f"launch prompt names {emitted}, but worktree_root: {WORKTREE_ROOT} "
        f"places this branch's worktree at {expected}"
    )
