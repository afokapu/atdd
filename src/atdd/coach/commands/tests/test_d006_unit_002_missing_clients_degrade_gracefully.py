# URN: test:integration-hardening:coach-single-command-driver:C001-INTEGRATION-002-missing-clients-degrade-gracefully
# Acceptance: acc:integration-hardening:C001-INTEGRATION-002-missing-keys-degrade-gracefully
# WMBT: wmbt:integration-hardening:C001
# Phase: GREEN
# Layer: application
"""C001-INTEGRATION-002 — When no claude CLI is found and no API keys are set,
register_production_clients() registers nothing, prints the help message to
stderr, and does not raise.

Spec: issue #592 acc:integration-hardening:C001-INTEGRATION-002-missing-keys-degrade-gracefully
"""
from __future__ import annotations

import io
import sys
from unittest.mock import patch


def _fresh_import(module_name: str):
    to_remove = [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]
    for k in to_remove:
        del sys.modules[k]


def test_no_clients_registered_when_no_cli(capsys):
    """When shutil.which returns None, zero production clients are added."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    try:
        with patch("shutil.which", return_value=None):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            registered = register_production_clients()

        assert registered == [], f"Expected no registrations, got {registered}"
        assert len(judge_mod.LLM_REGISTRY) == 0, (
            f"LLM_REGISTRY should be empty, has {sorted(judge_mod.LLM_REGISTRY)}"
        )
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)


def test_help_message_printed_to_stderr_when_no_cli(capsys):
    """The 'no LLM clients available' message is printed to stderr."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    try:
        with patch("shutil.which", return_value=None):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            register_production_clients()

        captured = capsys.readouterr()
        assert "no LLM clients available" in captured.err, (
            f"Expected help message in stderr, got: {captured.err!r}"
        )
        assert "ANTHROPIC_API_KEY" in captured.err or "config.yaml" in captured.err, (
            "Help message should mention ANTHROPIC_API_KEY or config.yaml"
        )
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)


def test_no_exception_when_no_cli():
    """register_production_clients() does not raise when no CLI is available."""
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()

    try:
        with patch("shutil.which", return_value=None):
            _fresh_import("atdd.coach.commands.llm_clients")
            from atdd.coach.commands.llm_clients import register_production_clients
            register_production_clients()  # Must not raise
    finally:
        judge_mod.LLM_REGISTRY.clear()
        judge_mod.LLM_REGISTRY.update(snapshot)
