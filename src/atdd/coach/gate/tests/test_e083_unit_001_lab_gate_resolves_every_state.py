# URN: test:govern-lifecycle:enforce-lab-evidence:E083-UNIT-001-lab-gate-resolves-every-state
# Acceptance: acc:govern-lifecycle:E083-UNIT-001-lab-gate-resolves-every-state
# WMBT: wmbt:govern-lifecycle:E083
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E083-UNIT-001 — the eight states, and why each one is in the table.

``lab_violations(body)`` is the pure half of the gate: given an issue body, every
reason its `## Lab` fails to constitute evidence. Pure on purpose — the store lookup
and the GateCheckResult wrapping live one level up, so the judgement itself is
testable without a repo, a store, or a network.

The five refusing states are not variations on a theme; each was measured, and three
of them are cases the OBVIOUS implementation lets through:

  absent / scaffold intact        the easy two — any implementation catches these
  headings present, bodies empty  a section-presence check passes this
  markers deleted, prose empty    `N/A`, `Not measured yet.` — passes a placeholder
                                  check, which only knows the strings it ships with
  marker + prose on one line      THE decisive one. ``check_placeholders`` fires only
                                  when the placeholder is the whole line (#1904,
                                  correctly — the substring form scored four hits
                                  over 120 issues and zero real). Every hand-written
                                  lab in the corpus is written this way, so three
                                  live bodies that literally say "To fill" all report
                                  ``compliant=True, placeholder_hits=[]``. Both the
                                  ASCII and the unicode-arrow spelling appear in the
                                  wild; both must be caught.

And the three passing states matter as much, because a gate that refuses honest work
is worse than none:

  CONFIRMED / DISPROVED           a negative result is the most valuable outcome and
                                  must never be penalised
  `Nothing.`                      the correct answer to "what it changed" when the
                                  hypothesis held. A length floor was tried and
                                  refused four of six legitimate terse answers, this
                                  one among them — the #1903 lesson, that a check can
                                  punish authors for stating the truth.
"""
from __future__ import annotations

import re

import pytest


def _lab_violations():
    """The pure evaluator, or fail naming the phase that lands it."""
    try:
        from atdd.coach.gate.lab_evidence_check import lab_violations
    except ImportError:  # pragma: no cover - the RED state
        pytest.fail(
            "atdd.coach.gate.lab_evidence_check.lab_violations not implemented yet — "
            "#1950 GREEN. INIT currently exits with no evidence its premise was tested."
        )
    return lab_violations


_SCAFFOLD_BODY = """# An issue

## Lab

### Hypothesis

(the premise this issue rests on, stated so it could be false)

### Setup

(how it was tested against the real system)

### Measured result

_To fill before INIT -> PLANNED._

### What it changed about the plan

_To fill._

## Phases
"""


def _body(hypothesis: str, setup: str, measured: str, changed: str) -> str:
    lab = (
        f"## Lab\n\n### Hypothesis\n\n{hypothesis}\n\n### Setup\n\n{setup}\n\n"
        f"### Measured result\n\n{measured}\n\n"
        f"### What it changed about the plan\n\n{changed}\n"
    )
    return f"# An issue\n\n{lab}\n## Phases\n"


REFUSING = {
    "section absent": "# An issue\n\n## Scope\n\nstuff\n\n## Phases\n",
    "scaffold intact": _SCAFFOLD_BODY,
    "headings present, bodies empty": _body("", "", "", ""),
    "markers deleted, prose empty": _body("N/A", "N/A", "Not measured yet.", "Nothing yet."),
    "marker + prose, ascii arrow": _body(
        "a real hypothesis about the system",
        "a real setup describing what was run",
        "_To fill before INIT -> PLANNED._ Expected: a dangling registry row.",
        "_To fill._ If neither residue is reportable, the validator is the half to land.",
    ),
    "marker + prose, unicode arrow": _body(
        "a real hypothesis about the system",
        "a real setup describing what was run",
        "_To fill before INIT → PLANNED._ Expected: a dangling registry row.",
        "_To fill._ If neither residue is reportable, the validator is the half to land.",
    ),
}

PASSING = {
    "hypothesis CONFIRMED": _body(
        "Guard-clause extraction lowers nesting without tripping the file-length ratchet.",
        "Ten worst offenders; ran the enforce ratchet after each and recorded all four numbers.",
        "nesting 41 -> 12 across ten files; file-length unchanged; cognitive fell 8%.",
        "Nothing.",
    ),
    "hypothesis DISPROVED": _body(
        "The verb-object failures are missing verbs, so the fix is to expand the lexicon.",
        "Read-only measurement over all 229 live artifacts.",
        "92 of 101 failures are noun-leading, not missing verbs. Genuinely missing: 2.",
        "Inverted it. Expanding the lexicon fixes 2 of 101.",
    ),
    "terse result table and terse change": _body(
        "A write failing between the two writes leaves a dangling registry row.",
        "Disposable repo; induce a failure at the second write; reverse order as control.",
        "| real features failing | 89 / 188 (47%) |",
        "Nothing.",
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSING))
def test_unfilled_states_are_refused(name):
    violations = _lab_violations()(REFUSING[name])
    assert violations, f"state {name!r} must be refused, but the gate returned no violation"


@pytest.mark.parametrize("name", sorted(PASSING))
def test_filled_states_pass(name):
    violations = _lab_violations()(PASSING[name])
    assert violations == [], (
        f"state {name!r} must satisfy the gate; got {violations}. A gate that refuses "
        f"an honest negative result, or an honest terse one, is worse than no gate."
    )


def test_each_unfilled_subsection_is_named_so_the_operator_knows_what_to_fix():
    """A refusal that names no reason is the defect class this gate exists inside."""
    violations = _lab_violations()(_SCAFFOLD_BODY)
    joined = " | ".join(violations)
    for name in ("Hypothesis", "Setup", "Measured result", "What it changed about the plan"):
        assert re.search(re.escape(name), joined), (
            f"the refusal must name `### {name}`; got {violations}"
        )
