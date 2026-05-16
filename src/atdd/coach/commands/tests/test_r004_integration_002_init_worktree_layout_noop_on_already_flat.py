# URN: test:govern-lifecycle:R004-INTEGRATION-002-init-worktree-layout-noop-on-already-flat
# Acceptance: acc:govern-lifecycle:R004-INTEGRATION-002-init-worktree-layout-noop-on-already-flat
# WMBT: wmbt:govern-lifecycle:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""RED test for #720 — `atdd init --worktree-layout` must be an idempotent
no-op on a repo already in flat-sibling layout, whether invoked from the main/
primary checkout or from a linked sibling worktree.

ProjectInitializer.init(worktree_layout=True) already takes the no-op
"Already in worktree-ready layout" branch when target_dir is main/. From a
linked sibling worktree it currently mis-detects the layout as "worktree" and
aborts with "You are inside a linked worktree" instead of the no-op branch.

This test FAILS today on the linked-worktree iteration: it expects the
worktree-ready no-op branch and zero file moves for BOTH targets.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def _make_flat_sibling_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a main/ primary checkout plus one flat sibling linked worktree."""
    main = tmp_path / "main"
    main.mkdir()
    _git("init", str(main))
    _git("-C", str(main), "config", "user.email", "t@t.test")
    _git("-C", str(main), "config", "user.name", "Tester")
    (main / "README.md").write_text("seed\n")
    _git("-C", str(main), "add", ".")
    _git("-C", str(main), "commit", "-m", "init")
    worktree = tmp_path / "feat-demo"
    _git("-C", str(main), "worktree", "add", str(worktree), "-b", "feat/demo")
    return main, worktree


def _snapshot(root: Path) -> dict[str, bytes]:
    """Map every file path (relative to root) to its bytes."""
    out: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


def test_r004_integration_002_init_worktree_layout_noop_on_already_flat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    main, worktree = _make_flat_sibling_repo(tmp_path)

    for target in (main, worktree):
        # An existing .atdd/ makes init() stop right after the layout block
        # (at the "already initialized" guard), keeping the test bounded.
        (target / ".atdd").mkdir(exist_ok=True)
        before = _snapshot(target)

        init = ProjectInitializer(target_dir=target)
        migrate_calls: list[int] = []
        monkeypatch.setattr(
            init, "_migrate_to_worktree_layout",
            lambda: migrate_calls.append(1),  # type: ignore[arg-type]
        )
        monkeypatch.setattr(init, "_write_workspace", lambda: None)

        capsys.readouterr()  # drain
        init.init(worktree_layout=True, force=False)
        out = capsys.readouterr().out

        # Zero files moved — the migration path must never run.
        assert migrate_calls == []
        # The on-disk file set is byte-for-byte identical.
        assert _snapshot(target) == before
        # RED: for the linked worktree, init currently prints
        # "Error: You are inside a linked worktree" instead of taking the
        # worktree-ready no-op branch.
        assert "Already in worktree-ready layout" in out
        assert "You are inside a linked worktree" not in out
