# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E053-UNIT-002-claude-md-source-of-truth-debanners-projects-v2
# Acceptance: acc:govern-lifecycle:E053-UNIT-002-claude-md-source-of-truth-debanners-projects-v2
# WMBT: wmbt:govern-lifecycle:E053
# Phase: GREEN
# Harness: unit
# Assertion: structural
# Layer: backend
"""E053-UNIT-002 — no shipped artifact declares a Projects-v2 source of truth.

This acceptance originally read `issues.source_of_truth` out of the four rendered
agent-config files and asserted they agreed and no longer named Projects v2. #1811
retired that projection and #1941 deleted the files, so the original test could not
resolve a repo root any more and had been failing on every run (#1979).

The guarantee survives the projection: whatever declares the issue source of truth,
it must not name the board. That is what this scans for — so the acceptance stays
bound to something executable instead of becoming a declaration that verifies
nothing, which is the defect class #1979 exists to remove.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

BANNED = ("Projects v2", "Project v2", "Projects-v2")
_LINE_RE = re.compile(r"^[ \t]*(?:#[ \t]*)?source_of_truth:[ \t]*(.+)$", re.MULTILINE)

# Where a shipped declaration could live. plan/ and docs/ are excluded on purpose:
# they carry the HISTORY of the decommission and legitimately name the board.
_SHIPPED_ROOTS = ("src", ".atdd")
_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".tmpl"}


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / "plan").is_dir():
            return parent
    raise AssertionError("repo root not found")


def _declarations(root: Path) -> list[tuple[Path, str]]:
    found = []
    for rel in _SHIPPED_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in _SUFFIXES:
                continue
            if "__pycache__" in f.parts or ".atdd/runtime" in f.as_posix():
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "source_of_truth:" not in text:
                continue
            for m in _LINE_RE.finditer(text):
                found.append((f.relative_to(root), m.group(1).strip()))
    return found


def test_no_shipped_source_of_truth_names_projects_v2():
    root = _repo_root()
    offenders = [
        f"{path}: {value}"
        for path, value in _declarations(root)
        for banned in BANNED
        if banned in value
    ]
    assert not offenders, (
        "a shipped artifact declares an issues.source_of_truth naming the retired "
        f"Projects-v2 board: {offenders}"
    )
