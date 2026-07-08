# URN: test:state-store:shared-store-per-project:layout
# Issue: #1315 (#1168 Phase 5)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1315 — single shared State Store per project (#1168 Phase 5).

The operational State Store must be ONE per project, living at the project root
*above* all worktrees (``<project>/.atdd/state/state.sqlite``), shared by every
worktree. The project root is derived deterministically from the git common dir
(the primary ``main/`` checkout's ``.git``) — not from per-worktree ``.atdd/``
markers, which every worktree commits and which would otherwise force a
per-worktree store (or raise :class:`AmbiguousControlRootError`).

These tests are hermetic: the git-common-dir lookup is injected via the
``git_common_dir`` parameter so no real git invocation is needed. Production
wires in the real git-backed resolver.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import cli as state_cli
from atdd.state.paths import (
    LayoutMode,
    resolve_control_root,
)


def _mk_worktree(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)
    return path


def _mk_marked_worktree(path: Path) -> Path:
    """A worktree carrying committed control-root markers (config + manifest)."""
    _mk_worktree(path)
    (path / ".atdd").mkdir(parents=True, exist_ok=True)
    (path / ".atdd" / "config.yaml").write_text("x\n", encoding="utf-8")
    (path / ".atdd" / "manifest.yaml").write_text("version: '2.0'\n", encoding="utf-8")
    return path


def _flat_sibling(tmp_path: Path):
    """Build project/{main,wt}/ where all worktrees share project/main/.git.

    Returns ``(project, main, wt, git_common_dir)`` where ``git_common_dir`` is a
    callable that mimics ``git rev-parse --git-common-dir`` for a flat-sibling
    layout (it always resolves to ``project/main/.git``).
    """
    project = tmp_path / "project"
    main = _mk_marked_worktree(project / "main")
    wt = _mk_marked_worktree(project / "feat-x")
    common = main / ".git"

    def git_common_dir(_start: Path):
        return common

    return project, main, wt, git_common_dir


# --------------------------------------------------------------------------- #
# Shared-store resolution (the #1315 contract)
# --------------------------------------------------------------------------- #
def test_store_resolves_to_project_root_from_a_worktree(tmp_path):
    project, _main, wt, gcd = _flat_sibling(tmp_path)

    res = resolve_control_root(wt, env={}, git_common_dir=gcd)

    assert res.layout_mode is LayoutMode.SIBLING_WORKTREE
    assert res.control_root == project
    assert res.state_store_path == project / ".atdd" / "state" / "state.sqlite"


def test_store_resolves_to_project_root_from_the_primary_main_checkout(tmp_path):
    project, main, _wt, gcd = _flat_sibling(tmp_path)

    res = resolve_control_root(main, env={}, git_common_dir=gcd)

    assert res.control_root == project
    assert res.state_store_path == project / ".atdd" / "state" / "state.sqlite"


def test_all_worktrees_resolve_to_the_same_store(tmp_path):
    project, main, wt, gcd = _flat_sibling(tmp_path)

    from_main = resolve_control_root(main, env={}, git_common_dir=gcd)
    from_wt = resolve_control_root(wt, env={}, git_common_dir=gcd)

    assert from_main.state_store_path == from_wt.state_store_path


def test_worktree_markers_do_not_force_per_worktree_store(tmp_path):
    # Every worktree commits .atdd/config.yaml + manifest.yaml. Under the shared
    # layout these must NOT make the worktree its own store root, and must NOT
    # raise AmbiguousControlRootError even when the project root is also a root.
    project, _main, wt, gcd = _flat_sibling(tmp_path)
    (project / ".atdd" / "state").mkdir(parents=True, exist_ok=True)  # project is a root too

    res = resolve_control_root(wt, env={}, git_common_dir=gcd)

    assert res.control_root == project


def test_env_override_still_wins_over_shared_resolution(tmp_path):
    project, _main, wt, gcd = _flat_sibling(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".atdd" / "state").mkdir(parents=True, exist_ok=True)

    res = resolve_control_root(wt, env={"ATDD_CONTROL_ROOT": str(elsewhere)}, git_common_dir=gcd)

    assert res.control_root == elsewhere


def test_single_repo_unaffected_when_common_dir_not_flat_sibling(tmp_path):
    # A plain single-repo checkout (not a flat-sibling "main/" layout): the store
    # stays inside the repo. Simulated by a git_common_dir whose parent is not
    # named "main".
    repo = _mk_marked_worktree(tmp_path / "repo")

    res = resolve_control_root(repo, env={}, git_common_dir=lambda _s: repo / ".git")

    assert res.layout_mode is LayoutMode.SINGLE_REPO
    assert res.control_root == repo
    assert res.state_store_path == repo / ".atdd" / "state" / "state.sqlite"


# --------------------------------------------------------------------------- #
# migrate-layout consolidation command (#1168 Phase 5 one-shot)
# --------------------------------------------------------------------------- #
def _manifest_with_one_session(root: Path) -> None:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "manifest.yaml").write_text(
        "version: '2.0'\n"
        "created: '2026-07-02'\n"
        "sessions:\n"
        "- id: '1315'\n"
        "  slug: single-shared-state-store-per-project\n"
        "  file: null\n"
        "  issue_number: 1315\n"
        "  type: implementation\n"
        "  status: INIT\n"
        "  created: '2026-07-02'\n"
        "  archived: null\n",
        encoding="utf-8",
    )


def test_migrate_layout_merges_per_worktree_store_and_deletes_it(tmp_path):
    # #1346 replaced the rebuild-from-manifest one-shot with a genuine merge: a
    # per-worktree store's rows are folded into the control-root store and the
    # per-worktree DB is deleted (not merely reported as abandoned).
    from atdd.state.cli import migrate_layout
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    project = tmp_path / "project"
    project.mkdir()
    # a real per-worktree store carrying a work_item
    wt = project / "feat-x"
    (wt / ".git").mkdir(parents=True)
    wt_db = wt / ".atdd" / "state" / "state.sqlite"
    src = StateStore(connect(init_state_store(db_path=wt_db)))
    src.objects.upsert("wi-x", "work_item", state="GREEN")

    result = migrate_layout(project_root=project)

    shared = project / ".atdd" / "state" / "state.sqlite"
    assert shared.is_file()
    assert result.store_path == shared
    assert result.merged >= 1
    # the per-worktree store is deleted, not abandoned
    assert not wt_db.exists()
    assert any("feat-x" in str(p) for p in result.deleted)

    conn = connect(shared)
    try:
        store = StateStore(conn)
        wi = store.objects.get("wi-x")
        assert wi is not None and wi.kind == "work_item"
    finally:
        conn.close()


def test_migrate_layout_cli_reports_shared_store(tmp_path, capsys):
    project = tmp_path / "project"
    main = project / "main"
    _manifest_with_one_session(main)

    rc = state_cli.run(["migrate-layout", "--project-root", str(project)])
    out = capsys.readouterr().out

    assert rc == 0
    assert str(project / ".atdd" / "state" / "state.sqlite") in out
