"""Test-harness conventions loader (Child 2).

Builds a frozen ``Conventions`` bundle from the canonical phase-machine YAML
(``src/atdd/coach/conventions/phase_machine.convention.yaml``, §4.5) so the
parity test can exercise the Child-1 coach-core pure functions without the real
``atdd.train.persistence.load_conventions`` (which ships in Child 7).

This is a deliberately minimal stand-in: it loads ONLY the phase machine (rules
and prompt templates are empty for the dry-run parity gate). When Child 7 ships
the real loader, the parity test re-points at it; this harness loader goes away.
The function name ``load_conventions`` matches the §4.4 contract on purpose.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

import atdd
from atdd.coach.core.types import Conventions, Persona, Phase, PhaseSpec

PHASE_MACHINE_YAML = (
    Path(atdd.__file__).resolve().parent
    / "coach"
    / "conventions"
    / "phase_machine.convention.yaml"
)


def _persona(value: str | None) -> Persona | None:
    return Persona(value) if value else None


def load_conventions(repo_root: Path | None = None) -> Conventions:
    """Load + freeze the phase machine into a ``Conventions`` snapshot.

    ``repo_root`` is accepted to mirror the §4.4 signature but is unused: the
    canonical YAML is resolved from the installed ``atdd`` package so the loader
    works identically from a worktree or an installed wheel.
    """
    raw = PHASE_MACHINE_YAML.read_text()
    data = yaml.safe_load(raw)

    phase_machine: dict[Phase, PhaseSpec] = {}
    for name, spec in data["phases"].items():
        phase = Phase(name)
        phase_machine[phase] = PhaseSpec(
            name=phase,
            agent=_persona(spec.get("agent")),
            transitions_to=tuple(Phase(p) for p in spec.get("transitions_to", [])),
            pre_commit_gate=spec.get("pre_commit_gate"),
        )

    snapshot_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return Conventions(
        phase_machine=phase_machine,
        rules={},
        prompt_templates={},
        snapshot_hash=snapshot_hash,
        snapshot_paths=(str(PHASE_MACHINE_YAML),),
    )
