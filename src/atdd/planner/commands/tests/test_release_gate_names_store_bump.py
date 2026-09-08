"""The generated Release Gate must not tell operators to bump by hand (#1646).

`CONDUCTOR.md::release` states that the version lives in the State Store, that
`pyproject.toml` carries no `version =` line, and that a hand-edited version
must not be re-introduced. The issue-body generator said the opposite —
"bump the version manually" — under an `INTERIM` marker whose interim ended
when #1172 shipped. Every issue authored by the tool carried that instruction,
so an agent reading its own issue body was pointed at a retired mechanism.
"""
from atdd.planner.commands.author_issue import create_issue_body, validate_issue_body


def test_release_gate_names_the_state_store_command():
    body = create_issue_body()

    assert "atdd state version bump" in body


def test_release_gate_never_instructs_a_manual_bump():
    body = create_issue_body()

    lowered = body.lower()
    assert "manually" not in lowered
    assert "bump the version per branch prefix" not in lowered


def test_generated_body_still_validates_against_the_schema():
    """The wording change must not disturb the section structure."""
    assert validate_issue_body(create_issue_body()) == []
