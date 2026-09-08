# URN: component:govern-lifecycle:enforcement-substrate:validation_coverage:backend:domain
# Runtime: python
# Purpose: Record and report how much of a validator suite an `atdd validate` run did not evaluate.

"""How much of itself a validator run did not evaluate (C014, #1632).

``atdd validate <phase>`` selects its validators with a pytest marker expression
and reports only what it ran. Measured 2026-08-03 on this repo:

    atdd validate planner --local --skip-api   ->  "237 passed"
    the identical selection, run serially      ->  "237 passed, 208 deselected"

The count is not merely under-advertised. Under the parallelism the runner uses by
default it is **gone**: pytest-xdist collects in the workers, so ``pytest_deselected``
fires there and the controller's terminal reporter — the thing that prints the
summary — never receives it. A fix that surfaced "whatever pytest said" would
surface nothing, so the runner has to obtain the number itself.

Across all four phases, 812 of 1898 validators are removed and no output mentions
it. That is #1670's premise inside the validator suite #1670 would mint a receipt
against: *a run that evaluated 0 of N must not return the verdict of one that
evaluated N and found nothing.*

VOCABULARY. ``could_not_check`` is deliberate, and matches
``atdd.coach.gate.decision.GateVerdict.COULD_NOT_CHECK`` (C013/#1719) — the same
fact on the transition-gate surface, so the two read alike. It is NOT spelled
``skipped``: pytest already uses that word for a different outcome, and reports
it. Collapsing them would hide the answer that has no other surface behind the one
that already has.

SCOPE. This module reports; it does not decide. A deselection does not fail the
run — every consumer repo excludes ``platform`` by design, so blocking on it would
break ``atdd validate`` everywhere for a change whose whole point is that the
number should be visible. Making a caller *refuse* on a non-zero count is #1670's
conditional mint, and it needs this number to exist first.

PURITY. Stdlib only, and no subprocess: the probe that runs pytest lives in
``atdd.coach.commands.test_runner``, which is impure by nature. Keeping the record,
the rendering and the parser here is what lets them be tested without a pytest
session — the same split ``decision.py`` holds against ``command_check.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

#: The word for "this was not evaluated", shared with the gate verdict of the same
#: name. Named once so a caller cannot spell it differently by hand.
COULD_NOT_CHECK = "could_not_check"


@dataclass(frozen=True)
class MarkerExclusion:
    """One marker expression a run applied, and why it applied it.

    The reason is not decoration. A bare count tells an operator that something
    went unobserved; it does not tell them which population, or whether the cause
    is a flag they passed or an environment detection they did not know had fired.
    In this repo it is nearly always the latter — ``not platform`` is injected when
    ``is_atdd_source_repo()`` is False, which it is under the installed CLI even in
    the toolkit's own checkout.
    """

    expression: str
    reason: str


@dataclass(frozen=True)
class CoverageReport:
    """What one ``atdd validate`` run evaluated, and what it did not.

    ``could_not_check`` counts validators the marker expression removed before
    execution. It is a count of observations *not made* — never of observations
    that succeeded, and never of pytest ``skipped`` results, which pytest reports
    on its own.
    """

    phase: str
    selected: int
    could_not_check: int
    exclusions: Tuple[MarkerExclusion, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Refuse a contradictory record rather than render one. Same
        # refusal-to-guess as C013's verdict/bool conflict: a coverage number
        # nobody can trust is worse than none, because it reads as measurement.
        if self.selected < 0:
            raise ValueError(f"selected must be >= 0, got {self.selected}")
        if self.could_not_check < 0:
            raise ValueError(
                f"could_not_check must be >= 0, got {self.could_not_check}"
            )

    @property
    def total(self) -> int:
        """Every validator the run's paths collected, evaluated or not."""
        return self.selected + self.could_not_check

    @property
    def complete(self) -> bool:
        """Whether the run evaluated everything it collected."""
        return self.could_not_check == 0


# --------------------------------------------------------------------------- #
# Reading pytest's own counts                                                 #
# --------------------------------------------------------------------------- #

# `pytest -q --collect-only` tails with one of:
#     "237/445 tests collected (208 deselected) in 3.42s"
#     "445 tests collected in 3.22s"
#     "1 test collected in 0.40s"
_DESELECTING = re.compile(
    r"(\d+)/(\d+)\s+tests?\s+collected\s*\((?:[^)]*?\b(\d+)\s+deselected)"
)
_PLAIN = re.compile(r"(?<![/\d])(\d+)\s+tests?\s+collected(?!\s*\()")


def parse_collected_counts(text: str) -> Optional[Tuple[int, int]]:
    """Return ``(selected, deselected)`` from pytest collection output.

    Returns ``None`` when the counts are not present — an unreadable probe is an
    unknown, and this module's entire subject is that an unknown must not be
    reported as a zero. Callers render "coverage unknown", not "nothing was
    deselected".
    """
    if not text or not isinstance(text, str):
        return None

    match = _DESELECTING.search(text)
    if match:
        return int(match.group(1)), int(match.group(3))

    match = _PLAIN.search(text)
    if match:
        return int(match.group(1)), 0

    return None


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #

_PREFIX = "[validation coverage]"


def render_coverage_report(report: CoverageReport) -> str:
    """Render *report* for an operator reading a terminal.

    A complete run renders too. "0 could_not_check" is a different claim from
    silence, and silence is the state this module exists to remove — the absence of
    a warning has to be evidence rather than the default.
    """
    lines = [
        f"{_PREFIX} {report.phase}: "
        f"{report.selected} of {report.total} validators evaluated; "
        f"{report.could_not_check} {COULD_NOT_CHECK}"
    ]

    if not report.complete:
        lines.append(
            f"  {COULD_NOT_CHECK} means this run did not evaluate them. "
            f"It is not a pass, and it is not a pytest skip."
        )
        for exclusion in report.exclusions:
            lines.append(f"    -m '{exclusion.expression}' — {exclusion.reason}")

    return "\n".join(lines)


def render_unknown_coverage(phase: str, detail: str) -> str:
    """Render the case where coverage itself could not be determined.

    The probe can fail — a collection error, a timeout, output this module cannot
    read. Saying so is the point: an unmeasured run reporting "0 not evaluated"
    would be the defect wearing the fix's clothes.
    """
    return (
        f"{_PREFIX} {phase}: coverage could not be determined ({detail}). "
        f"The number of validators this run did not evaluate is unknown."
    )


def coverage_reasons(expressions: Sequence[str], *, consumer_mode_reason: str) -> Tuple[MarkerExclusion, ...]:
    """Attach a reason to each marker expression a run applied.

    Known expressions get the cause the runner actually had; anything else gets an
    honest generic rather than a guess.
    """
    known = {
        "not platform": consumer_mode_reason,
        "not github_api": (
            "--skip-api was passed, so the GitHub-API-bound validators were not run"
        ),
        "github_api": (
            "--api-only was passed, so only the GitHub-API-bound validators were run"
        ),
    }
    return tuple(
        MarkerExclusion(expr, known.get(expr, "applied by the caller"))
        for expr in expressions
    )
