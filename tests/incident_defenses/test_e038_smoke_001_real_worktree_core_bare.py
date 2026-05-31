# URN: test:govern-lifecycle:extract-runtime-worktree-preserving-incident-defenses:E038-SMOKE-001-real-worktree-core-bare-false-on-disk
# Acceptance: acc:govern-lifecycle:E038-SMOKE-001-real-worktree-core-bare-false-on-disk
# WMBT: wmbt:govern-lifecycle:E038
# Phase: SMOKE
# Layer: backend.application
"""SMOKE — real on-disk proof of incident defense I-9.

Coach decomposition Child 5 (docs/coach-decomposition.md §13.5, §9). In a real
child interpreter process, against a real on-disk git repository, a worktree
created through the production ``atdd.runtime.worktree.ensure_issue_worktree``
must carry a per-worktree ``core.bare=false`` override — the canonical fix for
the recurring ``core.bare=true`` shared-config bleed.

This drives the real production wiring (the actual installed/importable module,
a real ``git worktree add``, and a real ``git config --worktree`` read) rather
than any synthetic fixture, per smoke.convention.yaml.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def test_real_worktree_has_per_worktree_core_bare_false(tmp_path):
    repo = tmp_path / "main"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.email", "smoke@example.com", cwd=repo)
    _git("config", "user.name", "ATDD Smoke", cwd=repo)
    (repo / "README.md").write_text("seed\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "seed", cwd=repo)

    target = tmp_path / "feat-smoke"

    # Real, fresh process exercising the production module end-to-end.
    src_dir = Path(__file__).resolve().parents[2] / "src"
    program = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(src_dir)!r})
        from atdd.runtime import worktree as wt
        result = wt.ensure_issue_worktree(
            {str(target)!r}, "feat/smoke", {str(repo)!r}, issue_number=892
        )
        assert result is not None, "ensure_issue_worktree returned None"
        print("CREATED", result)
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"child failed:\n{proc.stdout}\n{proc.stderr}"

    # The worktree is real and registered.
    listed = subprocess.run(
        ["git", "worktree", "list"], cwd=str(repo), capture_output=True, text=True
    ).stdout
    assert str(target) in listed, f"git does not list {target}:\n{listed}"

    # I-9: the per-worktree override is materialized on disk and reads false.
    core_bare = subprocess.run(
        ["git", "config", "--worktree", "core.bare"],
        cwd=str(target), capture_output=True, text=True,
    ).stdout.strip()
    assert core_bare == "false", (
        f"expected per-worktree core.bare=false on disk, got {core_bare!r}"
    )

    # The shared config must not be left bare by the creation path.
    shared = subprocess.run(
        ["git", "config", "--local", "core.bare"],
        cwd=str(repo), capture_output=True, text=True,
    ).stdout.strip()
    assert shared in ("", "false"), f"shared config left core.bare={shared!r}"
