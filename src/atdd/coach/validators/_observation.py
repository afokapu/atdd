# URN: component:govern-lifecycle:enforcement-substrate:observation:backend:domain
# Runtime: python
# Purpose: Separate "I could not look" from "there was nothing to look at" for validators that resolve remote objects (#1747/#1748).

"""Did the validator actually observe the thing it is judging? (#1747 / #1748)

A validator that resolves a remote object — a PR, its linked issue, that issue's
phase label — gets ``None`` back for two completely different reasons, and
:func:`atdd.coach.commands.pr.PRManager.resolve_linked_issue` returns the same
``None`` for both:

* the object could not be READ (the PR fetch failed, the linked issue could not
  be retrieved, the phase label is missing from an issue that must carry one), or
* there was nothing to read (the PR declares no auto-closing reference, so the
  rule is owed nothing here).

Reading the first as the second is the #1747 defect measured on PR ``#1757``: on
head sha ``54bdad8af`` the ``push`` run at 12:58:31Z reported **success** and the
``pull_request`` run at 13:08:46Z — two seconds after the PR came into existence —
reported **failure**, from identical repository state. The pass was vacuous. A
gate guarding the 2026-05-13 substrate-asymmetry incident (``#681``) had said
"green" on an observation it never made.

#1719 already built the vocabulary for this in :mod:`atdd.coach.gate.decision`;
this module is the adapter that lets a *pytest-shaped* validator speak it. The
three-way split is deliberately narrower than the four-verdict one: a validator
first asks "did I observe?" and only then asks "does the rule hold?".

    OBSERVED        -> the rule now decides:      GateVerdict.PASS / FAIL
    UNREADABLE      -> GateVerdict.COULD_NOT_CHECK  (REFUSES — fail closed)
    NO_OBLIGATION   -> GateVerdict.NOT_APPLICABLE   (proceeds)

HOLD ``NO_OBLIGATION`` PRECISELY. It is the member that re-collapses the
distinction if it is allowed to drift, and the #1747 brief says so in as many
words: "the link could not be READ" is not "the issue has no PR". A branch whose
PR does not exist yet owes this gate nothing and must keep merging; a PR that
declares ``Closes #N`` whose ``#N`` cannot be read must block. Widening
``UNREADABLE`` to cover the first would trade a false pass for a repo nobody can
merge in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from atdd.coach.gate.decision import GateVerdict

#: Prefix every ``COULD_NOT_CHECK`` detail string carries, so the refusal is
#: distinguishable at a glance from a rule violation in the same punch list.
#: The disposition gate speaks ``Violation`` records only — it has no verdict
#: field — so the verdict is carried in the text the operator actually reads.
#: Their next actions differ completely ("your PR is unmergeable" versus "I
#: could not look at your PR"), which is the whole reason #1719 split them.
COULD_NOT_CHECK_PREFIX = "COULD_NOT_CHECK:"


class Observation(str, Enum):
    """Whether the validator managed to look, before any question of the rule."""

    OBSERVED = "observed"
    UNREADABLE = "unreadable"
    NO_OBLIGATION = "no_obligation"

    def to_verdict(self) -> Optional[GateVerdict]:
        """The #1719 verdict this observation forces, or None if the rule decides.

        ``OBSERVED`` returns ``None`` on purpose rather than ``PASS``: the
        observation succeeded, so the verdict is the *rule's* to give, and
        answering ``PASS`` here would be the exact substitution — an unmade
        judgement wearing a made one's clothes — that #1747 is about.
        """
        return _OBSERVATION_VERDICTS.get(self)


_OBSERVATION_VERDICTS = {
    Observation.UNREADABLE: GateVerdict.COULD_NOT_CHECK,
    Observation.NO_OBLIGATION: GateVerdict.NOT_APPLICABLE,
}


@dataclass(frozen=True)
class Reading:
    """One resolution attempt: what came back, and — when nothing did — why.

    ``subject`` names what was being looked at (a PR number, an issue number) and
    is kept on every reading, including the ones that resolved nothing: a refusal
    has to be attributable to something, or the caller cannot route it. ``reason``
    is written to be printed verbatim — a refusal an operator cannot act on is
    only marginally better than the vacuous pass it replaces, so
    :meth:`unreadable` requires one.
    """

    observation: Observation
    subject: Optional[Any] = None
    payload: Optional[Any] = None
    reason: Optional[str] = None

    @property
    def verdict(self) -> Optional[GateVerdict]:
        """The forced #1719 verdict, or None when the rule still has to decide."""
        return self.observation.to_verdict()

    @property
    def blocks(self) -> bool:
        """Whether this reading alone refuses, without consulting the rule."""
        verdict = self.verdict
        return bool(verdict and verdict.blocks)

    @classmethod
    def observed(cls, payload: Any, subject: Optional[Any] = None) -> "Reading":
        """The lookup succeeded; ``payload`` is what it returned."""
        return cls(Observation.OBSERVED, subject=subject, payload=payload)

    @classmethod
    def unreadable(cls, reason: str, subject: Optional[Any] = None) -> "Reading":
        """The observation could not be made — say what, and what would fix it."""
        return cls(Observation.UNREADABLE, subject=subject, reason=reason)

    @classmethod
    def no_obligation(cls, reason: str, subject: Optional[Any] = None) -> "Reading":
        """The lookup succeeded and the rule is owed nothing here."""
        return cls(Observation.NO_OBLIGATION, subject=subject, reason=reason)


__all__ = [
    "COULD_NOT_CHECK_PREFIX",
    "Observation",
    "Reading",
]
