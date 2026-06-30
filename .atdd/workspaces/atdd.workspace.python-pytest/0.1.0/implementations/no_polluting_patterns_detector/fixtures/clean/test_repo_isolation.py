# URN: test:demo:clean:UNIT-001-git-ops-scoped-to-tmp_path
# Phase: GREEN
"""GREEN fixture: every git mutation is properly scoped to tmp_path (via -C,
cwd=tmp_path, --worktree, or a tmp_path init-path arg) -> RAW = [] -> PASS."""
import subprocess


def test_bare_init_with_tmp_path_arg(tmp_path):
    subprocess.run(["git", "init", "--bare", str(tmp_path / "remote.git")], check=True)


def test_core_bare_via_C_flag(tmp_path):
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.bare", "true"],
        check=True,
    )


def test_core_bare_via_cwd_tmp(tmp_path):
    subprocess.run(
        ["git", "config", "core.bare", "true"],
        cwd=str(tmp_path),
        check=True,
    )


def test_core_bare_via_worktree_flag():
    subprocess.run(["git", "config", "--worktree", "core.bare", "true"], check=True)
