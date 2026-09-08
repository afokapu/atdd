# URN: test:define-plans:atdd-plan-session:Y002-INTEGRATION-002-guidelines-render-the-new-vocabulary
# Acceptance: acc:define-plans:Y002-INTEGRATION-002-guidelines-render-the-new-vocabulary
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""Y002-INTEGRATION-002 — `atdd plan guidelines` hands agents the new vocabulary.

`plan_context._GUIDELINE_PREFIXES` is `("planner.plan.", "planner.decomposition.")`,
so `atdd plan guidelines` assembles the session-lifecycle node into the agent's
working context at runtime. Leaving that node stale would hand agents the old
words from the very command meant to orient them.

The same rendering carries `planner.decomposition.canonical-steps`, which
enumerates the WMBT job steps and is frozen. So after this rename the two
vocabularies appear side by side in one context: the session gates read
Intent/Attach/Compose/Ratify while the job steps still read
Define/Locate/Prepare/Confirm. That is deliberate, and both halves are asserted
here so neither drifts into the other.

RED: the session-lifecycle node still states D/L/P/C.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.planner.commands.plan_context import load_working_context

SESSION_NODE = "planner.plan.session-lifecycle"
CANONICAL_STEPS_NODE = "planner.decomposition.canonical-steps"

NEW_STAGE_WORDS = ["Intent", "Attach", "Compose", "Ratify"]
RETIRED_STAGE_WORDS = ["Define", "Locate", "Prepare", "Confirm"]


@pytest.fixture(scope="module")
def guidelines() -> dict:
    return load_working_context(find_repo_root())["guidelines"]


def test_the_session_lifecycle_node_is_rendered_at_all(guidelines):
    assert SESSION_NODE in guidelines, (
        "the session-lifecycle node is not in the agent working context; "
        "the rest of this file would pass vacuously")


@pytest.mark.parametrize("word", NEW_STAGE_WORDS)
def test_the_session_statement_names_each_new_stage(guidelines, word):
    assert word in guidelines[SESSION_NODE]["statement"]


@pytest.mark.parametrize("word", RETIRED_STAGE_WORDS)
def test_the_session_statement_drops_each_retired_stage(guidelines, word):
    assert word not in guidelines[SESSION_NODE]["statement"]


def test_the_session_node_no_longer_carries_the_dlpc_term(guidelines):
    """`dlpc` is a term_id naming the four gates by their initials. It is not a
    bound rule ID, so it is safe to move — and it must, or the term outlives the
    vocabulary it abbreviates."""
    assert "dlpc" not in guidelines[SESSION_NODE]["terms"]


def test_the_session_node_still_defines_its_gates_under_some_term(guidelines):
    """Dropping `dlpc` must be a rename, not a deletion."""
    assert guidelines[SESSION_NODE]["terms"], "session-lifecycle lost all its terms"


def test_the_wmbt_job_step_vocabulary_rendered_alongside_is_unchanged(guidelines):
    """The frozen half of the same working context."""
    statement = guidelines[CANONICAL_STEPS_NODE]["statement"]
    for word in RETIRED_STAGE_WORDS:
        assert word in statement, (
            f"the WMBT job-step vocabulary lost {word!r} — this rename must not "
            f"reach planner.decomposition.canonical-steps")
