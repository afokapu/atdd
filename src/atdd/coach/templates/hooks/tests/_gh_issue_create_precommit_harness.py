"""Shared harness for the pre-commit-gh-issue-create.sh hook tests (issue #816).

The hook source lives at src/atdd/coach/templates/hooks/pre-commit-gh-issue-create.sh
and is installed to .git/hooks/pre-commit by ``atdd init``. It greps the staged
diff for added lines matching ``^\\+.*\\bgh\\s+issue\\s+create\\b`` and rejects the
commit, exempting *.md paths.

RED state: the hook template does not exist yet, so ``install_hook`` asserts its
presence and fails with an explicit RED message until GREEN lands it.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root

REPO_ROOT = find_repo_root()
HOOK_TEMPLATE = (
    REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks" / "pre-commit-gh-issue-create.sh"
)


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    for key, val in (("user.email", "t@atdd.test"), ("user.name", "atdd test")):
        subprocess.run(["git", "-C", str(path), "config", key, val], check=True, capture_output=True)


def install_hook(repo: Path) -> Path:
    """Copy the pre-commit hook template into <repo>/.git/hooks/pre-commit (mode 0755)."""
    assert HOOK_TEMPLATE.exists(), (
        f"RED: pre-commit hook template not implemented yet at {HOOK_TEMPLATE.relative_to(REPO_ROOT)}"
    )
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    dst = hooks / "pre-commit"
    shutil.copy(HOOK_TEMPLATE, dst)
    dst.chmod(0o755)
    return dst


def stage(repo: Path, rel_path: str, content: str) -> None:
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel_path], check=True, capture_output=True)


def run_precommit(repo: Path) -> subprocess.CompletedProcess:
    """Invoke the installed pre-commit hook directly, as `git commit` would."""
    return subprocess.run(
        [str(repo / ".git" / "hooks" / "pre-commit")],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=20,
    )
