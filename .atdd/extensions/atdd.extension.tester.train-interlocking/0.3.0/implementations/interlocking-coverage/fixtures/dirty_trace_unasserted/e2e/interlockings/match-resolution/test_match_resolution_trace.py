# URN: test:match:match-resolution:E001-E2E-003-trace-mentioned-not-asserted
"""DIRTY fixture — every binding field is MENTIONED, only one is ASSERTED.

The check searched the whole source for each field NAME, so a field appearing in a
dict literal counted as asserted. This tree is the shape that exposed it: it builds
a trace carrying all eight fields and then asserts exactly one of them, which proves
nothing about the route that ran — the run could resolve the wrong category or guard
and this test would still pass. That is precisely what
tester.interlocking.trace-binds-declared-route exists to refuse, and it was passing.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def test_nominal_route_trace():
    resolution = InterlockingRunner(
        "plan/_trains/_interlockings/match-resolution.yaml"
    ).resolve_train("resolve_match", inputs={"all_players_voted": True}, state={})
    result = TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)

    trace = {
        "interlocking_id": result.trace["interlocking_id"],
        "route_id": result.trace["route_id"],
        "selected_train_id": result.trace["selected_train_id"],
        "route_category": result.trace["route_category"],
        "guard_id": result.trace["guard_id"],
        "resolution_strategy": result.trace["resolution_strategy"],
        "resolution_reason": result.trace["resolution_reason"],
    }
    assert trace["route_id"] == "nominal-all-voted"


def test_alternate_route_trace():
    """Covers the second admissible route, so ONLY the trace defect is isolated.

    Without this the tree also trips route-coverage, and a fixture that fires two
    rules cannot prove either one independently.
    """
    resolution = InterlockingRunner(
        "plan/_trains/_interlockings/match-resolution.yaml"
    ).resolve_train("resolve_match", inputs={"timer_expired": True}, state={})
    result = TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)
    assert result.trace["route_id"] == "alternate-timeout"
    assert resolution.selected_train_id == "3207-match-resolution-timeout"
