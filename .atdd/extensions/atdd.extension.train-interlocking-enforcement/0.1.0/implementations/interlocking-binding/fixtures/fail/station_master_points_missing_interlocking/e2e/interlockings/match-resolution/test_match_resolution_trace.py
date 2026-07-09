# URN: test:match:match-resolution:E2E-bilateral-trace-binding
"""Bilateral trace-binding e2e test for interlocking:match-resolution (CLEAN fixture).

Drives the PRODUCTION InterlockingRunner -> TrainRunner path (core afokapu/atdd#1251) — no mocks —
and asserts the captured trace's interlocking_id + route_id are values DECLARED in the interlocking
YAML, closing trace_to_declaration. Consumer-tree FIXTURE code; conftest.py keeps pytest from
collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners, not mocks


def test_resolve_match_trace_binds_declared_route():
    runner = InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")
    resolution = runner.resolve_train(
        "resolve_match", inputs={"all_players_voted": True}, state={}
    )
    result = TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)

    trace = result.trace
    assert trace["interlocking_id"] == "interlocking:match-resolution"
    assert trace["route_id"] == "nominal-all-voted"
    assert trace["selected_train_id"] == "3007-match-resolution-standard"
