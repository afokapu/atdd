"""Route bound Violations into the gate, with shadow precedence + fail-safe (E002, M001).

For each convention, decide what gates a lifecycle transition:

- A bound implementation that RAN (provider-spawn succeeded) OWNS the convention's
  gating: its Violations are used and the legacy validator is SHADOWED (suppressed
  for this run, logged). This is how gating migrates out of core (E002).
- A bound implementation that FAILED to run — crash, timeout, or malformed output
  (``SpawnResult.ran is False``) — must NOT be read as "no violations / gate
  passes". The router FALLS BACK to the legacy validator (fail-safe) and logs the
  failure loudly. Never fail-open (M001).
- A convention with no bound implementation is gated by its legacy validator,
  unchanged.

The router is given the legacy validator as a callable so it stays decoupled from
core's gate internals; the CLI/integration layer supplies the real runner.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from atdd.substrate.binding.binder import SpawnResult

# Where a convention's gating Violations came from.
SOURCE_BOUND = "bound"  # a bound impl ran and owns the gate (legacy shadowed)
SOURCE_LEGACY = "legacy"  # no bound impl; legacy gates as usual
SOURCE_LEGACY_FALLBACK = "legacy-fallback"  # bind failed; fell back to legacy (loud)


@dataclass
class GateOutcome:
    """How one convention was gated for a transition."""

    convention_id: str
    source: str
    violations: list[dict] = field(default_factory=list)
    shadowed_legacy: bool = False
    note: str = ""


def route_convention(
    convention_id: str,
    *,
    bound_spawn: SpawnResult | None,
    run_legacy: Callable[[], list[dict]],
    log: Callable[[str], None] | None = None,
) -> GateOutcome:
    """Decide the gate outcome for one convention (shadow / fallback / legacy)."""
    _log = log or (lambda _m: None)

    if bound_spawn is None:
        return GateOutcome(convention_id, SOURCE_LEGACY, list(run_legacy()))

    if bound_spawn.ran:
        _log(
            f"[bind] convention {convention_id!r} gated by bound impl "
            f"{bound_spawn.implementation_id!r}; legacy validator shadowed"
        )
        return GateOutcome(
            convention_id,
            SOURCE_BOUND,
            list(bound_spawn.violations),
            shadowed_legacy=True,
            note=f"bound:{bound_spawn.implementation_id}",
        )

    # M001 — bound impl failed to run; fail-safe to legacy, loudly.
    _log(
        f"[bind][ERROR] convention {convention_id!r} bound impl "
        f"{bound_spawn.implementation_id!r} failed to run "
        f"({bound_spawn.error or 'exit ' + str(bound_spawn.exit_code)}); "
        f"falling back to legacy validator"
    )
    return GateOutcome(
        convention_id,
        SOURCE_LEGACY_FALLBACK,
        list(run_legacy()),
        note=f"fallback:{bound_spawn.error or bound_spawn.exit_code}",
    )
