# URN: component:govern-lifecycle:enforcement-substrate:test_transport_realizes_mediation:backend:domain
# Runtime: python
# Purpose: Forcing rule (#1268) — a transport/mediation provider must realize the dispatch-verifies-channel-live obligation, or admission refuses it.

"""Binds ``coach.substrate.transport-realizes-mediation`` (strict, #1268 part B).

The substrate ``realizes`` mechanism (part A: ``coach.extension.realization-mapping``)
lets a package declare it satisfies a core node. This rule is the FORCING half: a
workspace provider that declares the decision-mediation / agent-session-transport
(``transport`` or ``orchestration``) capability MUST realize the
``coach.execution.dispatch-verifies-channel-live`` obligation. Without that edge a
transport provider could spawn a worker against a dead mediation channel whose gated
decisions never surface, so admission refuses it.

The check itself is ``compose.validate_transport_realizes_mediation`` (substrate,
reused by admission). This validator pins the negative (refuses) and positive (admits)
behaviour against real transport workspace fixtures.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

import atdd
from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.commands import compose as C

pytestmark = [pytest.mark.coach]

_RULE = bind_rule("coach.substrate.transport-realizes-mediation")

# Transport workspace fixtures live alongside the realization-gate package fixtures,
# resolved package-relatively so the test runs from an installed toolkit too.
_FIX = (
    pathlib.Path(atdd.__file__).resolve().parent
    / "planner" / "commands" / "tests" / "fixtures" / "packages"
)
_UNMEDIATED = _FIX / "acme.workspace.transport-unmediated"
_MEDIATED = _FIX / "acme.workspace.transport-mediated"


def _pkg(package_dir: pathlib.Path) -> dict:
    mp = package_dir / "atdd.workspace.yaml"
    return {
        "kind": "workspace",
        "dir": package_dir,
        "manifest_path": mp,
        "manifest": yaml.safe_load(mp.read_text()),
    }


def _core_ids() -> set[str]:
    return C.installed_core_node_ids()


def test_obligation_is_a_shipped_core_node() -> None:
    """The forcing rule can only bind if the obligation is a shipped core node."""
    assert C.MEDIATION_OBLIGATION_NODE in _core_ids()


def test_transport_capability_without_realizes_is_refused() -> None:
    """NEGATIVE: a transport provider lacking the realizes edge is refused.

    Refusing it enforces BOTH the forcing rule ``coach.substrate.transport-realizes-mediation``
    AND the obligation ``coach.execution.dispatch-verifies-channel-live`` it operationalizes
    (a provider that does not realize the obligation cannot be admitted)."""
    bind_rule("coach.substrate.transport-realizes-mediation")
    bind_rule("coach.execution.dispatch-verifies-channel-live")
    with pytest.raises(C.CompositionError, match="does not realizes"):
        C.validate_transport_realizes_mediation(_pkg(_UNMEDIATED), _core_ids())


def test_transport_capability_with_realizes_is_admitted() -> None:
    """POSITIVE: the same provider WITH the realizes edge onto the obligation passes."""
    # Must not raise.
    C.validate_transport_realizes_mediation(_pkg(_MEDIATED), _core_ids())


def test_non_transport_capability_is_not_forced() -> None:
    """A non-transport (e.g. execution) capability carries no obligation: no-op."""
    manifest = {
        "kind": "workspace",
        "workspace_id": "acme.workspace.exec-only",
        "capabilities": [{"capability_id": "execution.x", "domain": "execution",
                          "type": "command-runner", "contract": "x"}],
    }
    C.validate_transport_realizes_mediation({"manifest": manifest}, _core_ids())


__all__ = [
    "test_transport_capability_without_realizes_is_refused",
    "test_transport_capability_with_realizes_is_admitted",
]
