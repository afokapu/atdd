# URN: component:reconcile-dispositions:reconcile-dispositions:dispositions:backend:domain
# Runtime: python
# Purpose: Name the THREE distinct namespaces all spelled "disposition" as three
#          separate, importable anchors, and carry the single TOTAL treatment ->
#          verdict rule. Pure domain — no I/O, no other-layer imports.
"""The disposition namespace model (#1424 D001).

THREE unrelated things are all spelled ``disposition`` in the enforcement stack.
Before this model they shared no vocabulary, so they got conflated — a
documentation-only node was mistaken for a strict one, and a ``bound`` binding
entry could be read as a treatment. This module names all three separately so
that can never happen again:

1. **TREATMENT** — a convention node's ``metadata.disposition``. It declares how
   a rule's violations are TREATED when computing a verdict. Its vocabulary is
   :data:`TREATMENT_DISPOSITIONS` — ``strict``, ``advisory``,
   ``suppress-and-clean``, ``documentation-only``. This is the ONLY namespace
   that maps to a verdict (see :func:`fails_on_violation`).

2. **WIRING** — a ``binding.lock.yaml`` convention entry's ``disposition``. It is
   a BINDING state, not a treatment: :data:`BOUND_DISPOSITION` (``bound``) marks
   a convention wired to a provider so the runner will enforce it. It shares the
   spelling but NOT the vocabulary of TREATMENT — ``bound`` is deliberately not a
   member of :data:`TREATMENT_DISPOSITIONS`.

3. **GATE** — :data:`DISPOSITION_GATE` (``disposition_gate``) is the NAME of the
   suppression-marker validator that reads inline ``atdd:suppress(<rule>)``
   markers. A name for a validator, not a value any node carries.

Keeping the three apart is what lets a documentation-only node (TREATMENT) stop
being mistaken for a strict one, and a ``bound`` entry (WIRING) stop being read
as a treatment.
"""
from __future__ import annotations

from typing import Final, FrozenSet

# --------------------------------------------------------------------------- #
# Namespace 1: TREATMENT (a node's ``metadata.disposition``)
# --------------------------------------------------------------------------- #
STRICT: Final[str] = "strict"
ADVISORY: Final[str] = "advisory"
SUPPRESS_AND_CLEAN: Final[str] = "suppress-and-clean"
DOCUMENTATION_ONLY: Final[str] = "documentation-only"

#: The complete treatment vocabulary — the ONLY dispositions a convention node's
#: ``metadata.disposition`` may declare (E002 rejects anything outside this set).
TREATMENT_DISPOSITIONS: Final[FrozenSet[str]] = frozenset(
    {STRICT, ADVISORY, SUPPRESS_AND_CLEAN, DOCUMENTATION_ONLY}
)

#: Treatments that never fail a build — advisory and documentation-only nodes are
#: informational; their violations are reported but do not gate the verdict.
_NEVER_FAIL: Final[FrozenSet[str]] = frozenset({ADVISORY, DOCUMENTATION_ONLY})

# --------------------------------------------------------------------------- #
# Namespace 2: WIRING (a ``binding.lock`` entry's ``disposition``)
# --------------------------------------------------------------------------- #
#: The binding-lock value marking a convention married to a provider. NOT a
#: treatment — deliberately absent from :data:`TREATMENT_DISPOSITIONS`.
BOUND_DISPOSITION: Final[str] = "bound"

# --------------------------------------------------------------------------- #
# Namespace 3: GATE (the suppression-marker validator's name)
# --------------------------------------------------------------------------- #
#: The NAME of the inline-suppression gate validator — not a value a node carries.
DISPOSITION_GATE: Final[str] = "disposition_gate"


def is_treatment(disposition: str) -> bool:
    """True iff *disposition* is a member of the treatment vocabulary."""
    return disposition in TREATMENT_DISPOSITIONS


def fails_on_violation(disposition: str) -> bool:
    """TOTAL treatment -> verdict rule (#1424 E001).

    ``strict`` and ``suppress-and-clean`` fail on any violation; ``advisory`` and
    ``documentation-only`` never fail. The rule is total over the vocabulary; an
    unknown treatment fails CLOSED (only the two explicit never-fail treatments
    pass). Callers that must REJECT an unknown treatment validate against
    :data:`TREATMENT_DISPOSITIONS` first (E002) — this function never silently
    passes an out-of-vocabulary node.
    """
    return disposition not in _NEVER_FAIL
