# URN: test:spawn-agents:atdd-spawn-skeleton-and-harness:E001-UNIT-001-spawn-cli-launches-session-validator
# Acceptance: acc:spawn-agents:E001-UNIT-001-spawn-cli-launches-session
# WMBT: wmbt:spawn-agents:E001
# Phase: RED
# Layer: backend.integration
# Assertion: structural

"""E001-UNIT-001 (validator slice) — structural enforcement that the
``coach.spawn.atdd-spawn-cli`` rule (declared in
``src/atdd/coach/conventions/spawn.convention.yaml``) is bound to a
real spawn entry point in the toolkit.

Mirrors the structural-validator pattern of
``test_d002_unit_001_runtime_layout_doc_committed.py``: assert artifact
presence, key public symbols, and the adapter registry's K1 anchor
(``claude-code``). Behavioral coverage of the launch flow lives in
``src/atdd/coach/commands/tests/test_e001_*`` (the application-layer
tests; this file is the validator-layer mirror that
``coach.spawn.atdd-spawn-cli::validator`` resolves to).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.coach]

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SPAWN_MODULE = ATDD_PKG_DIR / "coach" / "commands" / "spawn.py"


def test_spawn_module_committed() -> None:
    """``src/atdd/coach/commands/spawn.py`` MUST exist — the K1
    deliverable per spec v9 §5.2."""
    assert SPAWN_MODULE.exists(), (
        f"Missing {SPAWN_MODULE}. Acceptance E001-UNIT-001 requires "
        f"spawn.py to be committed at src/atdd/coach/commands/spawn.py."
    )


def test_spawn_module_exposes_required_callables() -> None:
    """``cmd_spawn``, ``main``, ``run``, ``_build_parser`` MUST be public
    on ``atdd.coach.commands.spawn`` — these are the surfaces the K1
    acceptance tests bind to and the CLI dispatch wires through."""
    from atdd.coach.commands import spawn

    for name in ("cmd_spawn", "main", "run", "_build_parser"):
        assert callable(getattr(spawn, name, None)), (
            f"missing callable atdd.coach.commands.spawn.{name}"
        )


def test_spawn_emits_agent_spawned_event_conforming_to_schema() -> None:
    """The ``coach.spawn.atdd-spawn-cli`` rule_id MUST be declared as
    the canonical anchor on the spawn module so observers can correlate
    spawn-time decisions with downstream events. The event-conformance
    behavioral coverage lives in
    ``src/atdd/coach/commands/tests/test_e001_contract_001_agent_spawned_event_conforms.py``."""
    from atdd.coach.commands import spawn

    assert getattr(spawn, "SPAWN_RULE_ID", None) == "coach.spawn.atdd-spawn-cli", (
        "spawn.SPAWN_RULE_ID must be 'coach.spawn.atdd-spawn-cli' — the "
        "canonical anchor declared in spawn.convention.yaml."
    )


def test_spawn_adapter_registry_ships_claude_code() -> None:
    """K1 ships the ``claude-code`` adapter; codex / gemini / glm land
    in K-track follow-ups by registering on the same registry without
    editing the spawn module's CLI surface."""
    from atdd.coach.commands import spawn

    assert isinstance(spawn.ADAPTER_REGISTRY, dict)
    assert "claude-code" in spawn.ADAPTER_REGISTRY, (
        "ADAPTER_REGISTRY must register 'claude-code' as the K1 adapter."
    )
    assert callable(spawn.ADAPTER_REGISTRY["claude-code"])
