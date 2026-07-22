# URN: component:bind-extension-conventions:implementation-fanout-binding:backend:domain
# Runtime: python
# Purpose: Name the rules a multi-rule detector EMITS and OWNS but does not yet
#          REALIZE — the rules a scalar realizes_convention leaves unbound that
#          declaring the ownership list would bind — while excluding co-emitted
#          rules a detector does not own. Pure domain: manifest inspection only.
"""Implementation fan-out binding (#1426 WMBT E001).

The composer already fans one implementation out to the N conventions it realizes
(#1359), but binds nothing new because the multi-rule detectors declare
``realizes_convention`` as a single scalar string while emitting N rule ids from
one run. Declaring ``realizes_convention`` as the LIST of rule ids a detector OWNS
lets the composer bind them all with zero new detectors.

:func:`under_bound_rules` names the rules that fan-out would bind: the rules a
detector emits and owns but does not yet realize. OWNERSHIP is not CO-EMISSION —
``coder.logging.structured`` emits ``coder.logging.print`` but does not own it (the
dedicated print detector does), so a co-emitted rule is excluded from the
under-bound set and never fanned onto the wrong mechanism.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from atdd.substrate.binding.composer import realized_conventions


def emitted_rule_ids(implementation: Mapping) -> list:
    """The rule ids an implementation emits, as a list (scalar or list manifest)."""
    emits = implementation.get("emits_rule_ids")
    if emits is None:
        return []
    if isinstance(emits, str):
        return [emits]
    return [str(e) for e in emits]


def under_bound_rules(
    implementation: Mapping, *, co_emitted: Iterable[str] = ()
) -> set:
    """Rule ids the implementation OWNS and emits but does not yet REALIZE.

    ``owned = emitted - co_emitted``; ``realized = realizes_convention`` (scalar
    or list). Returns ``owned - realized``: the rules a scalar realizes_convention
    leaves unbound that declaring the ownership list would bind. An empty result
    means the manifest already realizes everything it owns.
    """
    realized = set(realized_conventions(dict(implementation)))
    owned = set(emitted_rule_ids(implementation)) - set(co_emitted)
    return owned - realized
