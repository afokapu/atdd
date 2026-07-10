# URN: test:author-plan-substrate:author-plan-spine:C008-UNIT-001-spine-rejects-non-object-spec
# Acceptance: acc:author-plan-substrate:C008-UNIT-001-spine-rejects-non-object-spec
# WMBT: wmbt:author-plan-substrate:C008
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C008-UNIT-001 (plan spine) — validate_author_spec rejects a non-object author spec.

Every per-kind plan writer reads its input with ``spec.get(...)``, so a spec that
is valid JSON but not an object (a string, list, number, boolean, or null)
detonates inside the writer. The spine must refuse it at the input guard,
carrying the offending field, before a unit is admitted or a writer runs.

RED: ``validate_author_spec`` does not exist yet. It is imported inside each
test body, not at module level, so its absence surfaces as a failing test rather
than a collection ImportError that would abort the whole suite.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError


@pytest.mark.parametrize(
    "spec, type_name",
    [
        ("hello", "string"),
        ([1, 2], "list"),
        (5, "number"),
        (1.5, "number"),
        (True, "boolean"),
        (None, "null"),
    ],
)
def test_validate_author_spec_rejects_non_object(spec, type_name):
    from atdd.planner.commands.author import validate_author_spec

    with pytest.raises(AuthorInputError) as exc:
        validate_author_spec(spec)

    assert exc.value.field == "spec", "the refusal must name the offending --spec field"
    assert type_name in str(exc.value), (
        f"the message must name the JSON type actually received ({type_name!r}); got {exc.value}"
    )


@pytest.mark.parametrize("spec", [{}, {"wagon": "play-audio"}])
def test_validate_author_spec_accepts_an_object(spec):
    from atdd.planner.commands.author import validate_author_spec

    assert validate_author_spec(spec) is None, "a dict spec must be accepted unchanged"
