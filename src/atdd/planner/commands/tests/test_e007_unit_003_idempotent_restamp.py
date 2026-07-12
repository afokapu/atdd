# URN: test:author-plan-substrate:author-interlocking:E007-UNIT-003-idempotent-restamp
# Acceptance: acc:author-plan-substrate:E007-UNIT-003-idempotent-restamp
# WMBT: wmbt:author-plan-substrate:E007
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-003 — authoring the same interlocking twice on unchanged inputs is
byte-identical (idempotent stamp + idempotent registry insert).

RED: create_interlocking does not exist yet.
"""
from __future__ import annotations

from atdd.planner.commands.author import create_interlocking
from atdd.planner.commands.tests._il_author_fixtures import (
    anchor_spec,
    author_route_train,
)


def test_reauthoring_is_byte_identical(tmp_path):
    author_route_train(tmp_path)

    il_path = create_interlocking(anchor_spec(), root=tmp_path)
    first_artifact = il_path.read_bytes()
    first_registry = (tmp_path / "plan" / "_trains" / "_interlockings.yaml").read_bytes()

    il_path2 = create_interlocking(anchor_spec(), root=tmp_path)
    assert il_path2 == il_path
    assert il_path.read_bytes() == first_artifact
    assert (tmp_path / "plan" / "_trains" / "_interlockings.yaml").read_bytes() == first_registry
