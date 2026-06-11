# URN: test:govern-lifecycle:decommission-projects-v2-board-sync:E053-SMOKE-001-config-loads-and-github-imports-without-projects-v2
# Acceptance: acc:govern-lifecycle:E053-SMOKE-001-config-loads-and-github-imports-without-projects-v2
# WMBT: wmbt:govern-lifecycle:E053
# Phase: RED
# Harness: integration
# Assertion: behavioral
# Layer: backend
"""E053-SMOKE-001 — github imports with no projects_v2 and config loads sans project_id.

Post-removal contract: in a real interpreter, ``atdd.integrations.github`` exposes
no ``projects_v2`` attribute, importing the submodule raises ModuleNotFoundError,
and a config without project_id loads cleanly.

RED now: ``atdd.integrations.github.projects_v2`` still imports successfully.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


def test_importing_projects_v2_raises_module_not_found():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("atdd.integrations.github.projects_v2")


def test_integrations_github_exposes_no_projects_v2_attr():
    gh = importlib.import_module("atdd.integrations.github")
    assert not hasattr(gh, "projects_v2"), "integrations.github must not expose projects_v2"


def test_config_without_project_id_loads_cleanly(tmp_path):
    from atdd.coach.commands.issue import IssueManager

    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    # No project_id key at all.
    (cfg / "config.yaml").write_text(yaml.safe_dump({"github": {"repo": "owner/repo"}}))

    mgr = IssueManager(target_dir=tmp_path)
    loaded = mgr._load_config()
    assert loaded["github"]["repo"] == "owner/repo"
    assert "project_id" not in loaded.get("github", {})
