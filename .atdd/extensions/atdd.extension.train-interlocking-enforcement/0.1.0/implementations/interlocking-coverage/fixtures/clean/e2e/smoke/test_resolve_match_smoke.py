# URN: test:match:match-resolution:E001-SMOKE-001-resolve-match
"""Station Master smoke test for the exposed resolve_match action (CLEAN fixture).

Drives the exposed action through the REAL entrypoint -> Station Master ->
InterlockingRunner -> TrainRunner path (core afokapu/atdd#1251) and asserts the
captured trace binds the declared route. Satisfies
tester.interlocking.smoke-coverage-for-station-master AND
tester.interlocking.trace-binds-declared-route for the clean tree.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from app import StationMaster  # real action entrypoint -> Station Master
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def test_resolve_match_smoke_reaches_station_master():
    # 1. a real action endpoint reaches the Station Master.
    station_master = StationMaster()
    # 2. the Station Master chooses the interlocking path (InterlockingRunner),
    #    3. InterlockingRunner resolves the route, 4. TrainRunner executes it.
    result = station_master.handle_action(
        "resolve_match", inputs={"all_players_voted": True}
    )
    assert isinstance(station_master.interlocking_runner, InterlockingRunner)
    assert isinstance(station_master.train_runner, TrainRunner)
    assert result.selected_train_id == "3007-match-resolution-standard"

    # 5. the trace records the interlocking binding fields (binds declared route).
    trace = result.trace
    assert trace["interlocking_id"] == "interlocking:match-resolution"
    assert trace["route_id"] == "nominal-all-voted"
    assert trace["selected_train_id"] == "3007-match-resolution-standard"
    assert trace["route_category"] == "nominal"
    assert trace["route_category_digit"] == "0"
    assert trace["guard_id"] == "guard:all-voted"
    assert trace["resolution_strategy"] == "fail_on_multiple_match"
    assert trace["resolution_reason"]
