"""InterlockingRunner — DIRTY fixture.

A broken route-control layer that competes with TrainRunner and Cargo:
  * resolve_train returns a bare train_id string (no structured InterlockingResolution model)
  * imports a wagon module directly
  * calls run_train(...) directly
  * loops over train.sequence as a step executor
  * references / mutates Cargo and stores artifact_urn values
All forbidden by core afokapu/atdd#1251.
"""
from match.wagon import run_match  # direct wagon import (forbidden)


class InterlockingRunner:
    def __init__(self, interlocking_yaml_path):
        self._path = interlocking_yaml_path

    def resolve_train(self, action, inputs, state=None):
        # BUG: bare train_id string, not a structured resolution model.
        return "3001-solo-match-complete"

    def execute(self, action, inputs, state=None, timing=None, capture_trace=True):
        train = _load_train(self._path)
        cargo = Cargo(inputs)  # references Cargo symbol (forbidden)
        for step in train.sequence:  # loops over train.sequence as executor (forbidden)
            cargo = run_train(step, cargo)  # calls run_train directly (forbidden)
        cargo["artifact_urn:match"] = run_match(cargo)  # mutates cargo + artifact_urn (forbidden)
        return cargo


def run_train(step, cargo):
    return cargo


class Cargo(dict):
    pass


def _load_train(path):
    class _T:
        sequence = ["match"]

    return _T()
