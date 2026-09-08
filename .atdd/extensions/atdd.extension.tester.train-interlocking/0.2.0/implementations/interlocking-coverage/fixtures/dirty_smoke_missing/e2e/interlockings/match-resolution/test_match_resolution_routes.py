# URN: test:match:match-resolution:E001-E2E-001-route-coverage
"""DIRTY fixture isolating tester.interlocking.smoke-coverage-for-station-master.

Both admissible routes are exercised through the production runners (route-coverage
+ production-runner satisfied) by calling InterlockingRunner DIRECTLY. No test ever
reaches the Station Master for the exposed resolve_match action, so the exposed
action has no smoke coverage — the only defect.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def _runner():
    return InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")


def test_nominal_route():
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"all_players_voted": True}, state={}
    )
    assert resolution.route_id == "nominal-all-voted"
    TrainRunner("3007-match-resolution-standard").execute(inputs={}, capture_trace=True)


def test_alternate_route():
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"timer_expired": True}, state={}
    )
    assert resolution.route_id == "alternate-timeout"
    TrainRunner("3207-match-resolution-timeout").execute(inputs={}, capture_trace=True)
