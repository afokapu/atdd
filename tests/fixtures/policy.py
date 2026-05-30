"""``PolicyHandle`` for the parity harness (Child 2).

The real ``PolicyHandle`` is part of the TrainRunner protocol and physically
lands in ``atdd.train.runner_iface`` in Child 8 (§4.7). Child 2 only needs the
shape — a frozen bundle of (coach_module, conventions) — to drive the dry-run
parity test, so it is defined here in the test harness and imported from
``tests.fixtures``. When Child 8 ships the canonical type, the parity test
re-points its import; nothing in ``src/`` depends on this copy.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from atdd.coach.core.types import Conventions


@dataclass(frozen=True)
class PolicyHandle:
    """Bundles coach-core entry points + frozen Conventions (§4.7)."""

    coach_module: ModuleType
    conventions: Conventions
