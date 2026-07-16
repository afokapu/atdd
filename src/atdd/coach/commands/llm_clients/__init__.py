"""Production LLM client auto-registration for `atdd coach issue-review`.

Clients self-register at import time when their backing CLI is available
(shutil.which). Tests patch shutil.which or call register_production_clients()
directly with a patched environment.

The registry itself lives in :mod:`atdd.coach.commands.llm_clients.registry`
(rehomed from the decommissioned `judge.py` in #1486) and is re-exported here so
existing importers of this package keep working.

Public API:
  - register_production_clients(which_fn=shutil.which) -> list[str]
  - LLMClient / LLMUnavailable / LLM_REGISTRY / register_llm_client
"""
from __future__ import annotations

import shutil
import sys
from typing import Callable

from atdd.coach.commands.llm_clients.registry import (
    LLMClient,
    LLMUnavailable,
    LLM_REGISTRY,
    register_llm_client,
)
from atdd.coach.commands.llm_clients._subprocess_shim import ClaudeSubprocessClient

_CLAUDE_MODELS: list[tuple[str, str]] = [
    ("claude-haiku", "claude-haiku-4-5-20251001"),
    ("claude-sonnet-4-6", "claude-sonnet-4-6"),
]


def register_production_clients(
    which_fn: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """Register production LLM clients into :data:`LLM_REGISTRY`.

    Returns the list of newly registered client names.
    Idempotent: re-registration overwrites the previous factory.
    """
    registered: list[str] = []

    claude_bin = which_fn("claude")
    if claude_bin:
        for name, model_id in _CLAUDE_MODELS:
            client = ClaudeSubprocessClient(claude_bin=claude_bin, model_id=model_id)
            register_llm_client(name, lambda c=client: c)
            registered.append(name)

    if not registered:
        print(
            "no LLM clients available — configure ANTHROPIC_API_KEY (or equivalent),"
            " or see .atdd/config.yaml::coach.llm_clients",
            file=sys.stderr,
        )

    return registered


# Auto-register at import time.
register_production_clients()


__all__ = [
    "ClaudeSubprocessClient",
    "LLMClient",
    "LLMUnavailable",
    "LLM_REGISTRY",
    "register_llm_client",
    "register_production_clients",
]
