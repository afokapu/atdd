"""Does THIS issue owe a live-smoke run? (#1602 — the gate's opt-in question.)

:class:`~atdd.coach.gate.smoke_execution_check.SmokeExecutionGateCheck` is
fail-closed: no attestation, no ``SMOKE->REFACTOR``. That is correct for an issue
that is *supposed* to smoke and wrong for every other issue in the repo, and the
difference is the whole reason this module exists. Without it, turning the gate on
would demand a live-smoke attestation from issues whose plan declares no
``execution_kind: live_smoke`` acceptance at all — an obligation they cannot
discharge, whose only exit is ``--force``. A gate reachable only by forcing past it
is a rubber stamp, which is the failure mode E069 names and #1602 exists to remove.

So the gate is OPT-IN, and this module answers the opt-in question:

    given an issue, which ``execution_kind: live_smoke`` acceptances does *its own
    plan scope* declare?

None → the gate is not applicable to that issue and passes. One or more → the
fail-closed logic applies in full, and the refusal can name the acceptances that
are owed.

WHY IT IS PER-ISSUE, AND WHY THAT MATTERS MORE THAN IT LOOKS. There is already a
repo-level answer to a similar-sounding question —
:func:`atdd.tester.substrate.smoke_attestation.plan_declares_live_smoke` — and it
is the wrong tool here by construction. It asks "does the REPO declare any
live_smoke acceptance", which became ``True`` for this repo the moment E069
landed. Wiring the opt-in to it would re-gate every issue in the repo on the very
commit that made the gate satisfiable: the trap, restored, one indirection deeper.
That function stays where it is, answering the question it is right for (should
the pytest hook bother walking ``plan/`` this session), and this module never
calls it.

HOW AN ISSUE MAPS TO AN OBLIGATION. The State Store work item is the issue's
identity locally (the gate has already resolved issue number → uid through the
``external_refs`` projection), and its ``data`` bag carries the issue's declared
plan scope. Two keys are consulted, both written by the ordinary authoring path:

* ``data.feature`` — a feature URN. ``plan/<wagon>/features/<slug>.yaml`` lists the
  WMBTs the feature is made of; each WMBT file carries the ``acceptances[]`` those
  WMBTs are discharged by. Any of them declaring ``execution_kind: live_smoke`` is
  an obligation on every issue bound to that feature.
* ``data.train`` — a train id. Train files carry ``acceptances[]`` of their own
  (which is why :func:`~atdd.tester.validators._acceptance_walker.iter_repo_acceptances`
  walks them), so a live_smoke acceptance declared there binds the train's issues.

An issue whose work item names neither — the common case, and the shape of every
work item in this repo today — declares no plan scope, therefore no live_smoke
acceptance, therefore owes nothing. It passes as *not applicable*, which is the
safety property that makes enabling the gate a non-event for issues that never
promised to smoke.

RESOLUTION IS BY IDENTITY, NOT BY SEARCH. A feature/WMBT URN's on-disk home is
derived from the URN itself (``feature:<wagon>:<slug>`` →
``plan/<wagon>/features/<slug>.yaml``, ``wmbt:<wagon>:<ID>`` →
``plan/<wagon>/<ID>.yaml``, with ``-`` → ``_`` on directory and file names), the
layout ``atdd plan`` authors into and every plan artifact in this repo obeys. A
URN that resolves to no file contributes no obligation and says so in the debug
log rather than failing the transition: "this issue declares nothing I can see" is
the not-applicable answer, and turning an unresolvable reference into a blocked
lifecycle would re-create the trap for a *typo*. The fail-closed teeth bite inside
a declared obligation — once an acceptance is found, only a real run satisfies it.

KNOWN, DELIBERATE GAP (do not close it here). Opt-in means an issue can avoid the
gate by declaring no live_smoke acceptance. Deciding which issues are REQUIRED to
declare one — a planner-side obligation, not a coach-side one — is a separate
concern and is not built here.

Dependency discipline: stdlib + ``yaml`` + ``atdd.coach.utils`` only. In
particular this module does NOT import ``atdd.tester`` (see above).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from atdd.coach.utils.plan_paths import TRAINS_DIRNAME, train_home

logger = logging.getLogger(__name__)

#: The ``execution_kind`` that means "this acceptance is discharged by a test that
#: runs against real infrastructure". Restated here rather than imported from
#: ``atdd.tester.substrate.smoke_attestation`` to keep coach off tester; the
#: literal is pinned to that module by
#: ``test_live_smoke_kind_matches_the_attestation_writer``.
LIVE_SMOKE_KIND = "live_smoke"

#: Work-item ``data`` keys naming the issue's plan scope, in the order the
#: obligation is accumulated. Same keys ``WorkItemReader.feature`` / ``.train``
#: read, so this consults the binding the authoring path already writes.
FEATURE_KEY = "feature"
TRAIN_KEY = "train"

_PLAN_DIRNAME = "plan"
_FEATURES_DIRNAME = "features"


@dataclass(frozen=True)
class SmokeObligation:
    """What one issue owes the smoke-execution gate, and where that came from.

    ``acceptance_urns`` empty means *not applicable*: nothing in the issue's plan
    scope asks for a live-smoke run. ``scopes`` records what was consulted so a
    verdict can explain itself — "no obligation" reads very differently when the
    issue declared no plan scope at all than when it declared one that asks for no
    live smoke, and an operator needs to tell those apart.
    """

    acceptance_urns: Tuple[str, ...] = ()
    scopes: Tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.acceptance_urns)

    def describe_scope(self) -> str:
        """Human phrase for what the issue's plan scope was resolved from."""
        if not self.scopes:
            return "its work item declares no plan scope (no feature, no train)"
        return "its plan scope is " + ", ".join(self.scopes)


def live_smoke_obligation(
    repo_root: Path, work_item_data: Optional[Mapping[str, Any]]
) -> SmokeObligation:
    """The live_smoke acceptances *this* issue's plan scope declares.

    ``work_item_data`` is the store work item's ``data`` bag — the issue's end of
    the mapping. ``repo_root`` is the worktree whose ``plan/`` is authoritative for
    the transition being decided (the gate hands it its own ``ctx.worktree``, so a
    branch that adds an acceptance is judged against the branch, not against main).
    """
    data = work_item_data or {}
    plan_dir = Path(repo_root) / _PLAN_DIRNAME

    scopes: List[str] = []
    urns: List[str] = []

    feature_urn = _as_urn(data.get(FEATURE_KEY))
    if feature_urn:
        scopes.append(feature_urn)
        urns.extend(_feature_live_smoke_urns(plan_dir, feature_urn))

    train_id = _as_urn(data.get(TRAIN_KEY))
    if train_id:
        scopes.append(train_id)
        urns.extend(
            _live_smoke_urns_in(_load_yaml(train_home(plan_dir / TRAINS_DIRNAME, train_id)))
        )

    return SmokeObligation(
        acceptance_urns=tuple(sorted(dict.fromkeys(urns))), scopes=tuple(scopes)
    )


# --------------------------------------------------------------------------- #
# Plan traversal                                                               #
# --------------------------------------------------------------------------- #
def _feature_live_smoke_urns(plan_dir: Path, feature_urn: str) -> List[str]:
    """live_smoke acceptance URNs reachable from one feature, through its WMBTs."""
    feature = _load_yaml(_feature_home(plan_dir, feature_urn))
    if feature is None:
        logger.debug(
            "smoke obligation: feature URN resolves to no plan file; nothing owed from it",
            extra={"feature": feature_urn, "plan_dir": str(plan_dir)},
        )
        return []

    urns: List[str] = []
    for entry in feature.get("wmbts") or []:
        wmbt_urn = _as_urn(entry)
        if not wmbt_urn:
            continue
        urns.extend(_live_smoke_urns_in(_load_yaml(_wmbt_home(plan_dir, wmbt_urn))))
    return urns


def _live_smoke_urns_in(document: Optional[Dict[str, Any]]) -> List[str]:
    """Every ``execution_kind: live_smoke`` acceptance URN in one plan document.

    Reads the same ``acceptances[]`` block WMBT and train files share, so a train
    acceptance and a WMBT acceptance are found by identical means.
    """
    if not document:
        return []
    urns: List[str] = []
    for acceptance in document.get("acceptances") or []:
        if not isinstance(acceptance, dict):
            continue
        if acceptance.get("execution_kind") != LIVE_SMOKE_KIND:
            continue
        identity = acceptance.get("identity")
        urn = identity.get("urn") if isinstance(identity, dict) else None
        if isinstance(urn, str) and urn:
            urns.append(urn)
    return urns


def _feature_home(plan_dir: Path, feature_urn: str) -> Optional[Path]:
    """``feature:<wagon>:<slug>`` -> ``plan/<wagon>/features/<slug>.yaml``."""
    parts = _typed_parts(feature_urn, "feature")
    if parts is None:
        return None
    wagon, slug = parts
    return plan_dir / _snake(wagon) / _FEATURES_DIRNAME / f"{_snake(slug)}.yaml"


def _wmbt_home(plan_dir: Path, wmbt_urn: str) -> Optional[Path]:
    """``wmbt:<wagon>:<ID>`` -> ``plan/<wagon>/<ID>.yaml``."""
    parts = _typed_parts(wmbt_urn, "wmbt")
    if parts is None:
        return None
    wagon, wmbt_id = parts
    return plan_dir / _snake(wagon) / f"{wmbt_id}.yaml"


def _typed_parts(urn: str, expected_kind: str) -> Optional[Tuple[str, str]]:
    """``(scope, name)`` for ``<kind>:<scope>:<name>``, or ``None`` if it is not one."""
    parts = urn.split(":")
    if len(parts) != 3 or parts[0] != expected_kind or not all(parts):
        return None
    return parts[1], parts[2]


def _snake(segment: str) -> str:
    """URN segments are kebab-case; their directories and files are snake_case."""
    return segment.replace("-", "_")


def _as_urn(value: Any) -> Optional[str]:
    """A non-empty URN string from a scalar or a ``{urn: ...}`` mapping, else None.

    Plan lists are written both ways (``wmbts: ["wmbt:a:E001"]`` and
    ``wmbts: [{urn: "wmbt:a:E001"}]``), and a work item's ``data`` bag carries the
    scalar form. Accepting both here keeps one caller shape.
    """
    if isinstance(value, Mapping):
        value = value.get("urn")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _load_yaml(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Parse a plan file, or ``None`` when it is absent/unreadable/not a mapping.

    Unreadable is treated as absent on purpose: an obligation this module cannot
    see is an obligation it must not invent, and a YAML error is a planner-side
    fault that the planner validators fail on — not a reason to freeze a
    lifecycle transition here.
    """
    if path is None or not path.is_file():
        return None
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        logger.warning(
            "smoke obligation: unreadable plan file; it contributes no obligation",
            extra={"path": str(path), "error": str(exc).splitlines()[0][:160]},
        )
        return None
    return document if isinstance(document, dict) else None


__all__ = [
    "FEATURE_KEY",
    "LIVE_SMOKE_KIND",
    "SmokeObligation",
    "TRAIN_KEY",
    "live_smoke_obligation",
]
