# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E053-UNIT-001-no-projects-v2-module-or-token-in-shipped-code
# Acceptance: acc:govern-lifecycle:E053-UNIT-001-no-projects-v2-module-or-token-in-shipped-code
# WMBT: wmbt:govern-lifecycle:E053
# Phase: RED
# Harness: unit
# Assertion: structural
# Layer: backend
"""E053-UNIT-001 — the Projects-v2 module and token plumbing are gone.

Post-removal contract: ``integrations/github/projects_v2.py`` does not exist and
no PROJECT_TOKEN / project_token / resolve_project_config / board-method symbols
remain in shipped code (excluding _archived, CHANGELOG, migration docs and tests).

RED now: projects_v2.py exists and the symbols are live in shipped code.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _src_root() -> Path:
    # src/atdd/coach/commands/tests/<this>  → parents[4] == src
    return Path(__file__).resolve().parents[4] / "atdd"


FORBIDDEN_SYMBOLS = (
    "PROJECT_TOKEN",
    "project_token",
    "resolve_project_config",
    "set_project_field_select",
    "set_project_field_text",
    "get_project_fields",
    "get_project_item_id",
    "get_project_item_field_values",
    "add_issue_to_project",
)


def _shipped_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune archives, caches and test trees (tests legitimately name the symbols).
        dirnames[:] = [
            d for d in dirnames
            if d not in {"__pycache__", "_archived", "tests"}
        ]
        for fname in filenames:
            if fname.endswith(".py") and not fname.startswith("test_"):
                yield Path(dirpath) / fname


def test_projects_v2_module_absent():
    mod = _src_root() / "integrations" / "github" / "projects_v2.py"
    assert not mod.exists(), f"projects_v2 substrate must be deleted: {mod}"


def test_no_projects_v2_symbols_in_shipped_code():
    root = _src_root()
    offenders = []
    for path in _shipped_py_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for sym in FORBIDDEN_SYMBOLS:
            if sym in text:
                offenders.append(f"{path.relative_to(root)}: {sym}")
    assert not offenders, "Projects-v2 substrate symbols remain:\n" + "\n".join(sorted(offenders))


def test_config_loader_does_not_require_project_id():
    """The .atdd/config.yaml loader no longer defines or reads project_id."""
    gh_init = _src_root() / "integrations" / "github" / "_gh.py"
    text = gh_init.read_text(encoding="utf-8", errors="ignore")
    assert "project_id" not in text, "config loader still references project_id"
