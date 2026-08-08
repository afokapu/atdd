"""Which edges the lifecycle declares, and where an issue is actually standing.

``atdd coach approve`` parsed ``FROM->TO``, resolved a signing key, signed and
wrote. It read NO issue state and validated the edge against NOTHING, so
``atdd coach approve 1726 --transition 'BANANA->MOON'`` minted happily, and — the
case that produced #1735 — two tokens were written for ``PLANNED->RED`` and
``SMOKE->REFACTOR`` while #1726 sat at ``INIT`` and had just had all five of its
transitions REFUSED by the template gate. Those tokens were not inert: each would
satisfy ``ApprovalTokenGateCheck`` for its exact ``(issue, from, to)`` tuple the
moment the issue ever reached that edge. An authorisation granted before the work
existed, waiting to be consumed.

This module supplies the two facts the mint needs to refuse:

* :func:`phase_machine` — the declared edges, read from
  ``coach/conventions/phase_machine.convention.yaml``, which is the SINGLE SOURCE
  OF TRUTH and says so in its own header: *add or change a phase HERE, never in
  Python*. It ships inside the package, so it resolves the same way from a
  worktree and from an installed wheel.
* :func:`resolve_issue_phase` — where the issue actually is, through the
  ``external_refs`` GitHub projection, exactly as ``SmokeExecutionGateCheck``
  resolves a work item before deciding anything.

NO HARDCODED FALLBACK PHASE LIST, deliberately. An unreadable convention makes
:func:`phase_machine` RAISE, and the mint refuses naming that. The tempting
alternative — fall back to a literal ``[INIT, PLANNED, RED, ...]`` in Python — is
precisely the second source of truth the convention header forbids, and it would
fail OPEN: the one moment the machine cannot be read is the one moment a
hardcoded copy is most likely to disagree with it.

PRECONDITION, NOT GATE EXECUTION. Running the edge's gates at mint time is #1670's
slice C, which has since landed in :mod:`atdd.coach.gate.mint_gate` and runs after
this module in ``approve_command``. This is the far narrower question that is
logically prior and needs no gate at all: a gate cannot be run for an edge the
issue is not standing on — so it is asked first, and an issue on the wrong edge
never pays for a gate run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

#: The canonical lifecycle state machine. Inside the package (not the repo), so a
#: consumer repo running an installed wheel reads the same declaration this
#: worktree does.
PHASE_MACHINE_PATH = (
    Path(__file__).resolve().parent.parent / "conventions" / "phase_machine.convention.yaml"
)

#: ``external_refs`` coordinates of the GitHub issue projection (#1183).
_GITHUB_PROVIDER = "github"
_ISSUE_REF_KIND = "issue"


class PhaseMachineUnavailable(RuntimeError):
    """The declared lifecycle could not be read, so no edge can be judged legal.

    Raised rather than degraded. A mint that cannot establish which edges exist
    must refuse; substituting a Python copy of the phase list would fork the
    single source of truth at exactly the moment it is unreadable.
    """


def _declared_targets(spec) -> Tuple[str, ...]:
    """One phase's ``transitions_to``, upper-cased; empty for a terminal or malformed one.

    Extracted so :func:`phase_machine` reads as load → validate → map, with the
    per-entry shape-tolerance living here instead of adding branches to the
    caller (``coder.refactor.complexity-cyclomatic``).

    A missing or non-list ``transitions_to`` yields ``()``, which is exactly what
    ``COMPLETE`` and ``OBSOLETE`` legitimately declare — so a malformed entry
    reads as terminal rather than as permissive, and a caller asking "may I go
    from here to X" gets ``no`` rather than an exception.
    """
    targets = spec.get("transitions_to") if isinstance(spec, dict) else None
    if not isinstance(targets, list):
        return ()
    return tuple(str(t).upper() for t in targets if t)


def phase_machine(path: Optional[Path] = None) -> Dict[str, Tuple[str, ...]]:
    """``{PHASE: (reachable, phases, ...)}`` as the convention declares it.

    Raises :class:`PhaseMachineUnavailable` when the file is missing, unparseable,
    or structurally not a phase machine.
    """
    source = Path(path) if path is not None else PHASE_MACHINE_PATH
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PhaseMachineUnavailable(
            f"the phase machine at {source} could not be read: {exc}"
        ) from exc

    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, dict) or not phases:
        raise PhaseMachineUnavailable(
            f"the phase machine at {source} declares no `phases` mapping"
        )
    return {str(name).upper(): _declared_targets(spec) for name, spec in phases.items()}


@dataclass(frozen=True)
class PhaseReading:
    """Where an issue is standing, or a sayable reason it could not be observed.

    Two fields rather than an ``Optional[str]`` because the ways this comes back
    empty need different operator actions — register the issue, record its phase,
    or fix the store — and a bare ``None`` collapses them into one refusal nobody
    can act on. :attr:`reason` is written to be printed verbatim.
    """

    phase: Optional[str] = None
    uid: Optional[str] = None
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.phase)


def _phase_in_store(store, issue_number: int) -> Tuple[Optional[str], Optional[str]]:
    """``(uid, state)`` for ``issue_number``; ``(None, None)`` if it resolves to nothing.

    Extracted from :func:`resolve_issue_phase` rather than inlined so the store
    walk sits at one nesting level instead of three inside a ``try``/``with``
    (``coder.refactor.complexity-nesting``). Same shape and same reason as #1720's
    ``_resolve_branch_in_store``.

    Reads only. What an empty answer MEANS is the caller's to say, because the
    caller is the half that has to make it actionable.
    """
    ref = store.external_refs.resolve(
        _GITHUB_PROVIDER, _ISSUE_REF_KIND, str(int(issue_number))
    )
    if ref is None:
        return None, None
    return ref.object_uid, getattr(store.objects.get(ref.object_uid), "state", None)


def resolve_issue_phase(start: Path, issue_number: int) -> PhaseReading:
    """The lifecycle phase the State Store records for ``issue_number``.

    ``start`` is a STARTING POINT for Control-Root resolution, never the location
    itself — the contract ``approval_paths`` keeps for the token path. Never
    raises: a store fault comes back as a :class:`PhaseReading` carrying a reason,
    so the mint refuses with something to act on rather than a traceback.
    """
    # Imported lazily so the gate package keeps importing without pulling the state
    # layer in — the deferred-import shape SmokeExecutionGateCheck established.
    from atdd.state.smoke_evidence import open_state_store

    try:
        with open_state_store(control_root=Path(start)) as store:
            uid, state = _phase_in_store(store, issue_number)
    except Exception as exc:  # noqa: BLE001 — reported as a reason, never raised
        logger.warning(
            "approval mint: the State Store could not be read for a phase check",
            extra={"issue": issue_number, "start": str(start), "error": str(exc)},
        )
        return PhaseReading(
            reason=(
                f"the State Store under {start} could not be read, so the phase "
                f"#{issue_number} is standing on could not be observed: {exc}"
            )
        )

    if uid is None:
        return PhaseReading(
            reason=(
                f"#{issue_number} resolves to no work item in the State Store, "
                f"so the phase it is standing on cannot be observed"
            )
        )
    if not state:
        return PhaseReading(
            uid=uid,
            reason=(
                f"work item {uid!r} (#{issue_number}) records no phase, so there is "
                f"nothing to check the requested transition against"
            ),
        )
    return PhaseReading(phase=str(state).upper(), uid=uid)


__all__ = [
    "PHASE_MACHINE_PATH",
    "PhaseMachineUnavailable",
    "PhaseReading",
    "phase_machine",
    "resolve_issue_phase",
]
