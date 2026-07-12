"""match wagon — CLEAN fixture.

A wagon transforms Cargo through run_train(). It reads and returns artifact dictionaries and does NOT
import interlocking code (Cargo boundary, core afokapu/atdd#1251).
"""


def run_match(cargo):
    cargo["match"] = {"result": {"valid_for_ranked": True}}
    return cargo
