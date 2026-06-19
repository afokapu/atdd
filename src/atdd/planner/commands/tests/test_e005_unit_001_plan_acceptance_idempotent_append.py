# URN: test:author-plan-substrate:author-acceptance:E005-UNIT-001-idempotent-append
# Acceptance: acc:author-plan-substrate:E005-UNIT-001-idempotent-append
# WMBT: wmbt:author-plan-substrate:E005
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E005-UNIT-001 (plan acceptance) — create_acceptance appends a block and is idempotent on urn.

RED: create_acceptance does not exist yet.
"""
from __future__ import annotations

import textwrap

from atdd.planner.commands.author import create_acceptance


def _seed_wmbt(tmp_path):
    p = tmp_path / "plan" / "demo_wagon" / "E001.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent("""\
        urn: "wmbt:demo-wagon:E001"
        step: "execute"
        direction: "maximize"
        dimension: "likelihood"
        object_of_control: "thing-creation"
        lens: "functional.effectiveness"
        statement: "maximize likelihood of thing-creation"
        acceptances: []
        """), encoding="utf-8")
    return p


def test_create_acceptance_is_idempotent_on_urn(tmp_path):
    wmbt = _seed_wmbt(tmp_path)
    block = {
        "identity": {"urn": "acc:demo-wagon:E001-UNIT-001-x", "id": "AC-UNIT-001",
                     "purpose": "x", "phase": "GREEN"},
        "harness": {"type": "unit", "category": "backend"},
        "given": {"abstract": ["a"]},
        "when": {"abstract": "b"},
        "then": {"abstract": ["c"]},
    }
    create_acceptance("wmbt:demo-wagon:E001", block, root=tmp_path)
    first = wmbt.read_text()
    create_acceptance("wmbt:demo-wagon:E001", block, root=tmp_path)  # same urn → no-op
    assert wmbt.read_text() == first
