"""
Unit tests for :mod:`atdd.coder.utils.python_file_walker`.

URN: urn:atdd:test:coder:utils:python_file_walker
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coder.utils.python_file_walker import (
    DEFAULT_EXCLUDE_PATTERNS,
    walk_consumer_python_files,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rels(root: Path, paths) -> set[str]:
    return {str(p.resolve().relative_to(root.resolve())) for p in paths}


def test_default_exclude_patterns_cover_vendored_dirs():
    """Regression guard for the canonical exclude list."""
    required = {
        "site-packages",
        ".venv",
        "venv",
        ".tox",
        "__pypackages__",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
    }
    missing = required - DEFAULT_EXCLUDE_PATTERNS
    assert not missing, f"DEFAULT_EXCLUDE_PATTERNS missing: {missing}"


def test_skips_all_vendored_directories_non_git(tmp_path: Path):
    """
    With no .git present, the walker falls back to rglob + exclude list.
    Files inside any vendored directory MUST NOT be yielded.
    """
    for rel in [
        ".venv/lib/python3.11/site-packages/atdd/module.py",
        "venv/lib/python3.11/site-packages/pkg/x.py",
        ".tox/py311/lib/pkg/y.py",
        "__pypackages__/3.11/lib/pkg/z.py",
        "node_modules/pkg/a.py",
        "build/lib/pkg/b.py",
        "dist/pkg/c.py",
        "some_pkg.dist-info/METADATA.py",
        "some_pkg.egg-info/PKG-INFO.py",
    ]:
        _write(tmp_path / rel, "x = 1\n")

    result = list(walk_consumer_python_files(tmp_path))
    assert result == [], f"Expected no files, got {[str(p) for p in result]}"


def test_non_git_fallback_yields_unexcluded_files(tmp_path: Path):
    """Fallback walker returns .py files that lie outside excluded dirs."""
    _write(tmp_path / "python" / "app.py", "x = 1\n")
    _write(tmp_path / "python" / "lib" / "helper.py", "y = 2\n")
    _write(tmp_path / ".venv" / "lib" / "vendored.py", "z = 3\n")  # excluded
    _write(tmp_path / "web" / "src" / "index.ts", "// not python\n")

    rels = _rels(tmp_path, walk_consumer_python_files(tmp_path))
    assert rels == {"python/app.py", "python/lib/helper.py"}


def test_nonexistent_root_yields_nothing(tmp_path: Path):
    ghost = tmp_path / "does-not-exist"
    assert list(walk_consumer_python_files(ghost)) == []


def test_git_ls_files_strategy_used_when_repo_initialised(tmp_path: Path):
    """
    With an initialised git repo tracking only consumer files, ``git
    ls-files`` MUST yield tracked files. Untracked vendored files (inside
    .venv) must NOT appear even if they live on disk.
    """
    if not _git_available():
        pytest.skip("git not available on PATH")

    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=str(tmp_path),
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "config", "commit.gpgsign", "false"],
        cwd=str(tmp_path),
        check=True,
    )

    _write(tmp_path / "python" / "app.py", "x = 1\n")
    _write(tmp_path / "python" / "sub" / "mod.py", "y = 2\n")
    _write(tmp_path / ".venv" / "lib" / "vendored.py", "z = 3\n")  # untracked

    subprocess.run(
        ["git", "add", "python/app.py", "python/sub/mod.py"],
        cwd=str(tmp_path),
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
    )

    rels = _rels(tmp_path, walk_consumer_python_files(tmp_path))
    assert rels == {"python/app.py", "python/sub/mod.py"}, rels


def test_git_strategy_excludes_tracked_vendored_files(tmp_path: Path):
    """
    Belt-and-braces: even if a consumer accidentally tracks a .venv file,
    the exclude filter catches it.
    """
    if not _git_available():
        pytest.skip("git not available on PATH")

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(tmp_path), check=True)

    _write(tmp_path / "python" / "app.py", "x = 1\n")
    _write(tmp_path / ".venv" / "lib" / "oops.py", "z = 3\n")  # accidentally tracked

    subprocess.run(
        ["git", "add", "python/app.py", ".venv/lib/oops.py"],
        cwd=str(tmp_path),
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
    )

    rels = _rels(tmp_path, walk_consumer_python_files(tmp_path))
    assert rels == {"python/app.py"}, (
        f"Tracked .venv file leaked past exclude filter: {rels}"
    )


def test_walking_a_subdir_works(tmp_path: Path):
    """
    Validators often pass ``repo_root / 'python'`` rather than the repo
    root itself. The walker must handle subdir roots correctly.
    """
    _write(tmp_path / "python" / "a.py", "x = 1\n")
    _write(tmp_path / "python" / "b.py", "y = 2\n")
    _write(tmp_path / ".venv" / "lib" / "c.py", "z = 3\n")  # outside subdir

    python_dir = tmp_path / "python"
    rels = {str(p.resolve().relative_to(python_dir.resolve()))
            for p in walk_consumer_python_files(python_dir)}
    assert rels == {"a.py", "b.py"}


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return False
    return True
