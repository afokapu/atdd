# Component: component:atdd-plan-core:confirm-gate:ArtifactNaming:backend:application
"""Confirm-gate artifact/contract naming enforcement (#1329).

``planner.artifact-naming.theme-first-identity`` / ``planner.artifact-naming.path-mirrors-identity``:
``atdd plan`` Confirm must not lock a plan whose kept wagon units declare a
produced artifact whose identity is not theme-first (bad grammar or a theme
outside ``get_theme_map``), or whose contract file path does not mirror that
identity. This is the gate body invoked by ``PlanSession.confirm`` *before* it
sets ``locked = True`` — so any failure leaves the session unlocked (atomicity),
mirroring the interlocking-sanity (#1249) and verb-object (#1276) gates.

It uses the pure :mod:`atdd.planner.artifact_naming` mechanic and resolves the
effective theme map from the repo's ``.atdd/config.yaml`` (``load_atdd_config``),
so a consumer/game repo governs against its own declared themes. Only kept
``wagon`` units' ``produce[]`` entries are checked (the artifacts a plan
authors); a produce entry with no ``name`` or a null contract is a no-op for the
respective clause.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from atdd.coach.utils.config import load_atdd_config
from atdd.planner.artifact_naming import (
    is_valid_artifact_identity,
    path_mirrors_identity,
)

__all__ = ["assert_kept_artifact_naming"]


def _produce_naming_failure(entry, wagon: str, config) -> "str | None":
    """The naming complaint for one ``produce[]`` entry, or None when it is sound.

    An entry with no ``name`` names nothing to check; one with a null/absent
    ``contract`` has no path to mirror. A malformed identity short-circuits — it
    cannot meaningfully mirror a path.
    """
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not name:
        return None
    ok, reason = is_valid_artifact_identity(name, config=config)
    if not ok:
        return f"{wagon} produce {name!r} — {reason}"
    contract = entry.get("contract")
    if not (isinstance(contract, str) and contract):
        return None
    ok, reason = path_mirrors_identity(name, contract)
    return None if ok else f"{wagon} produce {name!r} — {reason}"


def assert_kept_artifact_naming(session, root: Path | str = ".") -> None:
    """Raise :class:`SessionGateError` if any kept wagon unit produces an
    artifact whose identity is not theme-first or whose contract path does not
    mirror the identity. No offending produce entries -> returns silently.

    The check reads the *authorable* ``produce[]`` list from each kept wagon's
    ``spec`` — exactly what ``atdd author`` writes into the wagon manifest — and
    is a no-op for an entry that carries no ``name`` (nothing to name-check) or a
    null/absent ``contract`` (nothing to mirror; author-input validation polices
    a structurally-missing produce entry downstream)."""
    from atdd.planner.commands.plan_session import SessionGateError

    config = load_atdd_config(Path(root))
    failures: List[str] = []
    for unit in session.kept_units():
        if unit.get("kind") != "wagon":
            continue
        spec = unit.get("spec") or {}
        wagon = spec.get("wagon") or unit.get("ref", "")
        for entry in spec.get("produce") or []:
            failure = _produce_naming_failure(entry, wagon, config)
            if failure is not None:
                failures.append(failure)

    if failures:
        raise SessionGateError(
            "artifact-naming: cannot lock a plan with mis-named produced "
            f"artifact(s): {failures}"
        )
