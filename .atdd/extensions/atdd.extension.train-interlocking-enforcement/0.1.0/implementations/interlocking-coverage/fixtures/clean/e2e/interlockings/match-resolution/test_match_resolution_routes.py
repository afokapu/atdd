# URN: test:match:match-resolution:E001-E2E-001-route-coverage
"""End-to-end route coverage for interlocking:match-resolution (CLEAN fixture).

Exercises EVERY admissible route of the interlocking through the production
InterlockingRunner -> TrainRunner path (core afokapu/atdd#1251): each route's
guard-true case resolves to the expected train_id, the no-match case is covered,
and the ambiguous-match case is covered for the fail_on_multiple_match strategy.
The route's category_digit is asserted in the resolution metadata.

This is consumer-tree FIXTURE code (input the detector reads as text), not part of
the detector's own pytest suite — conftest.py keeps pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def _runner():
    return InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")


def test_nominal_all_voted_resolves_standard_train():
    # guard-true case: all voted -> nominal route resolves the standard train.
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"all_players_voted": True}, state={}
    )
    assert resolution.route_id == "nominal-all-voted"
    assert resolution.selected_train_id == "3007-match-resolution-standard"
    assert resolution.route_category_digit == "0"
    TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)


def test_alternate_timeout_resolves_timeout_train():
    # guard-true case for the alternate route: 3207-match-resolution-timeout.
    resolution = _runner().resolve_train(
        "resolve_match", inputs={"timer_expired": True}, state={}
    )
    assert resolution.route_id == "alternate-timeout"
    assert resolution.selected_train_id == "3207-match-resolution-timeout"
    assert resolution.route_category_digit == "2"
    TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)


def test_no_match_raises():
    # no-match case: no guard is satisfied -> InterlockingRunner resolves nothing.
    import pytest

    with pytest.raises(Exception):
        _runner().resolve_train("resolve_match", inputs={}, state={})


def test_ambiguous_match_raises_under_fail_on_multiple():
    # ambiguous-match case: both guards true -> fail_on_multiple_match rejects it.
    import pytest

    with pytest.raises(Exception):
        _runner().resolve_train(
            "resolve_match",
            inputs={"all_players_voted": True, "timer_expired": True},
            state={},
        )
