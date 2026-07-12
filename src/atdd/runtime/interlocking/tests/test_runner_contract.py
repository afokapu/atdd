# URN: test:atdd-runtime:interlocking-runner:contract-and-forbidden-boundaries
# Issue: #1251 (consumes #1248)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1251 runtime InterlockingRunner contract — resolution + delegation boundary.

Asserts the runtime route-control contract: Station Master resolves an action to
either a direct ``train_id`` or an interlocking; ``InterlockingRunner.resolve_train``
reuses the #1248 safe guard/route API to resolve exactly one admissible train,
fails closed on no-match / ambiguous-match / category mismatch / missing train
file, and ``execute`` delegates the selected train to the production TrainRunner
seam WITHOUT executing wagons, mutating Cargo, or using raw ``eval``.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from atdd.planner.interlocking.tests._fixtures import (
    ALTERNATE_TRAIN_ID,
    ALTERNATE_TRAIN_PATH,
    NOMINAL_TRAIN_ID,
    NOMINAL_TRAIN_PATH,
    interlocking_doc,
    write_tree,
)
from atdd.runtime.interlocking import (
    DirectTrainTarget,
    InterlockingResolution,
    InterlockingResolutionError,
    InterlockingRunner,
    InterlockingTarget,
    StationMasterError,
    resolve_journey,
)


class _RecordingExecutor:
    """A fake production TrainRunner seam: records the single delegated call.

    It only records and returns an opaque ``TrainResult`` sentinel; it never
    exposes a wagon-stepping or Cargo-mutation surface, so a runner that tries to
    drive a train through it could not (there is nothing to call).
    """

    def __init__(self):
        self.calls: list[dict] = []

    def execute(
        self,
        train_id,
        *,
        inputs,
        state=None,
        timing=None,
        capture_trace=True,
        interlocking_trace=None,
    ):
        self.calls.append(
            {
                "train_id": train_id,
                "inputs": inputs,
                "state": state,
                "timing": timing,
                "capture_trace": capture_trace,
                "interlocking_trace": interlocking_trace,
            }
        )
        return {"train_result": train_id, "trace": {"interlocking": interlocking_trace}}


@pytest.fixture()
def il_path(tmp_path: Path) -> Path:
    return write_tree(tmp_path)


# --------------------------------------------------------------------------- #
# Station Master JOURNEY_MAP — both shapes, additive, fail-closed
# --------------------------------------------------------------------------- #
def test_journey_map_direct_train_mapping():
    journey = {"start_match": "3001-solo-match-complete"}
    target = resolve_journey(journey, "start_match")
    assert isinstance(target, DirectTrainTarget)
    assert target.train_id == "3001-solo-match-complete"


def test_journey_map_interlocking_mapping():
    journey = {
        "resolve_match": {
            "interlocking_id": "interlocking:match-resolution",
            "path": "plan/_trains/_interlockings/match-resolution.yaml",
        }
    }
    target = resolve_journey(journey, "resolve_match")
    assert isinstance(target, InterlockingTarget)
    assert target.interlocking_id == "interlocking:match-resolution"
    assert target.path == "plan/_trains/_interlockings/match-resolution.yaml"


def test_journey_map_unknown_action_fails_closed():
    with pytest.raises(StationMasterError):
        resolve_journey({"start_match": "3001-x"}, "nope")


def test_journey_map_malformed_mapping_fails_closed():
    # Missing 'path' -> not a valid interlocking target and not a string -> closed.
    with pytest.raises(StationMasterError):
        resolve_journey({"resolve_match": {"interlocking_id": "x"}}, "resolve_match")


# --------------------------------------------------------------------------- #
# resolve_train — exactly one admissible route, structured resolution
# --------------------------------------------------------------------------- #
def test_resolve_train_returns_structured_resolution(il_path: Path):
    runner = InterlockingRunner(il_path)
    res = runner.resolve_train("resolve_match", {"all_players_voted": True})
    assert isinstance(res, InterlockingResolution)
    assert res.interlocking_id == "interlocking:match-resolution"
    assert res.route_id == "nominal-all-voted"
    assert res.train_id == NOMINAL_TRAIN_ID
    assert res.category == "nominal"
    assert res.guard_id == "guard:all-voted"
    assert res.resolution_strategy == "fail_on_multiple_match"
    assert res.reason  # non-empty human reason


def test_resolve_train_selects_alternate_route(il_path: Path):
    runner = InterlockingRunner(il_path)
    res = runner.resolve_train("resolve_match", {"timer_expired": True})
    assert res.route_id == "alternate-timeout"
    assert res.train_id == ALTERNATE_TRAIN_ID
    assert res.category == "alternate"


def test_resolve_train_fails_closed_on_no_match(il_path: Path):
    runner = InterlockingRunner(il_path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("resolve_match", {"all_players_voted": False})


def test_resolve_train_fails_closed_on_ambiguous_match(il_path: Path):
    runner = InterlockingRunner(il_path)
    # Both guards true under fail_on_multiple_match -> ambiguous -> closed.
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train(
            "resolve_match", {"all_players_voted": True, "timer_expired": True}
        )


def test_resolve_train_fails_closed_on_unknown_action(il_path: Path):
    runner = InterlockingRunner(il_path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("not_an_entrypoint", {"all_players_voted": True})


# --------------------------------------------------------------------------- #
# resolve_train — selected-route validation (category field, train file)
# --------------------------------------------------------------------------- #
def test_resolve_train_rejects_category_mismatch(tmp_path: Path):
    doc = interlocking_doc()
    # The selected `nominal` route now points at a train declaring `alternate`.
    # Judged on the train's category FIELD (#1421), not a digit in the identity.
    doc["routes"][0]["train_id"] = ALTERNATE_TRAIN_ID
    doc["routes"][0]["train_path"] = ALTERNATE_TRAIN_PATH
    path = write_tree(tmp_path, doc)
    runner = InterlockingRunner(path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("resolve_match", {"all_players_voted": True})


def test_resolve_train_rejects_missing_train_file(tmp_path: Path):
    path = write_tree(tmp_path)
    # Delete the target train file for the nominal route.
    (tmp_path / NOMINAL_TRAIN_PATH).unlink()
    runner = InterlockingRunner(path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("resolve_match", {"all_players_voted": True})


# --------------------------------------------------------------------------- #
# execute — delegates exactly one train_id to the production TrainRunner seam
# --------------------------------------------------------------------------- #
def test_execute_delegates_single_train_to_executor(il_path: Path):
    executor = _RecordingExecutor()
    runner = InterlockingRunner(il_path, train_executor=executor)
    result = runner.execute("resolve_match", {"all_players_voted": True})
    assert len(executor.calls) == 1
    call = executor.calls[0]
    assert call["train_id"] == NOMINAL_TRAIN_ID
    assert result["train_result"] == NOMINAL_TRAIN_ID


def test_execute_passes_interlocking_trace_to_executor(il_path: Path):
    executor = _RecordingExecutor()
    runner = InterlockingRunner(il_path, train_executor=executor)
    runner.execute("resolve_match", {"all_players_voted": True})
    trace = executor.calls[0]["interlocking_trace"]
    for key in (
        "interlocking_id",
        "route_id",
        "selected_train_id",
        "route_category",
        "guard_id",
        "resolution_strategy",
        "resolution_reason",
    ):
        assert key in trace, f"trace missing required field {key!r}"
    assert trace["selected_train_id"] == NOMINAL_TRAIN_ID
    assert trace["route_category"] == "nominal"


def test_execute_forwards_timing_and_capture_trace(il_path: Path):
    executor = _RecordingExecutor()
    runner = InterlockingRunner(il_path, train_executor=executor)
    runner.execute(
        "resolve_match",
        {"all_players_voted": True},
        timing={"deadline_ms": 5},
        capture_trace=False,
    )
    call = executor.calls[0]
    assert call["timing"] == {"deadline_ms": 5}
    assert call["capture_trace"] is False


def test_execute_fails_closed_without_executing_when_unresolved(il_path: Path):
    executor = _RecordingExecutor()
    runner = InterlockingRunner(il_path, train_executor=executor)
    with pytest.raises(InterlockingResolutionError):
        runner.execute("resolve_match", {})  # no guard true -> no match
    assert executor.calls == []  # never delegated -> never executed a train


def test_execute_without_executor_is_an_error(il_path: Path):
    runner = InterlockingRunner(il_path)  # no executor wired
    with pytest.raises(InterlockingResolutionError):
        runner.execute("resolve_match", {"all_players_voted": True})


# --------------------------------------------------------------------------- #
# Forbidden boundaries — no wagon stepping, no Cargo mutation, no raw eval
# --------------------------------------------------------------------------- #
def test_runner_has_no_wagon_or_cargo_surface():
    # The runner is route-control only: it must expose no method that would let
    # it execute a wagon step, pick the next step, or mutate Cargo.
    forbidden = {
        "run_train",
        "run_wagon",
        "step",
        "next_step",
        "advance",
        "mutate_cargo",
        "set_artifact",
        "put_artifact",
    }
    surface = {name for name in dir(InterlockingRunner) if not name.startswith("_")}
    assert not (forbidden & surface), forbidden & surface


def test_execute_does_not_mutate_caller_inputs(il_path: Path):
    executor = _RecordingExecutor()
    runner = InterlockingRunner(il_path, train_executor=executor)
    inputs = {"all_players_voted": True}
    snapshot = copy.deepcopy(inputs)
    runner.execute("resolve_match", inputs)
    assert inputs == snapshot  # Cargo/input data plane untouched by route control


def test_guards_use_no_raw_eval(tmp_path: Path):
    # A guard expression carrying a code-injection payload must be rejected by the
    # declarative grammar (surfaced as a resolution error), never evaluated.
    doc = interlocking_doc()
    doc["fragments"][0]["guards"][0]["expression"] = "__import__('os').system('x') == 0"
    path = write_tree(tmp_path, doc)
    runner = InterlockingRunner(path)
    with pytest.raises(InterlockingResolutionError):
        runner.resolve_train("resolve_match", {"all_players_voted": True})


def test_runner_source_contains_no_eval_or_exec():
    # Structural guarantee: the runtime route-control source uses no eval/exec.
    import atdd.runtime.interlocking as pkg

    pkg_dir = Path(pkg.__file__).resolve().parent
    for py in pkg_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "eval(" not in text, f"{py} contains eval("
        assert "exec(" not in text, f"{py} contains exec("
