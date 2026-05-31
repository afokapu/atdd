"""
Asserts the INIT phase's pre-commit gate is registered in the canonical
phase-machine convention with the expected validate-planner command.

Background (#925 — split from #919 Section B preparation): the prior
template-content-reader tests in
``test_e015_unit_002_atdd_md_init_phase_instructs_pre_commit_validate_planner.py``
asserted against the ``atdd_cycle.phases[INIT]`` block in CONDUCTOR.md.
That block duplicated convention content the Coach Decomposition (#887,
#888) has been removing — the canonical home is
``src/atdd/coach/conventions/phase_machine.convention.yaml`` (per §4.5).

This test asserts the same semantic — INIT has a pre-commit gate that
runs the planner validator before committing PLANNED — by reading the
convention YAML directly.

The "before committing PLANNED" timing semantic the original test
asserted as a prose string is **encoded by the field name itself** —
``pre_commit_gate`` names the timing. We assert the field exists and
carries the command; no prose-content check needed.

Convention: ``src/atdd/coach/conventions/phase_machine.convention.yaml``
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

_CONVENTION_FILENAME = "phase_machine.convention.yaml"
_EXPECTED_COMMAND_SUBSTRINGS = (
    "atdd validate planner",  # the command name; flags may evolve
)


def _load_convention(conv_path: Path) -> dict[str, Any]:
    assert conv_path.exists(), f"Convention not found: {conv_path}"
    return yaml.safe_load(conv_path.read_text())


def _init_phase(convention: dict[str, Any]) -> dict[str, Any]:
    phases = convention.get("phases")
    assert isinstance(phases, dict), (
        "phase_machine.convention.yaml must declare top-level 'phases:' mapping "
        f"(got {type(phases).__name__})"
    )
    init = phases.get("INIT")
    assert isinstance(init, dict), (
        "phase_machine.convention.yaml must declare an INIT phase "
        f"(found phases: {sorted(phases)})"
    )
    return init


def test_phase_machine_init_has_pre_commit_gate_field() -> None:
    """INIT phase declares a ``pre_commit_gate`` field (any non-empty string)."""
    conv_path = (
        Path(__file__).parent.parent  # src/atdd/coach
        / "conventions"
        / _CONVENTION_FILENAME
    )
    init = _init_phase(_load_convention(conv_path))
    gate = init.get("pre_commit_gate")
    assert isinstance(gate, str) and gate.strip(), (
        f"INIT.pre_commit_gate must be a non-empty string; got {gate!r}. "
        "The field encodes the 'run before committing PLANNED' timing semantic — "
        "without it, agents have no canonical instruction to pre-validate."
    )


def test_phase_machine_init_pre_commit_gate_invokes_validate_planner() -> None:
    """INIT.pre_commit_gate runs the planner validator (command name pinned)."""
    conv_path = (
        Path(__file__).parent.parent  # src/atdd/coach
        / "conventions"
        / _CONVENTION_FILENAME
    )
    init = _init_phase(_load_convention(conv_path))
    gate = init["pre_commit_gate"]
    for needle in _EXPECTED_COMMAND_SUBSTRINGS:
        assert needle in gate, (
            f"INIT.pre_commit_gate must invoke {needle!r}; got {gate!r}. "
            "The command name is the stable semantic — its CLI flags may evolve "
            "(e.g. '--local --skip-api' could become '--ci-mode'), but the "
            "underlying validator invocation is the contract."
        )


def test_installed_phase_machine_convention_ships_init_pre_commit_gate() -> None:
    """SMOKE: the rule ships in the installed-package convention YAML.

    Replaces the prior ``test_installed_atdd_md_has_rule_id`` /
    template-reader smoke (the rule-id half was moved in #921; this
    half moves the pre-commit-gate semantic).
    """
    conventions_module = importlib.import_module("atdd.coach.conventions")
    # Namespace package — resolve dir via __path__ (per #921 fix).
    conv_dir = Path(next(iter(conventions_module.__path__)))
    conv_path = conv_dir / _CONVENTION_FILENAME
    init = _init_phase(_load_convention(conv_path))
    gate = init.get("pre_commit_gate", "")
    assert "atdd validate planner" in gate, (
        f"Installed package convention {conv_path} INIT.pre_commit_gate does not "
        f"invoke 'atdd validate planner'; got {gate!r}. "
        "The fix did not ship into the installed distribution."
    )
