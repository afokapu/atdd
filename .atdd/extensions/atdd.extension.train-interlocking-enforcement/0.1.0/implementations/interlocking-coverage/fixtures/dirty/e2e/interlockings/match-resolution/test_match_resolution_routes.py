# URN: test:match:match-resolution:E001-E2E-001-route-coverage
"""End-to-end route coverage for interlocking:match-resolution (DIRTY fixture).

Exercises ONLY the nominal route. The interlocking's second admissible route (the
timeout branch) is referenced by neither its route_id nor its train_id anywhere
here, so it is an uncovered route — the silent-green gap the detector must flag.

Consumer-tree FIXTURE code (input the detector reads as text); conftest.py keeps
pytest from collecting it.
"""
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def test_nominal_all_voted_resolves_standard_train():
    resolution = InterlockingRunner(
        "plan/_trains/_interlockings/match-resolution.yaml"
    ).resolve_train("resolve_match", inputs={"all_players_voted": True}, state={})
    assert resolution.route_id == "nominal-all-voted"
    assert resolution.selected_train_id == "3007-match-resolution-standard"
    assert resolution.route_category_digit == "0"
    TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)
