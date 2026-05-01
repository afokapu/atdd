"""
Manifest-write discipline coach validator.

Convention: src/atdd/coach/conventions/issue.convention.yaml (manifest_write_discipline)
Issue: #344

Manifest-mutating CLI verbs (atdd issue, atdd update --status, atdd archive)
must commit their `.atdd/manifest.yaml` write atomically with the verb so a
worktree branched from main HEAD inherits the new entry. The contract has two
halves:

1. The single commit helper exists and behaves correctly (covered by the
   helper's own unit tests in `src/atdd/coach/utils/tests/test_git.py`).

2. Every call site in `IssueManager` that writes the manifest funnels
   through that helper afterwards. This validator enforces the second
   half via an AST walk of `issue.py` so a future contributor who adds
   a new manifest-write site without a matching commit is caught in CI.

Behavioural integration test
----------------------------
On top of the static AST check, we also exercise the
`_commit_manifest_change` method against a real tmp git repo so we know
the wiring is functional (not just textually present).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root


pytestmark = [pytest.mark.platform]


REPO_ROOT = find_repo_root()
ISSUE_MODULE_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "commands" / "issue.py"
HELPER_MODULE_PATH = REPO_ROOT / "src" / "atdd" / "coach" / "utils" / "git.py"


# ---------------------------------------------------------------------------
# Static contract: every _save_manifest call has a follow-up commit
# ---------------------------------------------------------------------------


def _save_manifest_call_lines(tree: ast.AST) -> List[Tuple[str, int]]:
    """Return (enclosing_function_name, lineno) for every `self._save_manifest(...)`
    call, skipping the method definition itself.
    """
    found: List[Tuple[str, int]] = []
    func_stack: List[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            func_stack.append(node.name)
            try:
                self.generic_visit(node)
            finally:
                func_stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "_save_manifest"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                if func_stack and func_stack[-1] != "_save_manifest":
                    found.append((func_stack[-1], node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return found


def _has_commit_followup_in_function(tree: ast.AST, function_name: str) -> bool:
    """Return True if the named method body contains at least one
    `self._commit_manifest_change(...)` call.

    This is the textual half of the contract — every method that
    contains a `_save_manifest` call must also contain a
    `_commit_manifest_change` call. The helper itself raises on misuse,
    so a single follow-up call inside the same method is enough to make
    the verb compliant.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "_commit_manifest_change"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "self"
                ):
                    return True
    return False


def test_every_save_manifest_call_site_has_commit_followup():
    """Every method that writes `.atdd/manifest.yaml` must also call
    `self._commit_manifest_change(...)` so the write is committed
    atomically with the verb (issue #344)."""
    if not ISSUE_MODULE_PATH.is_file():
        pytest.skip(f"issue.py not found at {ISSUE_MODULE_PATH}")

    source = ISSUE_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ISSUE_MODULE_PATH))

    call_sites = _save_manifest_call_lines(tree)
    assert call_sites, (
        "Expected at least one `self._save_manifest(...)` call site in "
        f"{ISSUE_MODULE_PATH}; found none. The audit assumption may have "
        "drifted."
    )

    drift = []
    for func_name, lineno in call_sites:
        if not _has_commit_followup_in_function(tree, func_name):
            drift.append(
                f"{ISSUE_MODULE_PATH.name}:{lineno} — method "
                f"`{func_name}` calls self._save_manifest() but is missing a "
                f"matching `self._commit_manifest_change(...)` call. "
                f"See issue.convention.yaml `manifest_write_discipline`."
            )

    if drift:
        bullets = "\n  - ".join(drift)
        pytest.fail(
            "Manifest-write discipline violation — every CLI verb that "
            "mutates `.atdd/manifest.yaml` must commit the change "
            "atomically.\n"
            f"  - {bullets}"
        )


# ---------------------------------------------------------------------------
# Static contract: helper module surface is stable
# ---------------------------------------------------------------------------


def test_helper_module_exposes_required_surface():
    """The helper signature is part of the public contract — surface
    drift here would silently break every call site."""
    from atdd.coach.utils import git as git_helper

    assert hasattr(git_helper, "git_commit_manifest_update"), (
        "Helper module is missing `git_commit_manifest_update`."
    )
    assert hasattr(git_helper, "ManifestCommitError"), (
        "Helper module is missing `ManifestCommitError`."
    )

    import inspect

    sig = inspect.signature(git_helper.git_commit_manifest_update)
    expected = {"path", "message", "verb", "repo_root", "allow_main"}
    actual = set(sig.parameters.keys())
    missing = expected - actual
    assert not missing, (
        f"git_commit_manifest_update is missing expected parameters: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Behavioural: IssueManager._commit_manifest_change leaves a clean tree
# ---------------------------------------------------------------------------


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _setup_fixture_repo(tmp_path: Path) -> Path:
    """Create a worktree-shaped fixture: git init on a feat branch, with a
    tracked initial manifest and a minimal `.atdd/config.yaml`."""
    _run("git", "init", "-q", "-b", "main", cwd=tmp_path)
    _run("git", "config", "user.email", "test@example.com", cwd=tmp_path)
    _run("git", "config", "user.name", "Test User", cwd=tmp_path)
    _run("git", "config", "commit.gpgsign", "false", cwd=tmp_path)

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "config.yaml").write_text(
        "github:\n  repo: afokapu/atdd\n  project_id: PVT_x\n",
        encoding="utf-8",
    )
    (atdd_dir / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")

    _run("git", "add", ".atdd/", cwd=tmp_path)
    _run("git", "commit", "-q", "-m", "seed fixture", cwd=tmp_path)
    _run("git", "checkout", "-q", "-b", "feat/manifest-discipline-fixture", cwd=tmp_path)
    return tmp_path


def test_commit_manifest_change_leaves_clean_tree_after_write(tmp_path):
    """A simulated CLI verb writes the manifest and then calls
    `_commit_manifest_change`; the working tree must be clean afterwards."""
    from atdd.coach.commands.issue import IssueManager

    repo = _setup_fixture_repo(tmp_path)
    manager = IssueManager(target_dir=repo)

    # Simulate a verb's manifest mutation.
    manifest = manager._load_manifest()
    manifest.setdefault("sessions", []).append(
        {"issue_number": 999, "slug": "fixture", "status": "INIT"}
    )
    manager._save_manifest(manifest)

    # Working tree is dirty before the commit hook fires.
    porcelain_before = _run(
        "git", "status", "--porcelain", ".atdd/manifest.yaml", cwd=repo
    ).stdout
    assert "manifest.yaml" in porcelain_before

    manager._commit_manifest_change(
        verb="atdd issue",
        message="chore(coach): register fixture issue in manifest",
    )

    porcelain_after = _run(
        "git", "status", "--porcelain", ".atdd/manifest.yaml", cwd=repo
    ).stdout
    assert porcelain_after == "", (
        f"Expected clean tree after _commit_manifest_change; got: {porcelain_after!r}"
    )

    head_msg = _run("git", "log", "-1", "--format=%s", cwd=repo).stdout.strip()
    assert head_msg == "chore(coach): register fixture issue in manifest"


def test_commit_manifest_change_is_a_noop_outside_a_git_repo(tmp_path):
    """The helper must skip cleanly when the target dir is not a git repo
    (covers test fixtures that supply a bare tmp_path) — surfaced as a
    silent skip, not an exception."""
    from atdd.coach.commands.issue import IssueManager

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()
    (atdd_dir / "manifest.yaml").write_text("sessions: []\n", encoding="utf-8")
    manager = IssueManager(target_dir=tmp_path)

    # Should not raise.
    manager._commit_manifest_change(verb="atdd issue", message="msg")
