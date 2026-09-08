"""match wagon — DIRTY fixture.

BUG: a wagon imports interlocking code, violating the Cargo boundary (core afokapu/atdd#1251).
"""
from trains.interlocking import InterlockingRunner  # forbidden: wagon imports interlocking


def run_match(cargo):
    _ = InterlockingRunner
    cargo["match"] = {"result": {"valid_for_ranked": True}}
    return cargo
