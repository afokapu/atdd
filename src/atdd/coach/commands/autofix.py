"""
Opt-in programmatic fixes for coach validators.

Triggered via ``atdd validate coach --fix``. Today this module implements
exactly one fixer — the GitHubClient stub autofixer (#304) — but the
registry pattern is in place so additional fixers can plug in without
further CLI churn.

Design notes (#304 Decision #5):
- Default ``atdd validate coach`` is read-only; only ``--fix`` mutates.
- Every fixer prints a per-edit summary and is idempotent: running it
  twice on the same tree produces no second edit and exit code 0.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional, Tuple

from atdd.coach.utils.repo import find_repo_root

CLIENT_NAME = "GitHubClient"
CLIENT_IMPORT = "from atdd.coach.github import GitHubClient"
AUTOSPEC_IMPORT = "from unittest.mock import create_autospec"


def _iter_test_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")


def _find_offending_classes(tree: ast.AST) -> List[ast.ClassDef]:
    """Return class nodes whose name contains ``GitHubClient`` (case-insensitive)
    and which do not explicitly inherit from the real ``GitHubClient``.
    """
    out: List[ast.ClassDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if "githubclient" not in node.name.lower():
            continue
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)
        if CLIENT_NAME in bases:
            continue
        out.append(node)
    return out


def _rewrite_file(path: Path) -> Tuple[int, Optional[str]]:
    """Rewrite a single file to subclass ``GitHubClient`` from any
    hand-rolled stub class named ``*GitHubClient``.

    Minimal-risk conversion: add ``(GitHubClient)`` as the class base so
    the real method signatures are inherited. Callers that want an
    autospec mock migrate by hand; the autofix just closes the
    drift-invisibility window. Idempotent: classes already inheriting
    from ``GitHubClient`` are untouched.

    Returns ``(edit_count, message)`` — message is ``None`` when no edit
    was needed.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return (0, f"skip {path}: {exc}")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return (0, f"skip {path}: parse error ({exc})")

    offenders = _find_offending_classes(tree)
    if not offenders:
        return (0, None)

    lines = source.splitlines(keepends=True)
    edits = 0
    # Apply from bottom to top so earlier line offsets stay valid.
    for cls in sorted(offenders, key=lambda c: c.lineno, reverse=True):
        idx = cls.lineno - 1
        original = lines[idx]
        if f"{cls.name}(" in original and CLIENT_NAME in original:
            continue  # already migrated
        stripped = original.rstrip("\n")
        # Naive but scoped: we only rewrite `class Name:` → `class Name(GitHubClient):`.
        needle_plain = f"class {cls.name}:"
        replacement = f"class {cls.name}({CLIENT_NAME}):"
        if needle_plain in stripped:
            lines[idx] = stripped.replace(needle_plain, replacement) + "\n"
            edits += 1
            continue
        # Class with existing bases — insert GitHubClient at front.
        needle_bases = f"class {cls.name}("
        if needle_bases in stripped:
            lines[idx] = stripped.replace(
                needle_bases, f"class {cls.name}({CLIENT_NAME}, ", 1
            ) + "\n"
            edits += 1
            continue

    if not edits:
        return (0, None)

    # Ensure `from atdd.coach.github import GitHubClient` is importable.
    joined = "".join(lines)
    if CLIENT_IMPORT not in joined:
        # Insert after the module docstring + existing imports block.
        insert_at = _find_import_anchor(lines)
        lines.insert(insert_at, CLIENT_IMPORT + "\n")

    path.write_text("".join(lines), encoding="utf-8")
    return (edits, f"{path}: converted {edits} class(es)")


def _find_import_anchor(lines: List[str]) -> int:
    """Return a line index suitable for inserting a new import.

    Walks past the module docstring and any leading ``import``/``from``
    statements; returns the first line after them. Falls back to 0 when
    the file starts with code immediately.
    """
    i = 0
    n = len(lines)
    # Module docstring
    if i < n and lines[i].lstrip().startswith(('"""', "'''")):
        quote = lines[i].lstrip()[:3]
        # Single-line docstring?
        if lines[i].count(quote) >= 2:
            i += 1
        else:
            i += 1
            while i < n and quote not in lines[i]:
                i += 1
            i += 1
    # Blank lines + imports
    while i < n:
        stripped = lines[i].strip()
        if stripped == "" or stripped.startswith(("import ", "from ")):
            i += 1
            continue
        break
    return i


def run_github_client_stub_autofix(
    repo_root: Optional[Path] = None,
) -> int:
    """Walk ``src/atdd/coach/commands/tests/`` and convert any hand-rolled
    ``GitHubClient`` stub to a subclass of the real ``GitHubClient``.

    Prints per-file edit messages and a footer summary. Always returns 0
    unless a write error escalates; callers use the message output to
    decide whether to commit.
    """
    # autofix targets toolkit-self test sources only; falls through silently
    # when run from a pip-installed consumer (root.exists() check below).
    root = (repo_root or find_repo_root()) / "src" / "atdd" / "coach" / "commands" / "tests"  # atdd:suppress(coach.source-layout.no-toolkit-self-layout-assumption)
    if not root.exists():
        print(f"autofix: tests root not found: {root}")
        return 0

    total_edits = 0
    files_edited = 0
    for path in _iter_test_files(root):
        edits, msg = _rewrite_file(path)
        if msg:
            print(f"autofix: {msg}")
        if edits:
            total_edits += edits
            files_edited += 1

    if total_edits == 0:
        print(
            "autofix: no hand-rolled GitHubClient stubs found "
            "(tree already compliant)."
        )
    else:
        print(
            f"autofix: converted {total_edits} class(es) across "
            f"{files_edited} file(s). Review the diff before committing."
        )
    return 0
