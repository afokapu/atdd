# URN: test:match:match-resolution:E001-SMOKE-002-resolve-match-module
"""CLEAN fixture — a Station Master reached as a MODULE, not a class.

The sibling clean fixture exports `class StationMaster` from app.py, and the smoke
check used to require that literal name. Nothing asks for it:
`coder.train.station-master-interlocking-routing` defines the Station Master as
`python/app.py` carrying a JOURNEY_MAP — structure, not nomenclature — and the coder
detector matches it that way.

So a consumer whose entrypoint is a module-level `dispatch()` PASSED the coder rule
and FAILED the tester one, with no documented way to satisfy both. This tree is that
consumer. It must be silent.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
import app  # the Station Master entrypoint module
from trains.runtime import InterlockingRunner, TrainRunner  # production runners


def test_resolve_match_smoke_reaches_station_master():
    assert "resolve_match" in app.JOURNEY_MAP
    runner = InterlockingRunner(app.JOURNEY_MAP["resolve_match"]["path"])
    resolution = runner.resolve_train("resolve_match", inputs={"all_players_voted": True}, state={})
    result = TrainRunner(resolution.selected_train_id).execute(inputs={}, capture_trace=True)

    trace = result.trace
    assert trace["interlocking_id"] == "interlocking:match-resolution"
    assert trace["route_id"] == "nominal-all-voted"
    assert trace["selected_train_id"] == "3007-match-resolution-standard"
    assert trace["route_category"] == "nominal"
    assert trace["guard_id"] == "guard:all-voted"
    assert trace["resolution_strategy"] == "fail_on_multiple_match"
    assert trace["resolution_reason"]
