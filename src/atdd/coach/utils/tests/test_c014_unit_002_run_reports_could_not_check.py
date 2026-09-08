# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C014-UNIT-002-a-run-counts-and-reports-what-it-did-not-check
# Acceptance: acc:govern-lifecycle:C014-UNIT-002-a-run-counts-and-reports-what-it-did-not-check
# WMBT: wmbt:govern-lifecycle:C014
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C014-UNIT-002 — a validate run counts and reports what it did not check.

``atdd validate planner --local --skip-api`` prints ``237 passed``. The identical
selection run without xdist prints ``237 passed, 208 deselected``. The count is
not merely under-advertised — under the parallelism the runner uses by default it
is *gone*, because deselection happens during worker collection and the xdist
controller never receives ``pytest_deselected``. So the run cannot surface a
number pytest did not give it, and the runner has to obtain and report the count
itself.

This file covers the pure half of that: the record, its rendering, and the parser
that reads pytest's own collection output. No subprocess, no pytest session — the
impure probe that feeds it is C014-SMOKE-001's subject.

The vocabulary is ``could_not_check``, matching ``GateVerdict.COULD_NOT_CHECK``
(C013/#1719) on the transition-gate surface. It is deliberately not ``skipped``:
pytest already uses that word for a different outcome, and reports it.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.validation_coverage import (
    COULD_NOT_CHECK,
    CoverageReport,
    MarkerExclusion,
    parse_collected_counts,
    render_coverage_report,
)


# --------------------------------------------------------------------------- #
# The record states the fraction, not just the remainder                       #
# --------------------------------------------------------------------------- #


def test_report_states_the_could_not_check_count_the_selected_count_and_the_total():
    """A reader must see the fraction, not have to infer it from one number."""
    report = CoverageReport(
        phase="planner",
        selected=237,
        could_not_check=208,
        exclusions=(MarkerExclusion("not platform", "consumer-mode detection"),),
    )

    assert report.could_not_check == 208
    assert report.selected == 237
    assert report.total == 445

    rendered = render_coverage_report(report)
    assert "237" in rendered
    assert "445" in rendered
    assert "208" in rendered


def test_report_names_every_exclusion_and_the_reason_it_was_applied():
    """A bare count is not actionable — the operator needs the population and why."""
    report = CoverageReport(
        phase="planner",
        selected=237,
        could_not_check=208,
        exclusions=(
            MarkerExclusion(
                "not platform",
                "atdd is not running from the toolkit source checkout",
            ),
            MarkerExclusion("not github_api", "--skip-api was passed"),
        ),
    )

    rendered = render_coverage_report(report)
    assert "not platform" in rendered
    assert "atdd is not running from the toolkit source checkout" in rendered
    assert "not github_api" in rendered
    assert "--skip-api was passed" in rendered


def test_a_complete_run_says_so_rather_than_staying_silent():
    """The absence of a warning must itself be evidence.

    A run that reports nothing about coverage is exactly the state this WMBT
    exists to remove; a run that says "0 could_not_check" is a different claim
    from one that says nothing at all.
    """
    report = CoverageReport(phase="coder", selected=229, could_not_check=0)

    assert report.total == 229
    assert report.complete is True

    rendered = render_coverage_report(report)
    assert rendered.strip(), "a complete run must still render a report"
    assert "0" in rendered
    assert "229" in rendered


def test_a_partial_run_is_not_complete():
    assert CoverageReport(phase="planner", selected=237, could_not_check=208).complete is False


# --------------------------------------------------------------------------- #
# The counts come from pytest, not from an estimate                            #
# --------------------------------------------------------------------------- #


def test_counts_are_parsed_from_the_deselecting_form_of_pytest_collection_output():
    text = (
        "src/atdd/planner/validators/tests/test_wmbt_has_smoke_acceptance_helpers.py::test_x\n"
        "\n"
        "237/445 tests collected (208 deselected) in 3.42s\n"
    )
    assert parse_collected_counts(text) == (237, 208)


def test_counts_are_parsed_from_the_non_deselecting_form():
    """A run that deselected nothing still yields a total, so "N of N" is reportable."""
    text = "some::node\n\n445 tests collected in 3.22s\n"
    assert parse_collected_counts(text) == (445, 0)


def test_singular_collection_output_is_parsed():
    assert parse_collected_counts("1 test collected in 0.4s\n") == (1, 0)


def test_unparseable_output_yields_no_counts_rather_than_a_fabricated_zero():
    """The failure mode this whole WMBT is about: never invent an observation.

    If the probe's output cannot be read, the honest answer is "I do not know",
    not "nothing was deselected".
    """
    assert parse_collected_counts("") is None
    assert parse_collected_counts("ERROR: file or directory not found\n") is None
    assert parse_collected_counts("no tests ran in 0.01s\n") is None


# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #


def test_the_reported_vocabulary_is_could_not_check_and_not_skipped():
    """Aligned with GateVerdict.COULD_NOT_CHECK; distinct from pytest's "skipped".

    pytest reports skips. It does not report these. Spelling the two the same way
    would hide the one that has no other surface behind the one that already has.
    """
    assert COULD_NOT_CHECK == "could_not_check"

    rendered = render_coverage_report(
        CoverageReport(
            phase="planner",
            selected=237,
            could_not_check=208,
            exclusions=(MarkerExclusion("not platform", "consumer-mode detection"),),
        )
    )
    assert COULD_NOT_CHECK in rendered
    assert "skipped" not in rendered.lower()


def test_a_count_that_is_not_an_observation_cannot_be_read_as_one():
    """The report must not let "208 could_not_check" be read as "208 fine"."""
    rendered = render_coverage_report(
        CoverageReport(
            phase="planner",
            selected=237,
            could_not_check=208,
            exclusions=(MarkerExclusion("not platform", "consumer-mode detection"),),
        )
    )
    assert "not evaluated" in rendered.lower() or "did not evaluate" in rendered.lower()


def test_a_negative_or_contradictory_record_is_refused_rather_than_rendered():
    """Same refusal-to-guess as C013's verdict/bool contradiction check."""
    with pytest.raises(ValueError):
        CoverageReport(phase="planner", selected=-1, could_not_check=0)
    with pytest.raises(ValueError):
        CoverageReport(phase="planner", selected=10, could_not_check=-5)
