# URN: test:match:match-resolution:E2E-002-trace-binding
"""DIRTY fixture isolating tester.interlocking.trace-binds-declared-route.

Both admissible routes are exercised through the production runners (route-coverage
+ production-runner satisfied). The test DOES inspect the runtime trace, but it
omits two required binding fields (the guard identity and the resolution rationale
are never asserted), so the trace does not fully bind back to the declared route —
the only defect.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def _runner():
    return InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")


def test_nominal_route_trace():
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"all_players_voted": True}, state={}
    )
    result = TrainRunner(resolution.selected_train_id).execute(
        inputs={}, capture_trace=True
    )
    trace = result.trace
    # Two required binding fields are deliberately never asserted -> the trace does
    # not bind the declared route.
    assert trace["interlocking_id"] == "interlocking:match-resolution"
    assert trace["route_id"] == "nominal-all-voted"
    assert trace["selected_train_id"] == "3007-match-resolution-standard"
    assert trace["route_category"] == "nominal"
    assert trace["route_category_digit"] == "0"
    assert trace["resolution_strategy"] == "fail_on_multiple_match"


def test_alternate_route():
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"timer_expired": True}, state={}
    )
    assert resolution.route_id == "alternate-timeout"
    TrainRunner("3207-match-resolution-timeout").execute(inputs={}, capture_trace=True)
