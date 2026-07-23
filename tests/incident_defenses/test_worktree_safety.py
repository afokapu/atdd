# URN: test:govern-lifecycle:extract-runtime-worktree-preserving-incident-defenses:E038-UNIT-001-ensure-issue-worktree-creates-idempotent-core-bare
# Acceptance: acc:govern-lifecycle:E038-UNIT-001-ensure-issue-worktree-creates-idempotent-core-bare
# Acceptance: acc:govern-lifecycle:E038-UNIT-002-incident-defenses-bare-dispatch-and-protected-main
# Acceptance: acc:govern-lifecycle:E038-UNIT-003-import-discipline-and-call-site-routing
# WMBT: wmbt:govern-lifecycle:E038
# Phase: RED
# Layer: backend.application
"""Incident-defense suite for the extracted ``atdd.runtime.worktree`` layer.

Coach decomposition Child 5 (docs/coach-decomposition.md §13.5, §9, umbrella
#887). This is the canonical home for the three worktree incident defenses
named in §9:

- **I-1** — no bare-directory worktree dispatch
  (``test_refuses_bare_dispatch``)
- **I-2** — no protected-main commits
  (``test_blocks_main_commit``)
- **I-9** — ``git config --worktree core.bare false`` on creation
  (``test_sets_per_worktree_core_bare``) — the canonical fix for the recurring
  ``core.bare=true`` shared-config bleed.

RED until ``src/atdd/runtime/worktree.py`` exists and the runtime call sites
delegate to it.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _make_repo(root: Path) -> Path:
    """Create a minimal git repo at ``root/main`` with one seed commit."""
    repo = root / "main"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "ATDD Test", cwd=repo)
    (repo / "README.md").write_text("seed\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "seed", cwd=repo)
    return repo


def _worktree_listed(repo: Path, path: Path) -> bool:
    out = subprocess.run(
        ["git", "worktree", "list"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    return str(path) in out


def _read_worktree_core_bare(worktree: Path) -> str:
    """Read ``git config --worktree core.bare`` from inside ``worktree``."""
    res = subprocess.run(
        ["git", "config", "--worktree", "core.bare"],
        cwd=str(worktree), capture_output=True, text=True,
    )
    return res.stdout.strip()


# --------------------------------------------------------------------------- #
# AC-UNIT-001 — create / idempotent / I-9 core.bare=false
# --------------------------------------------------------------------------- #
def test_ensure_issue_worktree_creates_real_git_worktree(tmp_path):
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-thing"

    result = wt.ensure_issue_worktree(target, "feat/thing", repo)

    assert result == target
    assert (target / ".git").exists(), f"{target} is not a git worktree"
    assert _worktree_listed(repo, target)


def test_ensure_issue_worktree_is_idempotent(tmp_path):
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-thing"

    first = wt.ensure_issue_worktree(target, "feat/thing", repo)
    second = wt.ensure_issue_worktree(target, "feat/thing", repo)

    assert first == second == target
    # exactly one linked worktree registered for this path
    porcelain = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout
    assert porcelain.count(f"worktree {target}") == 1


def test_sets_per_worktree_core_bare(tmp_path):
    """I-9: every new worktree carries a per-worktree ``core.bare=false``."""
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-bare"

    wt.ensure_issue_worktree(target, "feat/bare", repo)

    assert _read_worktree_core_bare(target) == "false", (
        "ensure_issue_worktree must set `git config --worktree core.bare false` "
        "on the new worktree (incident defense I-9)"
    )


def test_creation_does_not_leave_shared_config_bare(tmp_path):
    """The creation path must not leave the SHARED repo config as core.bare=true."""
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-shared"

    wt.ensure_issue_worktree(target, "feat/shared", repo)

    shared = subprocess.run(
        ["git", "config", "--local", "core.bare"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout.strip()
    assert shared in ("", "false"), f"shared config left core.bare={shared!r}"


# --------------------------------------------------------------------------- #
# AC-UNIT-002 — I-1 bare/foreign dispatch + I-2 protected main
# --------------------------------------------------------------------------- #
def test_refuses_bare_dispatch(tmp_path):
    """I-1: a path that exists with foreign content is refused, never clobbered."""
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-foreign"
    target.mkdir()
    (target / "important.txt").write_text("do not delete me\n")

    result = wt.ensure_issue_worktree(target, "feat/foreign", repo)

    assert result is None, "foreign-content path must be refused (I-1)"
    assert (target / "important.txt").exists(), "must not clobber foreign content"
    assert not _worktree_listed(repo, target), "no worktree should be registered"


def test_clears_atdd_only_residue(tmp_path):
    """A path containing only atdd residue is safe to clear and create over."""
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-residue"
    target.mkdir()
    (target / ".launch_prompt.txt").write_text("stale\n")

    result = wt.ensure_issue_worktree(target, "feat/residue", repo)

    assert result == target
    assert (target / ".git").exists()


def test_is_protected_branch():
    from atdd.runtime import worktree as wt

    assert wt.is_protected_branch("main") is True
    assert wt.is_protected_branch("master") is True
    assert wt.is_protected_branch("feat/x") is False
    assert wt.is_protected_branch("fix/main-thing") is False


def test_blocks_main_commit(tmp_path):
    """I-2: refuses to create a worktree on a protected branch (would commit to main)."""
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "on-main"

    with pytest.raises(wt.ProtectedBranchError):
        wt.ensure_issue_worktree(target, "main", repo)

    assert not target.exists(), "no worktree must be created on a protected branch"
    assert not _worktree_listed(repo, target)


# --------------------------------------------------------------------------- #
# AC-UNIT-003 — import discipline (coach call-site retired with #1483)
# --------------------------------------------------------------------------- #
def test_runtime_worktree_has_no_forbidden_imports():
    """§3.3: atdd.runtime.worktree imports no orchestration/integration layer."""
    src = REPO_ROOT / "src" / "atdd" / "runtime" / "worktree.py"
    tree = ast.parse(src.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden = {
        "atdd.coach", "atdd.train", "atdd.integrations",
    }
    leaked = {
        imp for imp in imports
        for fb in forbidden
        if imp == fb or imp.startswith(fb + ".")
    }
    assert not leaked, f"runtime.worktree leaked forbidden imports: {leaked}"
# --------------------------------------------------------------------------- #
# remove_worktree
# --------------------------------------------------------------------------- #
def test_remove_worktree_unregisters_and_deletes(tmp_path):
    from atdd.runtime import worktree as wt

    repo = _make_repo(tmp_path)
    target = tmp_path / "feat-remove"
    wt.ensure_issue_worktree(target, "feat/remove", repo)
    assert _worktree_listed(repo, target)

    ok = wt.remove_worktree(target, repo, force=True)

    assert ok is True
    assert not _worktree_listed(repo, target)
    assert not target.exists()
