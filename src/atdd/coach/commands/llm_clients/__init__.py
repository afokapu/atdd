"""Production LLM client auto-registration for atdd judge / atdd issue review.

Clients self-register at import time when their backing CLI is available
(shutil.which). Tests patch shutil.which or call register_production_clients()
directly with a patched environment.

Public API:
  - register_production_clients(which_fn=shutil.which) -> list[str]
"""
from __future__ import annotations

import shutil
import sys
from typing import Callable

from atdd.coach.commands import judge as _judge_mod
from atdd.coach.commands.llm_clients._subprocess_shim import ClaudeSubprocessClient

_CLAUDE_MODELS: list[tuple[str, str]] = [
    ("claude-haiku", "claude-haiku-4-5-20251001"),
    ("claude-sonnet-4-6", "claude-sonnet-4-6"),
]


def register_production_clients(
    which_fn: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """Register production LLM clients into judge.LLM_REGISTRY.

    Returns the list of newly registered client names.
    Idempotent: re-registration overwrites the previous factory.
    """
    registered: list[str] = []

    claude_bin = which_fn("claude")
    if claude_bin:
        for name, model_id in _CLAUDE_MODELS:
            client = ClaudeSubprocessClient(claude_bin=claude_bin, model_id=model_id)
            _judge_mod.register_llm_client(name, lambda c=client: c)
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
