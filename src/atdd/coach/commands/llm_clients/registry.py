"""Generic LLM client plumbing — the pluggable client registry and protocol.

Rehomed from `atdd.coach.commands.judge` (#1486). `judge.py` mixed this generic
plumbing with the `atdd judge` CLI + call-site machinery; the orchestration half
was decommissioned with the coach's sub-worker verbs, so the plumbing lives here,
alongside the production clients that register into it.

Consumers:
- `llm_clients/__init__.py`     — registers the production clients at import time.
- `llm_clients/_subprocess_shim` — raises :class:`LLMUnavailable`.
- `commands/issue_review.py`     — reads :data:`LLM_REGISTRY` for its `--llms` option.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol


class LLMUnavailable(Exception):
    """Raised by an LLM client when the model is unreachable.

    Callers catch this and route to their own fail-open policy.
    """


class LLMClient(Protocol):
    """An LLM client invoked once per call.

    Implementations may return any JSON-serializable Python value
    (dict / list / str / number / bool / None). The caller validates the
    return against its JSON Schema.
    """

    def invoke(self, prompt: str) -> Any: ...  # pragma: no cover - protocol


LLM_REGISTRY: dict[str, Callable[[], LLMClient]] = {}


def register_llm_client(name: str, factory: Callable[[], LLMClient]) -> None:
    """Register an LLM client factory under `name`.

    The factory is called once per invocation. Tests register stubs here;
    production clients register real clients at import time.
    """
    LLM_REGISTRY[name] = factory


__all__ = [
    "LLMClient",
    "LLMUnavailable",
    "LLM_REGISTRY",
    "register_llm_client",
]
