# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D006-UNIT-001-default-clients-registered
# Acceptance: acc:judge-ambiguous-decisions:LLM-REGISTRY-001-default-clients-registered
# WMBT: wmbt:judge-ambiguous-decisions:D006
# Phase: RED
# Layer: application
"""D006-UNIT-001 — When the claude CLI is available, at least 2 production
clients are registered in LLM_REGISTRY at import time.

Spec: issue #592 acc:judge-ambiguous-decisions:LLM-REGISTRY-001-default-clients-registered
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch


def _fresh_import(module_name: str, extra_modules: list[str] | None = None):
    """Remove module and submodules from sys.modules so they re-import fresh."""
    to_remove = [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]
    if extra_modules:
        for em in extra_modules:
            to_remove += [k for k in sys.modules if k == em or k.startswith(em + ".")]
    for k in to_remove:
        del sys.modules[k]


def test_at_least_two_clients_registered_when_claude_available(tmp_path, monkeypatch):
    """When shutil.which('claude') returns a path, 2+ clients are registered."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    fake_claude = str(tmp_path / "claude")

    try:
        with patch("shutil.which", return_value=fake_claude):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            registered = register_production_clients()

        assert len(registered) >= 2, f"Expected >=2 clients, got {registered}"
        assert len(judge_mod.LLM_REGISTRY) >= 2, (
            f"LLM_REGISTRY has {sorted(judge_mod.LLM_REGISTRY)}, expected >=2"
        )
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)


def test_registered_factories_are_callable(tmp_path, monkeypatch):
    """Each registered factory returns an object with an invoke() method."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    fake_claude = str(tmp_path / "claude")

    try:
        with patch("shutil.which", return_value=fake_claude):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            registered = register_production_clients()

        for name in registered:
            factory = judge_mod.LLM_REGISTRY[name]
            assert callable(factory), f"Factory for {name!r} is not callable"
            client = factory()
            assert hasattr(client, "invoke"), f"Client for {name!r} has no invoke()"
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)


def test_registered_names_include_expected_claude_models(tmp_path):
    """Registered names include claude-haiku and claude-sonnet-4-6."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    fake_claude = str(tmp_path / "claude")

    try:
        with patch("shutil.which", return_value=fake_claude):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            register_production_clients()

        assert "claude-haiku" in judge_mod.LLM_REGISTRY
        assert "claude-sonnet-4-6" in judge_mod.LLM_REGISTRY
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)
