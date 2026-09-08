# URN: test:define-plans:atdd-plan-session:Y002-UNIT-005-wmbt-step-vocabulary-is-untouched
# Acceptance: acc:define-plans:Y002-UNIT-005-wmbt-step-vocabulary-is-untouched
# WMBT: wmbt:define-plans:Y002
# Phase: RED
# Layer: unit
# Assertion: structural
"""Y002-UNIT-005 — the rename did not bleed into the WMBT step vocabulary.

`define`, `locate`, `prepare` and `confirm` belong to TWO unrelated naming
systems. This rename moves the plan-session gates. It must not touch the WMBT
job-step vocabulary, whose letters are artifact filename prefixes — a
find-and-replace over the four words hits both systems, and only one of them
should move.

This is a tripwire, not a behaviour change: it passes before and after. That is
the point — it fails only if the rename over-reaches.
"""
from __future__ import annotations

import json
from pathlib import Path

import atdd
from atdd.planner.validators.test_wmbt_vocabulary import AUTHORIZED_STEPS

# The plan-session stage names, which must NEVER appear as WMBT job steps.
SESSION_STAGE_NAMES = {"intent", "attach", "compose", "ratify"}

SCHEMA_PATH = (Path(atdd.__file__).resolve().parent
               / "planner" / "schemas" / "wmbt.schema.json")


def test_the_four_shared_words_still_map_to_their_letters():
    assert AUTHORIZED_STEPS["define"] == "D"
    assert AUTHORIZED_STEPS["locate"] == "L"
    assert AUTHORIZED_STEPS["prepare"] == "P"
    assert AUTHORIZED_STEPS["confirm"] == "C"


def test_the_nine_authorized_steps_are_unchanged():
    assert AUTHORIZED_STEPS == {
        "define": "D", "locate": "L", "prepare": "P", "confirm": "C",
        "execute": "E", "monitor": "M", "modify": "Y", "resolve": "R",
        "conclude": "K",
    }


def test_no_session_stage_name_leaked_into_the_wmbt_vocabulary():
    leaked = SESSION_STAGE_NAMES & set(AUTHORIZED_STEPS)
    assert not leaked, f"plan-session stage names leaked into WMBT steps: {leaked}"


def test_the_schema_mirror_still_carries_the_same_nine_steps():
    """wmbt.schema.json mirrors AUTHORIZED_STEPS and is frozen with it."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["step"]["enum"] == list(AUTHORIZED_STEPS)
