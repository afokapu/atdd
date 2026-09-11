# URN: test-support:atdd-plan-core:session-machine:plan-session-fixtures
"""Shared plan-session spec fixtures for the confirm-gate validators (#1929).

Each of these validators exercises ONE confirm gate — artifact naming, path
mirroring, interlocking sanity, issue binding, verb-object naming — so their
wagon units used to carry only the one or two keys their own gate reads.

``planner.plan.spec-is-schema-valid`` now checks kept specs for completeness
before the lock, and a two-key wagon cannot satisfy ``wagon.schema.json``. That
is not a fixture inconvenience: ``create_wagon({"wagon": "manage-users"})``
would have raised ``AuthorInputError`` at author time anyway, so these sessions
described a decomposition that could never have been written. ``wagon_spec()``
is the realistic floor each gate's own fields are then layered onto.
"""
from __future__ import annotations

#: The required fields of `wagon.schema.json` that no confirm gate reads, at
#: values that satisfy every pattern. Keep this the MINIMUM: a fixture that
#: over-specifies stops exercising its own gate's defaults.
_WAGON_REQUIRED_FLOOR = {
    "description": "the wagon under test in a confirm-gate fixture",
    "subject": "agent:planner",
    "context": "administration",
    "action": "manages users",
    "goal": "users are governed",
    "outcome": "user records are current",
    # `produce` is required and non-empty; a caller exercising the artifact
    # gates overrides it with the entry its own gate reads.
    "produce": [{"name": "commons:users", "contract": None}],
}


def wagon_spec(slug: str = "manage-users", **over) -> dict:
    """A wagon spec complete enough to reach the gate under test.

    ``slug`` must be verb-object (the #1276 gate runs before this one).
    ``over`` layers the fields the calling gate actually exercises — typically
    ``produce`` or ``theme`` — over the floor.
    """
    spec = {"wagon": slug, **_WAGON_REQUIRED_FLOOR}
    spec.update(over)
    return spec


def train_spec(train_id: str = "3007-match-resolution-standard", **over) -> dict:
    """A train spec complete enough to reach the gate under test.

    Same rationale as :func:`wagon_spec`: these fixtures carried only
    ``source_interlocking`` because that is all the interlocking gate reads, and
    ``create_train`` would have raised on the rest at author time anyway.
    """
    spec = {
        "train_id": train_id,
        "title": "the train under test",
        "description": "the train a confirm-gate fixture keeps",
        "themes": ["commons"],
        "participants": ["wagon:manage-users"],
        "sequence": [{"step": 1, "intent": "carry the route under test",
                      "from": "wagon:manage-users", "to": "wagon:manage-users",
                      "artifact": "commons:users:record"}],
    }
    spec.update(over)
    return spec
