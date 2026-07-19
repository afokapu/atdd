# URN: test:place-worktrees:place-worktrees:E001-UNIT-001-both-creation-paths-agree-under-configured-root
# Acceptance: acc:place-worktrees:E001-UNIT-001-both-creation-paths-agree-under-configured-root
# WMBT: wmbt:place-worktrees:E001
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""E001-UNIT-001 — both worktree creation paths resolve the same configured root.

Issue #1524. The Phase 0 audit found `atdd worktree create` and `atdd coach enter`
are two COMPLETE creation paths, each deriving placement independently:

    branch.py:418           worktree_path = self.target_dir.parent / worktree_dir_name
    issue_lifecycle.py:178  worktree_path = self.target_dir.parent / f"{prefix}-{slug}"

Introducing `worktree_root` at only one of them makes the two commands place the
same branch's worktree in different directories. This pins that a single resolver
decides for both.

Phase RED: fails because neither path reads `worktree_root` — both compute
`target_dir.parent`, ignoring the configured root entirely.
Phase GREEN: both resolve to `<root>/<worktree_root>/<prefix>-<slug>`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.coach.commands.branch import BranchManager
from atdd.coach.commands.issue_lifecycle import IssueLifecycle
from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

pytestmark = [pytest.mark.coach]

ISSUE = 1524
SLUG = "config-driven-worktree-placement"
PREFIX = "feat"
WORKTREE_ROOT = "worktrees"


def _proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _repo(tmp_path: Path) -> Path:
    """A control root whose config places worktrees under a NON-default root."""
    root = tmp_path / "main"
    (root / ".atdd").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\n"  # control-root marker
        "github:\n"
        "  repo: owner/repo\n"
        "  default_branch: main\n"
        f"worktree_root: {WORKTREE_ROOT}\n"
    )
    # `_find_issue` reads the State Store — the manifest fallback is retired
    # (#1400 CORE-034). Seed the work item the create path resolves.
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        store.objects.upsert(
            SLUG,
            WORK_ITEM_KIND,
            state="RED",
            data={"issue_number": ISSUE, "type": "implementation"},
        )
        store.external_refs.link(SLUG, GITHUB_PROVIDER, "issue", str(ISSUE))
        conn.commit()
    finally:
        conn.close()
    return root


def _expected(root: Path) -> Path:
    """Where the configured root says this branch's worktree belongs."""
    return root / WORKTREE_ROOT / f"{PREFIX}-{SLUG}"


def _legacy(root: Path) -> Path:
    """Where today's hardcoded flat-sibling derivation puts it."""
    return root.parent / f"{PREFIX}-{SLUG}"


def _run_side_effect(cmd, **kwargs):
    """git calls BranchManager.branch() makes before creating the worktree."""
    if cmd[:2] == ["git", "fetch"]:
        return _proc(0)
    if cmd[:3] == ["git", "branch", "-r"]:
        return _proc(0, stdout="")  # no remote branch → new-branch path
    return _proc(0)


def test_e001_unit_001_both_creation_paths_agree_under_configured_root(tmp_path):
    root = _repo(tmp_path)
    expected = _expected(root)

    # --- path 1: `atdd worktree create` (branch.py) -----------------------
    # ensure_issue_worktree is the runtime seam the coach layer hands an
    # already-derived absolute path to — capture what it is told to create.
    created: list = []

    def _capture(worktree_path, branch_name, target_dir, **kwargs):
        created.append(Path(worktree_path))
        Path(worktree_path).mkdir(parents=True, exist_ok=True)
        return Path(worktree_path)

    # The worktree-ready layout guard fires before the derivation and is not
    # the behaviour under test; a tmp_path repo is 'no-git'. Stubbing it keeps
    # the failure below about PLACEMENT rather than about repo shape.
    with patch("atdd.coach.utils.repo.detect_worktree_layout", return_value="worktree-ready"), \
         patch("atdd.runtime.worktree.ensure_issue_worktree", side_effect=_capture), \
         patch("atdd.coach.commands.branch.subprocess.run", side_effect=_run_side_effect), \
         patch.object(BranchManager, "_record_binding_in_store", return_value=True):
        BranchManager(root).branch(ISSUE)

    # Guard against a vacuous red: if branch.py never reaches the creation
    # seam, the assertions below would "fail" without exercising placement.
    assert created, "branch.py never reached the worktree-creation seam"
    create_path = created[0]

    # --- path 2: `atdd coach enter` (issue_lifecycle.py) ------------------
    # The lookup must find a worktree that genuinely exists under the
    # configured root. A directory also exists at the legacy sibling location,
    # so this pins that CONFIGURATION decides placement, not directory
    # happenstance — the lookup must not silently prefer the legacy path.
    expected.mkdir(parents=True, exist_ok=True)
    _legacy(root).mkdir(parents=True, exist_ok=True)

    enter_path = IssueLifecycle(root)._find_worktree_for_issue(SLUG, PREFIX)

    # --- the acceptance ---------------------------------------------------
    assert create_path == expected, (
        f"atdd worktree create placed the worktree at {create_path}, "
        f"but worktree_root: {WORKTREE_ROOT} says {expected}"
    )
    assert enter_path == expected, (
        f"atdd coach enter resolved the worktree to {enter_path}, "
        f"but worktree_root: {WORKTREE_ROOT} says {expected}"
    )
    # The point of the acceptance: the two commands agree with each other.
    assert create_path == enter_path, (
        "atdd worktree create and atdd coach enter disagree about placement: "
        f"{create_path} != {enter_path}"
    )
    # Neither may fall back to the hardcoded flat sibling.
    assert create_path != _legacy(root)
    assert enter_path != _legacy(root)
