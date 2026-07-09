# URN: test:match:match-resolution:E2E-002-trace-binding
"""Trace-binding e2e test for interlocking:match-resolution (CLEAN fixture).

Captures the runtime trace from a production InterlockingRunner -> TrainRunner run
and asserts EVERY required binding field, tying the executed route back to its
interlocking YAML declaration (core afokapu/atdd#1248/#1251). Satisfies
tester.interlocking.trace-binds-declared-route.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def test_alternate_timeout_trace_binds_declared_route():
    runner = InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")
    resolution = runner.resolve_train(
        "resolve_match", inputs={"timer_expired": True}, state={}
    )
    result = TrainRunner(resolution.selected_train_id).execute(
        inputs={}, capture_trace=True
    )

    trace = result.trace
    assert trace["interlocking_id"] == "interlocking:match-resolution"
    assert trace["route_id"] == "alternate-timeout"
    assert trace["selected_train_id"] == "3207-match-resolution-timeout"
    assert trace["route_category"] == "alternate"
    assert trace["route_category_digit"] == "2"
    assert trace["guard_id"] == "guard:timer-expires"
    assert trace["resolution_strategy"] == "fail_on_multiple_match"
    assert trace["resolution_reason"] == "timer_expired == true"
