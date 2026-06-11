# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E053-UNIT-002-claude-md-source-of-truth-debanners-projects-v2
# Acceptance: acc:govern-lifecycle:E053-UNIT-002-claude-md-source-of-truth-debanners-projects-v2
# WMBT: wmbt:govern-lifecycle:E053
# Phase: RED
# Harness: unit
# Assertion: structural
# Layer: backend
"""E053-UNIT-002 — CLAUDE.md (and synced siblings) debanner Projects v2.

Post-removal contract: ``issues.source_of_truth`` names GitHub Issues (labels)
plus the local .atdd/manifest.yaml, no longer naming Projects v2 / Project v2 /
Projects-v2, and the four rendered files agree.

RED now: every file reads "GitHub Issues + Project v2 custom fields".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

SIBLINGS = ("CLAUDE.md", "GEMINI.md", "GLM.md", "AGENTS.md")
BANNED = ("Projects v2", "Project v2", "Projects-v2")
_LINE_RE = re.compile(r"^\s*source_of_truth:\s*(.+)$", re.MULTILINE)


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "CLAUDE.md").exists() and (parent / "plan").is_dir():
            return parent
    raise AssertionError("repo root with CLAUDE.md not found")


def _source_of_truth(path: Path) -> str:
    m = _LINE_RE.search(path.read_text(encoding="utf-8", errors="ignore"))
    assert m, f"source_of_truth not found in {path.name}"
    return m.group(1).strip()


def test_source_of_truth_debanners_projects_v2():
    root = _repo_root()
    values = {}
    for name in SIBLINGS:
        value = _source_of_truth(root / name)
        values[name] = value
        for banned in BANNED:
            assert banned not in value, f"{name} source_of_truth still names {banned!r}: {value}"
        assert "manifest" in value.lower(), f"{name} must name the local manifest: {value}"
        assert "label" in value.lower(), f"{name} must name issue labels: {value}"


def test_siblings_agree():
    root = _repo_root()
    rendered = {_source_of_truth(root / name) for name in SIBLINGS}
    assert len(rendered) == 1, f"source_of_truth disagrees across siblings: {rendered}"
